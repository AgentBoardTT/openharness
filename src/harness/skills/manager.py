"""Skill lifecycle management and discovery."""

from __future__ import annotations

import logging
from pathlib import Path

from harness.skills.loader import SkillDef, parse_skill_md

logger = logging.getLogger(__name__)

# Default directories to search for skills
_BUILTIN_DIR = Path(__file__).parent.parent.parent.parent / "skills"
_PROJECT_DIR_NAME = ".harness/skills"
_USER_DIR_NAME = ".harness/skills"


class SkillManager:
    """Manages skill discovery and lifecycle.

    Search order:
    1. Built-in skills (harness/skills/)
    2. User-level skills (~/.harness/skills/)
    3. Project-level skills (.harness/skills/)
    """

    def __init__(self, cwd: str | Path | None = None) -> None:
        self._skills: dict[str, SkillDef] = {}
        self._cwd = Path(cwd).resolve() if cwd else Path.cwd()

    def discover(self) -> int:
        """Discover skills from all search paths.

        Returns the number of skills found.
        """
        count = 0

        # 1. Built-in skills
        count += self._scan_dir(_BUILTIN_DIR, source="builtin")

        # 2. User-level skills
        user_dir = Path.home() / _USER_DIR_NAME
        count += self._scan_dir(user_dir, source="user")

        # 3. Project-level skills (overrides others)
        project_dir = self._cwd / _PROJECT_DIR_NAME
        count += self._scan_dir(project_dir, source="project")

        logger.info("Discovered %d skills", count)
        return count

    def _scan_dir(self, directory: Path, source: str) -> int:
        """Scan a directory for SKILL.md files."""
        if not directory.is_dir():
            return 0

        count = 0
        for skill_dir in sorted(directory.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                # Also check for SKILL.md directly in the directory
                if skill_dir.is_file() and skill_dir.name == "SKILL.md":
                    skill_file = skill_dir
                else:
                    continue
            try:
                skill = parse_skill_md(skill_file)
                self._skills[skill.name] = skill
                count += 1
                logger.debug("Loaded skill '%s' from %s (%s)", skill.name, skill_file, source)
            except Exception as exc:
                logger.warning("Failed to load skill from %s: %s", skill_file, exc)

        return count

    def get(self, name: str) -> SkillDef | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[SkillDef]:
        """List all discovered skills."""
        return list(self._skills.values())

    def list_user_invocable(self) -> list[SkillDef]:
        """List skills that can be invoked by the user (slash commands)."""
        return [s for s in self._skills.values() if s.user_invocable]

    def get_skill_prompt(self, name: str, args: dict[str, str] | None = None) -> str | None:
        """Get the expanded prompt for a skill, with argument substitution.

        Arguments are substituted as {arg_name} in the prompt template.
        """
        skill = self._skills.get(name)
        if skill is None:
            return None

        prompt = skill.prompt
        if args:
            for key, value in args.items():
                prompt = prompt.replace(f"{{{key}}}", value)

        return prompt

    def get_skill_summary(self) -> str:
        """Build a summary of available skills for the system prompt."""
        invocable = self.list_user_invocable()
        if not invocable:
            return ""

        lines = ["Available skills (invoke with /name):"]
        for skill in invocable:
            args_str = f" [{', '.join(skill.args)}]" if skill.args else ""
            lines.append(f"  /{skill.name}{args_str} — {skill.description}")

        return "\n".join(lines)
