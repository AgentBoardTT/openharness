"""Tests for CLI subcommands."""

from __future__ import annotations

from click.testing import CliRunner

from harness.cli.main import cli


class TestModelsCommand:
    def test_models_list(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["models", "list"])
        assert result.exit_code == 0
        assert "claude-sonnet-4-6" in result.output
        assert "gpt-4o" in result.output
        assert "gemini-2.0-flash" in result.output

    def test_models_list_filter(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["models", "list", "-p", "anthropic"])
        assert result.exit_code == 0
        assert "claude" in result.output
        assert "gpt-4o" not in result.output

    def test_models_info(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["models", "info", "sonnet"])
        assert result.exit_code == 0
        assert "claude-sonnet-4-6" in result.output
        assert "200,000" in result.output

    def test_models_info_unknown(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["models", "info", "nonexistent"])
        assert result.exit_code == 1


class TestSessionsCommand:
    def test_sessions_list(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["sessions", "list"])
        assert result.exit_code == 0


class TestConfigCommand:
    def test_config_list(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "list"])
        assert result.exit_code == 0
        assert "Environment:" in result.output
        assert "TOML config:" in result.output
