"""Tests for the memory system."""

from pathlib import Path

import pytest

from harness.memory.auto import AutoMemory
from harness.memory.project import load_project_instructions


class TestProjectInstructions:
    def test_load_harness_md(self, tmp_path: Path):
        (tmp_path / "HARNESS.md").write_text("Always use uv.\n")
        content = load_project_instructions(tmp_path)
        assert content == "Always use uv."

    def test_load_dot_harness_md(self, tmp_path: Path):
        (tmp_path / ".harness.md").write_text("Hidden config.\n")
        content = load_project_instructions(tmp_path)
        assert content == "Hidden config."

    def test_no_file_returns_none(self, tmp_path: Path):
        content = load_project_instructions(tmp_path)
        assert content is None

    def test_walks_up_to_parent(self, tmp_path: Path):
        (tmp_path / "HARNESS.md").write_text("Project root.\n")
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)
        content = load_project_instructions(subdir)
        assert content == "Project root."

    def test_stops_at_git_root(self, tmp_path: Path):
        # Create a .git directory to stop walking
        (tmp_path / ".git").mkdir()
        (tmp_path / "HARNESS.md").write_text("Git root.\n")
        subdir = tmp_path / "src"
        subdir.mkdir()
        content = load_project_instructions(subdir)
        # Should find it in parent (tmp_path) since .git stops the walk there
        assert content == "Git root."


class TestAutoMemory:
    def test_save_and_load(self, tmp_path: Path):
        mem = AutoMemory(cwd=tmp_path)
        mem.save("test_key", {"value": 42})
        result = mem.load("test_key")
        assert result == {"value": 42}

    def test_load_missing_returns_none(self, tmp_path: Path):
        mem = AutoMemory(cwd=tmp_path)
        assert mem.load("nonexistent") is None

    def test_delete(self, tmp_path: Path):
        mem = AutoMemory(cwd=tmp_path)
        mem.save("to_delete", "temporary")
        assert mem.load("to_delete") == "temporary"
        assert mem.delete("to_delete") is True
        assert mem.load("to_delete") is None

    def test_delete_missing_returns_false(self, tmp_path: Path):
        mem = AutoMemory(cwd=tmp_path)
        assert mem.delete("nonexistent") is False

    def test_list_keys(self, tmp_path: Path):
        mem = AutoMemory(cwd=tmp_path)
        mem.save("alpha", 1)
        mem.save("beta", 2)
        keys = mem.list_keys()
        assert "alpha" in keys
        assert "beta" in keys

    def test_project_overrides_user(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Use a fake home to avoid polluting real ~/.harness/memory/
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        mem = AutoMemory(cwd=tmp_path)
        mem.save("shared", "project_value", scope="project")
        mem.save("shared", "user_value", scope="user")
        # Project-level takes precedence
        result = mem.load("shared")
        assert result == "project_value"

    def test_context_summary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        mem = AutoMemory(cwd=tmp_path)
        mem.save("pref", "always use uv")
        summary = mem.get_context_summary()
        assert "pref" in summary
        assert "always use uv" in summary

    def test_empty_summary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        mem = AutoMemory(cwd=tmp_path)
        assert mem.get_context_summary() == ""
