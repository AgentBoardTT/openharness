"""Context management — token counting and compaction."""

from __future__ import annotations

import json

from harness.types.messages import CompactionEvent
from harness.types.providers import ChatMessage, ProviderAdapter

# Compaction triggers at this fraction of the context window
COMPACTION_THRESHOLD = 0.85

# After compaction, aim for this fraction of the context window
COMPACTION_TARGET = 0.50

# Minimum messages to keep (system + last user + last assistant)
MIN_MESSAGES_KEEP = 4


def estimate_message_tokens(
    msg: ChatMessage,
    provider: ProviderAdapter,
) -> int:
    """Estimate tokens for a single message."""
    if isinstance(msg.content, str):
        return provider.estimate_tokens(msg.content) + 4  # role overhead
    elif isinstance(msg.content, list):
        total = 4
        for block in msg.content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    total += provider.estimate_tokens(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    total += provider.estimate_tokens(
                        json.dumps(block.get("input", {}))
                    ) + 10
                elif block.get("type") == "tool_result":
                    total += provider.estimate_tokens(
                        str(block.get("content", ""))
                    ) + 10
                else:
                    total += provider.estimate_tokens(json.dumps(block))
        return total
    return 10


def estimate_total_tokens(
    messages: list[ChatMessage],
    system: str,
    provider: ProviderAdapter,
) -> int:
    """Estimate total token count for a message history."""
    total = provider.estimate_tokens(system) + 10  # system overhead
    for msg in messages:
        total += estimate_message_tokens(msg, provider)
    return total


def needs_compaction(
    messages: list[ChatMessage],
    system: str,
    provider: ProviderAdapter,
    context_window: int,
) -> bool:
    """Check if the message history needs compaction."""
    if len(messages) < MIN_MESSAGES_KEEP:
        return False
    total = estimate_total_tokens(messages, system, provider)
    return total > int(context_window * COMPACTION_THRESHOLD)


def _find_safe_boundary(messages: list[ChatMessage], target_idx: int) -> int:
    """Find a safe boundary to split messages.

    Avoids splitting in the middle of a tool_use/tool_result pair.
    Returns the index of the first message to keep.
    """
    idx = target_idx

    # Walk forward to find a clean boundary (user message that isn't a tool result)
    while idx < len(messages) - MIN_MESSAGES_KEEP:
        msg = messages[idx]
        if msg.role == "user":
            # Check it's not a tool result
            if isinstance(msg.content, str):
                return idx
            if isinstance(msg.content, list):
                has_tool_result = any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in msg.content
                )
                if not has_tool_result:
                    return idx
        idx += 1

    # Fallback: keep last MIN_MESSAGES_KEEP messages
    return max(0, len(messages) - MIN_MESSAGES_KEEP)


def compact_messages(
    messages: list[ChatMessage],
    system: str,
    provider: ProviderAdapter,
    context_window: int,
) -> tuple[list[ChatMessage], CompactionEvent]:
    """Compact messages by summarizing older ones.

    Strategy:
    1. Calculate how many tokens to remove to reach the target
    2. Find a safe boundary point in the message history
    3. Summarize everything before the boundary into a single message
    4. Return the compacted messages + a CompactionEvent

    Returns:
        Tuple of (compacted_messages, compaction_event)
    """
    tokens_before = estimate_total_tokens(messages, system, provider)
    target_tokens = int(context_window * COMPACTION_TARGET)
    tokens_to_remove = tokens_before - target_tokens

    if tokens_to_remove <= 0:
        return messages, CompactionEvent(
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            summary="No compaction needed.",
        )

    # Find how many messages to summarize
    running_tokens = 0
    split_idx = 0
    for i, msg in enumerate(messages):
        running_tokens += estimate_message_tokens(msg, provider)
        if running_tokens >= tokens_to_remove:
            split_idx = i + 1
            break

    # Find safe boundary
    split_idx = _find_safe_boundary(messages, split_idx)

    if split_idx == 0:
        return messages, CompactionEvent(
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            summary="Cannot compact further.",
        )

    # Build summary of compacted messages
    old_messages = messages[:split_idx]
    kept_messages = messages[split_idx:]

    summary = _build_summary(old_messages)

    # Create summary message
    summary_msg = ChatMessage(
        role="user",
        content=(
            f"[Context Summary — {len(old_messages)} earlier messages compacted]\n\n"
            f"{summary}\n\n"
            "[End of summary. The conversation continues below.]"
        ),
    )

    compacted = [summary_msg] + kept_messages
    tokens_after = estimate_total_tokens(compacted, system, provider)

    return compacted, CompactionEvent(
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        summary=summary,
    )


def _build_summary(messages: list[ChatMessage]) -> str:
    """Build a text summary of a list of messages.

    This is a simple extractive summary. A production system would
    use the LLM itself to summarize, but that requires an API call
    and adds complexity. This approach is fast and deterministic.
    """
    parts: list[str] = []
    tool_calls: list[str] = []
    files_mentioned: set[str] = set()

    for msg in messages:
        if isinstance(msg.content, str):
            text = msg.content
            if msg.role == "user" and len(text) > 200:
                parts.append(f"User asked: {text[:200]}...")
            elif msg.role == "assistant" and len(text) > 200:
                parts.append(f"Assistant replied: {text[:200]}...")
        elif isinstance(msg.content, list):
            for block in msg.content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    name = block.get("name", "unknown")
                    args = block.get("input", {})
                    tool_calls.append(name)
                    if "file_path" in args:
                        files_mentioned.add(args["file_path"])
                    elif "command" in args:
                        cmd = args["command"]
                        if len(cmd) > 80:
                            cmd = cmd[:80] + "..."
                        tool_calls.append(f"  $ {cmd}")
                elif block.get("type") == "text":
                    text = block.get("text", "")
                    if text and len(text) > 100:
                        parts.append(text[:100] + "...")

    summary_lines = []
    if parts:
        summary_lines.append("Conversation included:")
        for p in parts[:10]:  # Cap at 10 entries
            summary_lines.append(f"  - {p}")

    if tool_calls:
        unique_tools = sorted(set(tool_calls))
        summary_lines.append(
            f"Tools used: {', '.join(unique_tools[:20])}"
        )

    if files_mentioned:
        summary_lines.append(
            f"Files referenced: {', '.join(sorted(files_mentioned)[:20])}"
        )

    if not summary_lines:
        summary_lines.append(
            f"({len(messages)} messages were exchanged.)"
        )

    return "\n".join(summary_lines)
