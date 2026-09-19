"""Run a short Python script in a disposable working directory.

Isolation goals (pragmatic, not a perfect jail):
- temp cwd only for user files
- stripped env + minimal PATH (no nvm / user toolchains)
- wall-clock timeout + optional memory soft-cap
- on macOS: Seatbelt denies reading/writing under /Users except the venv,
  and denies network
- in-process guards block the common escape hatches (subprocess, os.system)

Uploaded inputs are copied in; new files the script writes are saved for download.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import sys
import tempfile
import textwrap
from pathlib import Path

from agent_console.repositories.files import FileTooLargeError, UnknownFileError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]

_SCRIPT_NAME = "_agent_script.py"
_RUNNER_NAME = "_agent_runner.py"
_PROFILE_NAME = "_agent_sandbox.sb"
_CACHE_DIR = "_sandbox_cache"
_MAX_CODE_CHARS = 80_000
_MAX_OUTPUT_FILES = 20
_SKIP_NAMES = {_SCRIPT_NAME, _RUNNER_NAME, _PROFILE_NAME}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n…[{omitted} characters truncated]"


def _runner_source(max_bytes: int) -> str:
    """Child entrypoint: soft memory cap, FS/process guards, then run the script."""
    # Guards run in the child so they apply even when Seatbelt is unavailable.
    return textwrap.dedent(
        f"""\
        import builtins
        import os
        import sys

        _CWD = os.path.realpath(os.getcwd())
        _ALLOWED_PREFIXES = (
            _CWD,
            os.path.realpath(sys.prefix),
            os.path.realpath(sys.base_prefix),
            "/usr",
            "/System",
            "/Library",
            "/opt",
            "/tmp",
            "/private/tmp",
            "/private/var/folders",
            "/var/folders",
        )

        def _allowed(path: str, *, write: bool) -> bool:
            try:
                real = os.path.realpath(path)
            except OSError:
                return False
            if write:
                return real == _CWD or real.startswith(_CWD + os.sep)
            return any(
                real == prefix or real.startswith(prefix.rstrip("/") + "/")
                for prefix in _ALLOWED_PREFIXES
            )

        _real_open = builtins.open

        def _guarded_open(file, mode="r", *args, **kwargs):
            path = file if isinstance(file, (str, bytes, os.PathLike)) else str(file)
            mode_s = mode.decode() if isinstance(mode, bytes) else str(mode)
            writing = any(flag in mode_s for flag in "wax+")
            if not _allowed(os.fspath(path), write=writing):
                raise PermissionError(
                    f"sandbox: path not allowed in run_python: {{os.fspath(path)!r}}"
                )
            return _real_open(file, mode, *args, **kwargs)

        builtins.open = _guarded_open

        def _blocked(*_a, **_k):
            raise PermissionError(
                "sandbox: subprocess / shell execution is blocked in run_python"
            )

        try:
            import subprocess

            subprocess.Popen = _blocked  # type: ignore[assignment]
            subprocess.call = _blocked  # type: ignore[assignment]
            subprocess.run = _blocked  # type: ignore[assignment]
            subprocess.check_call = _blocked  # type: ignore[assignment]
            subprocess.check_output = _blocked  # type: ignore[assignment]
            subprocess.getoutput = _blocked  # type: ignore[assignment]
            subprocess.getstatusoutput = _blocked  # type: ignore[assignment]
        except Exception:
            pass

        for name in ("system", "popen", "execv", "execve", "execvp", "execvpe", "execl", "execlp", "execle"):
            if hasattr(os, name):
                setattr(os, name, _blocked)

        try:
            import resource

            _cap = {int(max_bytes)}
            _soft, _hard = resource.getrlimit(resource.RLIMIT_AS)
            if _hard != resource.RLIM_INFINITY:
                _cap = min(_cap, _hard)
            resource.setrlimit(resource.RLIMIT_AS, (_cap, _hard))
        except Exception:
            pass

        import runpy

        runpy.run_path({_SCRIPT_NAME!r}, run_name="__main__")
        """
    )


def _seatbelt_profile(*, cwd: Path, venv: Path, base_prefix: Path) -> str:
    """macOS Seatbelt: block network and home-dir reads outside the venv/cwd."""
    cwd_s = str(cwd.resolve())
    venv_s = str(venv.resolve())
    base_s = str(base_prefix.resolve())
    return textwrap.dedent(
        f"""\
        (version 1)
        (allow default)
        (deny network*)
        (deny file-read*
          (require-all
            (regex #"^/Users/")
            (require-not (subpath "{venv_s}"))
            (require-not (subpath "{base_s}"))
            (require-not (subpath "{cwd_s}"))
          ))
        (deny file-write*
          (require-all
            (regex #"^/Users/")
            (require-not (subpath "{venv_s}"))
            (require-not (subpath "{cwd_s}"))
          ))
        """
    )


def _guess_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _is_user_output(path: Path, cwd: Path) -> bool:
    """Skip sandbox internals and library caches (matplotlib fontlist, etc.)."""
    try:
        rel = path.relative_to(cwd)
    except ValueError:
        return False
    if any(part.startswith("_") or part.startswith(".") for part in rel.parts[:-1]):
        return False
    if path.name in _SKIP_NAMES or path.name.startswith("."):
        return False
    lower = path.name.lower()
    if lower.startswith("fontlist") and lower.endswith(".json"):
        return False
    if "__pycache__" in rel.parts:
        return False
    return True


def _collect_output_paths(cwd: Path, staged: set[str]) -> list[Path]:
    """Walk the sandbox cwd without following symlinks; stay under cwd."""
    root = cwd.resolve()
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(cwd, followlinks=False):
        base = Path(dirpath)
        # Don't descend into symlink directories (followlinks=False already,
        # but also prune hidden / cache dirs early).
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".")
            and not name.startswith("_")
            and name != "__pycache__"
            and not (base / name).is_symlink()
        ]
        for name in filenames:
            path = base / name
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            if path.name in staged:
                continue
            try:
                if not path.resolve().is_relative_to(root):
                    continue
            except (OSError, ValueError):
                continue
            if _is_user_output(path, cwd):
                found.append(path)
    return sorted(found)

def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id
    settings = context.settings

    @registry.tool(
        name="run_python",
        description=(
            "Run a short Python script when the task needs code: charts/plots, "
            "CSV/Excel transforms, generating files, or multi-step computation. "
            "Call this on your own when that fits — do not wait for the user to "
            "say \"Python\". Prefer `calculate` only for a single arithmetic "
            "expression. Available libraries include the stdlib plus matplotlib "
            "(use a non-interactive backend / savefig), openpyxl, python-docx, "
            "and pypdf. Prefer `write_file` with a .docx/.xlsx name for simple "
            "docs/spreadsheets; use `run_python` when you need charts or custom "
            "layout. Optional `inputs` copies uploaded files into the cwd. New "
            "files the script writes are saved for download. Sandboxed: no "
            "network, no access to the host home directory, no subprocess/shell. "
            "Only the temp working directory and staged uploads are readable."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Full Python source to run (not a REPL snippet).",
                },
                "inputs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional upload names or ids to copy into the working "
                        "directory before the script starts."
                    ),
                },
            },
            "required": ["code"],
        },
    )
    async def run_python(code: str = "", inputs: list[str] | None = None) -> str:
        source = code if isinstance(code, str) else ""
        if not source.strip():
            return (
                "Error: missing required argument `code`. Pass the full Python "
                "source as a string in one call. For a simple .docx/.xlsx summary, "
                "prefer `write_file` instead of run_python."
            )
        if len(source) > _MAX_CODE_CHARS:
            return (
                f"Error: code is {len(source)} characters; "
                f"the limit is {_MAX_CODE_CHARS}."
            )

        input_names = [str(name).strip() for name in (inputs or []) if str(name).strip()]
        timeout = float(settings.python_timeout)
        out_limit = int(settings.python_max_output_chars)
        mem_bytes = int(settings.python_memory_bytes)

        with tempfile.TemporaryDirectory(prefix="agent-py-") as tmp:
            cwd = Path(tmp)
            cache = cwd / _CACHE_DIR
            cache.mkdir()
            staged: set[str] = set()

            for ref in input_names:
                try:
                    row = await files.get(user_id, ref)
                    data = await files.raw_bytes(user_id, ref)
                except UnknownFileError as exc:
                    return f"Error: {exc}"
                target = cwd / Path(row.name).name
                if target.name in _SKIP_NAMES or target.name.startswith("."):
                    return f"Error: cannot stage input named {target.name!r}."
                target.write_bytes(data)
                staged.add(target.name)

            (cwd / _SCRIPT_NAME).write_text(source, encoding="utf-8")
            (cwd / _RUNNER_NAME).write_text(_runner_source(mem_bytes), encoding="utf-8")

            env = {
                # Do not inherit the host PATH (nvm, global npm, homebrew extras).
                "PATH": "/usr/bin:/bin",
                "HOME": str(cache),
                "TMPDIR": str(cache),
                "MPLCONFIGDIR": str(cache / "mpl"),
                "XDG_CACHE_HOME": str(cache / "xdg"),
                "LANG": os.environ.get("LANG", "en_US.UTF-8"),
                "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "MPLBACKEND": "Agg",
            }

            python = Path(sys.executable).resolve()
            argv = [str(python), _RUNNER_NAME]
            if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file():
                profile = cwd / _PROFILE_NAME
                profile.write_text(
                    _seatbelt_profile(
                        cwd=cwd,
                        venv=Path(sys.prefix),
                        base_prefix=Path(sys.base_prefix),
                    ),
                    encoding="utf-8",
                )
                argv = [
                    "/usr/bin/sandbox-exec",
                    "-f",
                    str(profile),
                    *argv,
                ]

            try:
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    cwd=str(cwd),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as exc:
                return f"Error: could not start Python: {exc}"
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except TimeoutError:
                try:
                    os.killpg(process.pid, 9)
                except (ProcessLookupError, PermissionError, OSError):
                    process.kill()
                await process.wait()
                return (
                    f"Error: script exceeded the {timeout:g}s time limit and was killed."
                )

            exit_code = process.returncode if process.returncode is not None else -1
            stdout = _truncate(stdout_b.decode("utf-8", errors="replace"), out_limit)
            stderr = _truncate(stderr_b.decode("utf-8", errors="replace"), out_limit)

            saved: list[str] = []
            errors: list[str] = []
            produced = _collect_output_paths(cwd, staged)
            max_bytes = settings.max_upload_bytes
            for path in produced[:_MAX_OUTPUT_FILES]:
                try:
                    size = path.stat().st_size
                    if size > max_bytes:
                        errors.append(
                            f"{path.name}: {size} bytes exceeds limit "
                            f"({max_bytes} bytes)"
                        )
                        continue
                    data = path.read_bytes()
                    row = await files.save(
                        user_id,
                        name=path.name,
                        data=data,
                        content_type=_guess_type(path),
                    )
                    saved.append(
                        f"{row.name} ({row.size} bytes) — "
                        f"/api/files/{row.id}/download"
                    )
                except FileTooLargeError as exc:
                    errors.append(str(exc))
                except OSError as exc:
                    errors.append(f"{path.name}: {exc}")

            if len(produced) > _MAX_OUTPUT_FILES:
                errors.append(
                    f"skipped {len(produced) - _MAX_OUTPUT_FILES} extra output files "
                    f"(cap {_MAX_OUTPUT_FILES})"
                )

        parts = [f"exit_code={exit_code}"]
        if stdout.strip():
            parts.append(f"stdout:\n{stdout}")
        else:
            parts.append("stdout: (empty)")
        if stderr.strip():
            parts.append(f"stderr:\n{stderr}")
        if saved:
            parts.append("saved files:\n" + "\n".join(f"- {line}" for line in saved))
        if errors:
            parts.append("save notes:\n" + "\n".join(f"- {line}" for line in errors))
        return "\n\n".join(parts)
