"""Basic text output for non-interactive mode."""

from __future__ import annotations

import sys

from harness.types.messages import (
    CompactionEvent,
    Message,
    Result,
    SystemEvent,
    TextMessage,
    ToolResult,
    ToolUse,
)


def print_message(msg: Message) -> None:
    """Print a message to stdout in basic text mode."""
    match msg:
        case TextMessage(text=t, is_partial=True):
            sys.stdout.write(t)
            sys.stdout.flush()
        case TextMessage(text=_, is_partial=False):
            pass  # Full text already printed via partials
        case ToolUse(name=name, args=args):
            tool_display = f"\n[Tool: {name}]"
            if name == "Bash" and "command" in args:
                tool_display += f" $ {args['command']}"
            elif name in ("Read", "Write", "Edit") and "file_path" in args:
                tool_display += f" {args['file_path']}"
            elif name == "Glob" and "pattern" in args:
                tool_display += f" {args['pattern']}"
            elif name == "Grep" and "pattern" in args:
                tool_display += f" /{args['pattern']}/"
            print(tool_display, file=sys.stderr)
        case ToolResult(content=content, is_error=is_error):
            if is_error:
                print(f"[Error] {content[:200]}", file=sys.stderr)
            elif len(content) > 200:
                print(f"[Result] {content[:200]}...", file=sys.stderr)
        case Result(
            text=_, session_id=sid, turns=turns,
            tool_calls=tc, total_tokens=tokens, total_cost=cost,
        ):
            print(file=sys.stderr)
            parts = [f"Session: {sid}", f"Turns: {turns}", f"Tools: {tc}"]
            if tokens:
                parts.append(f"Tokens: {tokens:,}")
            if cost:
                parts.append(f"Cost: ${cost:.4f}")
            print(" | ".join(parts), file=sys.stderr)
        case CompactionEvent(tokens_before=before, tokens_after=after):
            print(f"\n[Compacted: {before:,} -> {after:,} tokens]", file=sys.stderr)
        case SystemEvent(type=t):
            pass  # Suppress system events in basic output
