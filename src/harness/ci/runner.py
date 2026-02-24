"""CI runner entry point."""

from __future__ import annotations

from typing import Any

from harness.ci.config import load_ci_config
from harness.ci.github import GitHubClient, resolve_github_config
from harness.ci.reporter import StatusReporter
from harness.ci.webhook import WebhookEventType, parse_github_event


async def run_ci(
    *,
    mode: str | None = None,
    prompt: str | None = None,
    provider: str = "anthropic",
    model: str | None = None,
    sandbox: str = "process",
    check_name: str = "harness-agent",
) -> dict[str, Any]:
    """Run the CI agent.

    Auto-detects mode from GitHub webhook event if not specified.

    Returns a result dict with status and summary.
    """
    from harness.core.engine import run
    from harness.types.messages import Result, TextMessage

    # Load CI config — provides defaults for unspecified parameters
    ci_config = load_ci_config()

    # Apply config defaults for parameters not explicitly passed
    resolved_provider = provider or ci_config.provider
    resolved_model = model or ci_config.model
    resolved_check_name = check_name or ci_config.check_name
    resolved_max_turns = ci_config.max_turns
    resolved_permission_mode = ci_config.permission_mode

    # Parse webhook event
    event_type, event_payload = parse_github_event()

    # Auto-detect mode
    if mode is None:
        if event_type in (
            WebhookEventType.PR_OPENED,
            WebhookEventType.PR_SYNCHRONIZE,
            WebhookEventType.PR_REOPENED,
        ):
            mode = "review"
        elif event_type == WebhookEventType.ISSUE_OPENED:
            mode = "issue"
        else:
            mode = "general"

    # Build prompt from event
    if prompt is None:
        prompt = _build_prompt(mode, event_type, event_payload)

    # Set up GitHub reporting
    gh_config = resolve_github_config()
    reporter: StatusReporter | None = None
    if gh_config:
        client = GitHubClient(gh_config)
        reporter = StatusReporter(client, check_name=resolved_check_name)

        head_sha = _extract_sha(event_payload)
        if head_sha:
            await reporter.start(head_sha)

    # Run agent
    final_text = ""
    result_data: dict[str, Any] = {"status": "success"}
    try:
        async for msg in run(
            prompt,
            provider=resolved_provider,
            model=resolved_model,
            max_turns=resolved_max_turns,
            permission_mode=resolved_permission_mode,
        ):
            if isinstance(msg, TextMessage) and not msg.is_partial:
                final_text = msg.text
            elif isinstance(msg, Result):
                result_data["turns"] = msg.turns
                result_data["tool_calls"] = msg.tool_calls
                result_data["total_tokens"] = msg.total_tokens

        result_data["summary"] = final_text

        if reporter:
            await reporter.complete(summary=final_text)

    except Exception as e:
        result_data["status"] = "failure"
        result_data["error"] = str(e)
        if reporter:
            await reporter.fail(summary=f"Error: {e}")

    return result_data


def _build_prompt(
    mode: str, event_type: WebhookEventType, payload: dict[str, Any],
) -> str:
    """Build an agent prompt from the CI event."""
    if mode == "review":
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number", "")
        pr_title = pr.get("title", "")
        pr_body = pr.get("body", "")
        return (
            f"Review pull request #{pr_number}: {pr_title}\n\n"
            f"Description:\n{pr_body}\n\n"
            "Provide a thorough code review with actionable feedback."
        )

    if mode == "issue":
        issue = payload.get("issue", {})
        issue_number = issue.get("number", "")
        issue_title = issue.get("title", "")
        issue_body = issue.get("body", "")
        return (
            f"Analyze issue #{issue_number}: {issue_title}\n\n"
            f"Description:\n{issue_body}\n\n"
            "Suggest implementation approaches and identify affected files."
        )

    return "Analyze the latest changes and provide a summary."


def _extract_sha(payload: dict[str, Any]) -> str:
    """Extract the head SHA from the event payload."""
    # PR events
    pr = payload.get("pull_request", {})
    head = pr.get("head", {})
    sha = head.get("sha", "")
    if sha:
        return sha

    # Push events
    return payload.get("after", "")
