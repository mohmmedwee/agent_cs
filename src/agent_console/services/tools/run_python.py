"""Run a short Python script in a disposable working directory.

The model gets a real interpreter for charts, transforms, and exact computation
that AST `calculate` cannot cover. Isolation is pragmatic, not a hardened jail:
temp cwd, stripped env, wall-clock timeout, optional memory soft-cap on Linux,
and HITL before every call. Network is not OS-blocked in v1 — treat approval as
the primary gate.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import sys
import tempfile
from pathlib import Path

from agent_console.repositories.files import FileTooLargeError, UnknownFileError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]

_SCRIPT_NAME = "_agent_script.py"
_RUNNER_NAME = "_agent_runner.py"
_CACHE_DIR = "_sandbox_cache"
_MAX_CODE_CHARS = 80_000
_MAX_OUTPUT_FILES = 20
_SKIP_NAMES = {_SCRIPT_NAME, _RUNNER_NAME}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n…[{omitted} characters truncated]"


def _runner_source(max_bytes: int) -> str:
    """Child entrypoint: soft memory cap (when OS allows), then run the script."""
    return (
        "import runpy\n"
        "try:\n"
        "    import resource\n"
        f"    _cap = {int(max_bytes)}\n"
        "    _soft, _hard = resource.getrlimit(resource.RLIMIT_AS)\n"
        "    if _hard != resource.RLIM_INFINITY:\n"
        "        _cap = min(_cap, _hard)\n"
        "    resource.setrlimit(resource.RLIMIT_AS, (_cap, _hard))\n"
        "except Exception:\n"
        "    pass\n"
        f"runpy.run_path({_SCRIPT_NAME!r}, run_name='__main__')\n"
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
            "files the script writes are saved for download. No network. The UI "
            "asks the user to Allow/Deny; do not ask in chat first."
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
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                # Keep caches off the output walk — matplotlib writes fontlist here.
                "HOME": str(cache),
                "TMPDIR": str(cache),
                "MPLCONFIGDIR": str(cache / "mpl"),
                "XDG_CACHE_HOME": str(cache / "xdg"),
                "LANG": os.environ.get("LANG", "en_US.UTF-8"),
                "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                # Headless charting — no display on the API host.
                "MPLBACKEND": "Agg",
            }

            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    _RUNNER_NAME,
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
            produced = sorted(
                path
                for path in cwd.rglob("*")
                if path.is_file()
                and path.name not in staged
                and _is_user_output(path, cwd)
            )
            for path in produced[:_MAX_OUTPUT_FILES]:
                try:
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
