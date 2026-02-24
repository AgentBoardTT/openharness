"""GitHubClient — httpx-based GitHub API client."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    """GitHub connection configuration."""

    token: str
    repository: str  # "owner/repo"
    api_url: str = "https://api.github.com"


def resolve_github_config() -> GitHubConfig | None:
    """Resolve GitHub config from environment variables."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        return None
    return GitHubConfig(token=token, repository=repo)


class GitHubClient:
    """Lightweight GitHub API client using httpx.

    Use as an async context manager to reuse a single connection pool::

        async with GitHubClient(config) as client:
            pr = await client.get_pr(42)
            files = await client.get_pr_files(42)

    Individual methods also work outside the context manager (they create
    a short-lived client per call for backward compatibility).
    """

    def __init__(self, config: GitHubConfig) -> None:
        self._config = config
        self._headers = {
            "Authorization": f"Bearer {config.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GitHubClient:
        self._client = httpx.AsyncClient(headers=self._headers)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        url = f"{self._config.api_url}/repos/{self._config.repository}{path}"
        hdrs = headers or self._headers
        if self._client is not None:
            resp = await self._client.get(url, headers=hdrs)
        else:
            async with httpx.AsyncClient() as c:
                resp = await c.get(url, headers=hdrs)
        resp.raise_for_status()
        return resp

    async def _post(self, path: str, json: dict[str, Any]) -> httpx.Response:
        url = f"{self._config.api_url}/repos/{self._config.repository}{path}"
        if self._client is not None:
            resp = await self._client.post(url, headers=self._headers, json=json)
        else:
            async with httpx.AsyncClient() as c:
                resp = await c.post(url, headers=self._headers, json=json)
        resp.raise_for_status()
        return resp

    async def _patch(self, path: str, json: dict[str, Any]) -> httpx.Response:
        url = f"{self._config.api_url}/repos/{self._config.repository}{path}"
        if self._client is not None:
            resp = await self._client.patch(url, headers=self._headers, json=json)
        else:
            async with httpx.AsyncClient() as c:
                resp = await c.patch(url, headers=self._headers, json=json)
        resp.raise_for_status()
        return resp

    # -- Public API -------------------------------------------------------

    async def get_pr(self, pr_number: int) -> dict[str, Any]:
        """Get a pull request."""
        resp = await self._get(f"/pulls/{pr_number}")
        return resp.json()

    async def get_pr_diff(self, pr_number: int) -> str:
        """Get the diff for a pull request."""
        headers = {**self._headers, "Accept": "application/vnd.github.diff"}
        resp = await self._get(f"/pulls/{pr_number}", headers=headers)
        return resp.text

    async def get_pr_files(self, pr_number: int) -> list[dict[str, Any]]:
        """Get files changed in a pull request."""
        resp = await self._get(f"/pulls/{pr_number}/files")
        return resp.json()

    async def create_check_run(
        self,
        name: str,
        head_sha: str,
        *,
        status: str = "in_progress",
    ) -> dict[str, Any]:
        """Create a check run."""
        resp = await self._post("/check-runs", json={
            "name": name,
            "head_sha": head_sha,
            "status": status,
        })
        return resp.json()

    async def update_check_run(
        self,
        check_run_id: int,
        *,
        status: str | None = None,
        conclusion: str | None = None,
        output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a check run."""
        data: dict[str, Any] = {}
        if status is not None:
            data["status"] = status
        if conclusion is not None:
            data["conclusion"] = conclusion
        if output is not None:
            data["output"] = output
        resp = await self._patch(f"/check-runs/{check_run_id}", json=data)
        return resp.json()

    async def create_pr_review(
        self,
        pr_number: int,
        body: str,
        *,
        event: str = "COMMENT",
    ) -> dict[str, Any]:
        """Create a pull request review."""
        resp = await self._post(
            f"/pulls/{pr_number}/reviews",
            json={"body": body, "event": event},
        )
        return resp.json()

    async def post_issue_comment(
        self, issue_number: int, body: str,
    ) -> dict[str, Any]:
        """Post a comment on an issue or PR."""
        resp = await self._post(
            f"/issues/{issue_number}/comments",
            json={"body": body},
        )
        return resp.json()
