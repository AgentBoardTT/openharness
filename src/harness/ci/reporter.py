"""StatusReporter — GitHub check run management."""

from __future__ import annotations

from typing import Any

from harness.ci.github import GitHubClient


class StatusReporter:
    """Manages a GitHub check run lifecycle."""

    def __init__(self, client: GitHubClient, check_name: str = "harness-agent") -> None:
        self._client = client
        self._check_name = check_name
        self._check_run_id: int | None = None

    @property
    def check_run_id(self) -> int | None:
        return self._check_run_id

    async def start(self, head_sha: str) -> int:
        """Create an in-progress check run. Returns the check run ID."""
        result = await self._client.create_check_run(
            name=self._check_name,
            head_sha=head_sha,
            status="in_progress",
        )
        self._check_run_id = result["id"]
        return self._check_run_id

    async def complete(
        self,
        *,
        conclusion: str = "success",
        title: str = "Harness Agent",
        summary: str = "",
    ) -> None:
        """Complete the check run with a conclusion."""
        if self._check_run_id is None:
            return

        output: dict[str, Any] = {"title": title, "summary": summary}

        await self._client.update_check_run(
            self._check_run_id,
            status="completed",
            conclusion=conclusion,
            output=output,
        )

    async def fail(self, *, title: str = "Harness Agent", summary: str = "") -> None:
        """Mark the check run as failed."""
        await self.complete(conclusion="failure", title=title, summary=summary)
