"""Discovery and loading of SKILL.md files.

The format matches the one Claude Code, Cursor, and other Agent Skills hosts
use — YAML frontmatter with `name` and `description`, then a markdown body — so
a directory of skills written for those tools works here unchanged.

Progressive disclosure is the whole point: the agent sees only the index at
startup and pays for a skill's body only when it reads one.
"""

from pathlib import Path

import yaml

from agent_console.models.skills import Skill

__all__ = ["SkillRepository", "UnknownSkillError"]

_FRONTMATTER_FENCE = "---"


class UnknownSkillError(LookupError):
    """No loaded skill matches the given name."""


def _parse_skill_file(path: Path) -> tuple[dict, str]:
    """Split a SKILL.md into its frontmatter mapping and its body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith(_FRONTMATTER_FENCE):
        return {}, text

    # Split on the closing fence only, so `---` inside the body survives.
    _, _, remainder = text.partition(_FRONTMATTER_FENCE)
    raw_frontmatter, fence, body = remainder.partition(f"\n{_FRONTMATTER_FENCE}")
    if not fence:
        return {}, text

    try:
        metadata = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(metadata, dict):
        return {}, text
    return metadata, body.lstrip("\n")


class SkillRepository:
    """Loads skills from one or more directories of `<name>/SKILL.md`.

    Every loaded skill costs its description in the system prompt on every
    request, so `allowlist` exists to let a large shared library be mined for a
    handful of relevant skills rather than loaded wholesale.
    """

    def __init__(self, directories: list[Path], allowlist: set[str] | None = None) -> None:
        self._directories = directories
        self._allowlist = allowlist or None
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        """Rescan the configured directories. Later directories win on name clashes."""
        found: dict[str, Skill] = {}
        for directory in self._directories:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*/SKILL.md")):
                metadata, _ = _parse_skill_file(path)
                name = str(metadata.get("name") or path.parent.name)
                if self._allowlist is not None and name not in self._allowlist:
                    continue
                description = str(metadata.get("description") or "").strip()
                if not description:
                    # Without a description the model has no basis for choosing
                    # it, so an unlabelled skill is worse than no skill.
                    continue
                found[name] = Skill(name=name, description=description, path=path)
        self._skills = found

    def list(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda skill: skill.name)

    def index(self) -> str:
        """The name+description block that goes into the system prompt."""
        return "\n".join(skill.index_line() for skill in self.list())

    def read(self, name: str, max_chars: int | None = None) -> str:
        """One skill's markdown body, capped.

        Shared skill libraries contain some very long files, and a skill body
        stays in the conversation for every step that follows it. An uncapped
        read can therefore cost more context than the task it was meant to help.
        """
        skill = self._skills.get(name)
        if skill is None:
            available = ", ".join(self._skills) or "none"
            raise UnknownSkillError(f"no skill named {name!r}. Available: {available}")

        _, body = _parse_skill_file(skill.path)
        if max_chars is None or len(body) <= max_chars:
            return body
        return (
            body[:max_chars]
            + f"\n\n[skill truncated at {max_chars} of {len(body)} characters]"
        )
