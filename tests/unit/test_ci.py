"""Tests for the CI/CD module."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.ci.webhook import WebhookEventType, parse_github_event
from harness.ci.config import CIConfig, load_ci_config, generate_ci_template
from harness.ci.github import GitHubClient, GitHubConfig, resolve_github_config
from harness.ci.reporter import StatusReporter


# ---------------------------------------------------------------------------
# Webhook parsing tests
# ---------------------------------------------------------------------------


class TestWebhookParsing:
    def test_parse_pr_opened(self, tmp_path: Path) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps({
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Fix bug",
                "body": "This fixes the bug",
                "head": {"sha": "abc123"},
            },
        }))

        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event_file),
        }):
            event_type, payload = parse_github_event()
            assert event_type == WebhookEventType.PR_OPENED
            assert payload["pull_request"]["number"] == 42

    def test_parse_issue_opened(self, tmp_path: Path) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps({
            "action": "opened",
            "issue": {"number": 10, "title": "New feature"},
        }))

        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "issues",
            "GITHUB_EVENT_PATH": str(event_file),
        }):
            event_type, payload = parse_github_event()
            assert event_type == WebhookEventType.ISSUE_OPENED

    def test_parse_push(self, tmp_path: Path) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps({"after": "def456"}))

        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_EVENT_PATH": str(event_file),
        }):
            event_type, payload = parse_github_event()
            assert event_type == WebhookEventType.PUSH

    def test_parse_unknown_event(self) -> None:
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "deployment",
            "GITHUB_EVENT_PATH": "",
        }):
            event_type, _ = parse_github_event()
            assert event_type == WebhookEventType.UNKNOWN

    def test_missing_event_file(self) -> None:
        with patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_EVENT_PATH": "/nonexistent/path.json",
        }):
            event_type, payload = parse_github_event()
            assert payload == {}


# ---------------------------------------------------------------------------
# GitHub config resolution tests
# ---------------------------------------------------------------------------


class TestGitHubConfig:
    def test_resolves_from_env(self) -> None:
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "ghp_test123",
            "GITHUB_REPOSITORY": "owner/repo",
        }):
            config = resolve_github_config()
            assert config is not None
            assert config.token == "ghp_test123"
            assert config.repository == "owner/repo"

    def test_returns_none_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = resolve_github_config()
            assert config is None


# ---------------------------------------------------------------------------
# GitHubClient tests (mocked httpx)
# ---------------------------------------------------------------------------


class TestGitHubClient:
    def _make_client(self) -> GitHubClient:
        return GitHubClient(GitHubConfig(
            token="test-token",
            repository="owner/repo",
        ))

    @pytest.mark.asyncio
    async def test_get_pr(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"number": 1, "title": "Test PR"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_response),
            ))
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_pr(1)
            assert result["number"] == 1

    @pytest.mark.asyncio
    async def test_post_issue_comment(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 123}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=mock_response),
            ))
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.post_issue_comment(1, "Test comment")
            assert result["id"] == 123


# ---------------------------------------------------------------------------
# StatusReporter tests
# ---------------------------------------------------------------------------


class TestStatusReporter:
    @pytest.mark.asyncio
    async def test_start_creates_check_run(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_check_run = AsyncMock(return_value={"id": 999})
        mock_client.update_check_run = AsyncMock(return_value={})

        reporter = StatusReporter(mock_client, check_name="test-check")
        check_id = await reporter.start("abc123")
        assert check_id == 999
        assert reporter.check_run_id == 999

    @pytest.mark.asyncio
    async def test_complete_updates_check_run(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_check_run = AsyncMock(return_value={"id": 999})
        mock_client.update_check_run = AsyncMock(return_value={})

        reporter = StatusReporter(mock_client)
        await reporter.start("abc123")
        await reporter.complete(summary="All good")

        mock_client.update_check_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_marks_failure(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_check_run = AsyncMock(return_value={"id": 999})
        mock_client.update_check_run = AsyncMock(return_value={})

        reporter = StatusReporter(mock_client)
        await reporter.start("abc123")
        await reporter.fail(summary="Something broke")

        call_kwargs = mock_client.update_check_run.call_args
        assert call_kwargs.kwargs.get("conclusion") == "failure" or \
               (len(call_kwargs.args) > 0 and "failure" in str(call_kwargs))


# ---------------------------------------------------------------------------
# CI Config tests
# ---------------------------------------------------------------------------


class TestCIConfig:
    def test_default_config(self) -> None:
        config = CIConfig()
        assert "pull_request" in config.triggers
        assert config.provider == "anthropic"
        assert config.sandbox == "process"

    def test_load_yaml_config(self, tmp_path: Path) -> None:
        harness_dir = tmp_path / ".harness"
        harness_dir.mkdir()
        ci_file = harness_dir / "ci.yml"
        ci_file.write_text("""
triggers:
  - pull_request
provider: openai
model: gpt-4o
sandbox: docker
check_name: custom-check
max_turns: 25
""")
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("pyyaml not installed")

        config = load_ci_config(str(tmp_path))
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.sandbox == "docker"
        assert config.check_name == "custom-check"
        assert config.max_turns == 25

    def test_missing_config_returns_defaults(self) -> None:
        config = load_ci_config("/nonexistent/path")
        assert isinstance(config, CIConfig)
        assert config.provider == "anthropic"

    def test_generate_template(self) -> None:
        template = generate_ci_template()
        assert "triggers" in template
        assert "provider" in template
        assert "sandbox" in template
