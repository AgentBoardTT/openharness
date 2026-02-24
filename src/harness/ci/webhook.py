"""GitHub webhook event parsing."""

from __future__ import annotations

import json
import os
from enum import Enum
from typing import Any


class WebhookEventType(Enum):
    """Supported GitHub webhook event types."""

    PR_OPENED = "pull_request.opened"
    PR_SYNCHRONIZE = "pull_request.synchronize"
    PR_REOPENED = "pull_request.reopened"
    ISSUE_OPENED = "issues.opened"
    ISSUE_COMMENT = "issue_comment.created"
    PUSH = "push"
    UNKNOWN = "unknown"


def parse_github_event() -> tuple[WebhookEventType, dict[str, Any]]:
    """Parse a GitHub Actions webhook event.

    Reads from GITHUB_EVENT_NAME and GITHUB_EVENT_PATH environment variables.
    Returns (event_type, event_payload).
    """
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")

    payload: dict[str, Any] = {}
    if event_path and os.path.exists(event_path):
        with open(event_path) as f:
            payload = json.load(f)

    action = payload.get("action", "")
    full_event = f"{event_name}.{action}" if action else event_name

    type_map: dict[str, WebhookEventType] = {
        "pull_request.opened": WebhookEventType.PR_OPENED,
        "pull_request.synchronize": WebhookEventType.PR_SYNCHRONIZE,
        "pull_request.reopened": WebhookEventType.PR_REOPENED,
        "issues.opened": WebhookEventType.ISSUE_OPENED,
        "issue_comment.created": WebhookEventType.ISSUE_COMMENT,
        "push": WebhookEventType.PUSH,
    }

    event_type = type_map.get(full_event, WebhookEventType.UNKNOWN)
    return event_type, payload
