"""Tests for the skills system."""

from pathlib import Path

from harness.skills.loader import parse_skill_md
from harness.skills.manager import SkillManager


class TestParseSkillMd:
    def test_full_frontmatter(self, tmp_path: Path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: test-skill\n"
            "description: A test skill\n"
            "allowed_tools: [Bash, Read]\n"
            "args: [message]\n"
            "user_invocable: true\n"
            "---\n"
            "Do the thing with {message}.\n"
        )
        skill = parse_skill_md(skill_file)
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert skill.allowed_tools == ["Bash", "Read"]
        assert skill.args == ["message"]
        assert skill.user_invocable is True
        assert "Do the thing with {message}." in skill.prompt

    def test_no_frontmatter(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("Just do something useful.")
        skill = parse_skill_md(skill_file)
        assert skill.name == "my-skill"
        assert skill.prompt == "Just do something useful."

    def test_minimal_frontmatter(self, tmp_path: Path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: minimal\n"
            "---\n"
            "The prompt.\n"
        )
        skill = parse_skill_md(skill_file)
        assert skill.name == "minimal"
        assert skill.description == ""
        assert skill.allowed_tools == []
        assert skill.user_invocable is True

    def test_boolean_false(self, tmp_path: Path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: hidden\n"
            "user_invocable: false\n"
            "---\n"
            "Hidden skill.\n"
        )
        skill = parse_skill_md(skill_file)
        assert skill.user_invocable is False


class TestSkillManager:
    def test_discover_from_directory(self, tmp_path: Path):
        # Create a skill directory structure
        skills_dir = tmp_path / ".harness" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\n"
            "name: my-skill\n"
            "description: A project skill\n"
            "---\n"
            "Do the thing.\n"
        )
        mgr = SkillManager(cwd=tmp_path)
        count = mgr.discover()
        assert count >= 1
        skill = mgr.get("my-skill")
        assert skill is not None
        assert skill.description == "A project skill"

    def test_list_skills(self, tmp_path: Path):
        skills_dir = tmp_path / ".harness" / "skills" / "skill-a"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: skill-a\ndescription: Skill A\n---\nDo A.\n"
        )
        skills_dir2 = tmp_path / ".harness" / "skills" / "skill-b"
        skills_dir2.mkdir(parents=True)
        (skills_dir2 / "SKILL.md").write_text(
            "---\nname: skill-b\ndescription: Skill B\n---\nDo B.\n"
        )
        mgr = SkillManager(cwd=tmp_path)
        mgr.discover()
        skills = mgr.list_skills()
        assert len(skills) >= 2
        names = {s.name for s in skills}
        assert "skill-a" in names
        assert "skill-b" in names

    def test_get_skill_prompt_with_args(self, tmp_path: Path):
        skills_dir = tmp_path / ".harness" / "skills" / "greet"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: greet\nargs: [name]\n---\nHello {name}!\n"
        )
        mgr = SkillManager(cwd=tmp_path)
        mgr.discover()
        prompt = mgr.get_skill_prompt("greet", args={"name": "World"})
        assert prompt == "Hello World!"

    def test_get_skill_summary(self, tmp_path: Path):
        skills_dir = tmp_path / ".harness" / "skills" / "test-cmd"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: test-cmd\ndescription: Run tests\nuser_invocable: true\n---\nRun tests.\n"
        )
        mgr = SkillManager(cwd=tmp_path)
        mgr.discover()
        summary = mgr.get_skill_summary()
        assert "/test-cmd" in summary
        assert "Run tests" in summary

    def test_nonexistent_skill_returns_none(self, tmp_path: Path):
        mgr = SkillManager(cwd=tmp_path)
        mgr.discover()
        assert mgr.get("nonexistent") is None
        assert mgr.get_skill_prompt("nonexistent") is None
