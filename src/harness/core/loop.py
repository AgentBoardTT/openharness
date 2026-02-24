"""The core agent loop — orchestrates provider + tools."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from harness.core.context import compact_messages, needs_compaction
from harness.core.session import Session
from harness.permissions.rules import PermissionDecision
from harness.types.config import RunConfig
from harness.types.hooks import HookEvent
from harness.types.messages import (
    Message,
    Result,
    SystemEvent,
    TextMessage,
    ToolResult,
    ToolUse,
)
from harness.types.providers import ChatMessage, ProviderAdapter, StreamEvent
from harness.types.tools import ToolContext, ToolResultData

SYSTEM_PROMPT = """\
You are Harness, an expert software engineering assistant.

You have tools to read, write, and edit files, run shell commands, search codebases, and \
browse the web. Use them proactively to accomplish the user's request.

IMPORTANT: Be action-oriented. When the user asks you to build, fix, or change something, \
start doing it immediately using your tools. Do NOT ask clarifying questions unless the \
request is genuinely ambiguous and you cannot make a reasonable default choice. Prefer \
making sensible decisions and executing over asking for permission or preferences. If the \
user doesn't specify details, choose good defaults and proceed.

Be concise in your text responses. Let your tool calls and code do the talking.

Working directory: {cwd}
"""


class AgentLoop:
    """The core agent loop.

    Orchestrates: user prompt -> model -> tool calls -> model -> ... -> final response.
    """

    def __init__(
        self,
        provider: ProviderAdapter,
        tools: dict[str, Any],  # name -> tool with execute() and definition
        config: RunConfig,
        session: Session,
        context_window: int = 200_000,
        permission_manager: Any | None = None,
        mcp_manager: Any | None = None,
        hook_manager: Any | None = None,
        steering: Any | None = None,
        approval_callback: Any | None = None,
        audit_logger: Any | None = None,
        sandbox_executor: Any | None = None,
    ):
        self._provider = provider
        self._tools = tools
        self._config = config
        self._session = session
        self._cwd = Path(config.cwd or ".").resolve()
        self._tool_defs = [t.definition for t in tools.values()]
        # Only format the bare SYSTEM_PROMPT constant. If config.system_prompt
        # is set it was already formatted by engine.py and may contain literal
        # braces from HARNESS.md or skill summaries.
        if config.system_prompt:
            self._system = config.system_prompt
        else:
            self._system = SYSTEM_PROMPT.format(cwd=str(self._cwd))
        self._context_window = context_window
        self._permission_manager = permission_manager
        self._mcp_manager = mcp_manager
        self._hook_manager = hook_manager
        self._steering = steering
        self._approval_callback = approval_callback
        self._audit_logger = audit_logger
        self._sandbox_executor = sandbox_executor

        # Add MCP tool definitions if available
        if self._mcp_manager is not None:
            try:
                mcp_defs = self._mcp_manager.get_tool_defs()
                self._tool_defs.extend(mcp_defs)
            except (AttributeError, Exception):
                pass

    async def run(self, user_message: str) -> AsyncIterator[Message]:
        """Run the agent loop for a user message. Yields Message events."""
        # Add user message to session
        user_msg = ChatMessage(role="user", content=user_message)
        self._session.add_message(user_msg)

        yield SystemEvent(type="session_start", data={"session_id": self._session.session_id})

        messages = self._session.messages
        turn = 0
        total_tokens = 0
        total_cost = 0.0
        tool_call_count = 0
        final_text = ""

        while turn < self._config.max_turns:
            turn += 1

            # Check for steering messages between turns
            steering_msg = await self._check_steering()
            if steering_msg:
                steer = ChatMessage(role="user", content=steering_msg)
                self._session.add_message(steer)
                messages.append(steer)

            # Check for context compaction
            if needs_compaction(
                messages, self._system,
                self._provider, self._context_window,
            ):
                messages, event = compact_messages(
                    messages, self._system,
                    self._provider, self._context_window,
                )
                self._session.set_messages(messages)
                yield event

            # Call provider
            accumulated_text = ""
            tool_uses: list[dict[str, Any]] = []
            current_tool: dict[str, Any] | None = None
            stop_reason = "end_turn"
            turn_tokens = 0
            turn_input_tokens = 0
            turn_output_tokens = 0

            async for event in self._provider.chat_completion_stream(
                messages=messages,
                tools=self._tool_defs,
                system=self._system,
                max_tokens=self._config.max_tokens,
            ):
                event: StreamEvent
                if event.type == "text_delta" and event.text:
                    accumulated_text += event.text
                    yield TextMessage(text=event.text, is_partial=True)

                elif event.type == "tool_use_start":
                    current_tool = {
                        "id": event.tool_use_id or "",
                        "name": event.tool_name or "",
                        "args_json": "",
                    }

                elif event.type == "tool_use_delta" and current_tool is not None:
                    current_tool["args_json"] += event.tool_args_json or ""

                elif event.type == "tool_use_end" and current_tool is not None:
                    try:
                        raw = current_tool["args_json"]
                        args = json.loads(raw) if raw else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_uses.append({
                        "id": current_tool["id"],
                        "name": current_tool["name"],
                        "args": args,
                    })
                    current_tool = None

                elif event.type == "message_end":
                    stop_reason = event.stop_reason or "end_turn"
                    if event.usage:
                        turn_input_tokens = event.usage.get("input_tokens", 0)
                        turn_output_tokens = event.usage.get("output_tokens", 0)
                        turn_tokens = turn_input_tokens + turn_output_tokens

            # Emit final text if any
            if accumulated_text:
                yield TextMessage(text=accumulated_text, is_partial=False)
                final_text = accumulated_text

            # Build assistant message content
            assistant_content: list[dict[str, Any]] = []
            if accumulated_text:
                assistant_content.append({"type": "text", "text": accumulated_text})
            for tu in tool_uses:
                block = self._provider.format_tool_use(
                    tu["id"], tu["name"], tu["args"],
                )
                assistant_content.append(block)

            if assistant_content:
                assistant_msg = ChatMessage(role="assistant", content=assistant_content)
                self._session.add_message(assistant_msg)
                messages.append(assistant_msg)

            # Calculate cost using actual input/output token counts
            model_info = getattr(self._provider, '_model_info', None)
            turn_cost = 0.0
            if model_info and hasattr(model_info, 'input_cost_per_mtok'):
                in_cost = turn_input_tokens * model_info.input_cost_per_mtok
                out_cost = turn_output_tokens * model_info.output_cost_per_mtok
                turn_cost = (in_cost + out_cost) / 1_000_000

            total_tokens += turn_tokens
            total_cost += turn_cost
            self._session.record_turn(tokens=turn_tokens, cost=turn_cost)

            # Audit: log provider call
            if self._audit_logger:
                self._audit_logger.log_provider_call(
                    self._config.provider,
                    self._provider.model_id,
                    input_tokens=turn_input_tokens,
                    output_tokens=turn_output_tokens,
                    cost=turn_cost,
                )

            # OTel: record metrics
            try:
                from harness.observability.metrics import record_tokens, record_cost
                record_tokens(
                    turn_input_tokens, turn_output_tokens,
                    provider=self._config.provider,
                    model=self._provider.model_id,
                )
                if turn_cost > 0:
                    record_cost(
                        turn_cost,
                        provider=self._config.provider,
                        model=self._provider.model_id,
                    )
            except ImportError:
                pass

            # If no tool calls, we're done
            if stop_reason != "tool_use" or not tool_uses:
                break

            # Execute tool calls
            tool_result_contents: list[dict[str, Any]] = []
            for tu in tool_uses:
                tool_call_count += 1

                # Safe default in case tool execution is interrupted
                result = ToolResultData(content="Tool execution failed.", is_error=True)

                # Check permissions before executing
                decision = self._check_permission(tu["name"], tu["args"])

                # Audit: log permission decision
                if self._audit_logger:
                    self._audit_logger.log_permission_decision(
                        tu["name"], decision.value, self._config.permission_mode.value,
                    )

                if decision == PermissionDecision.DENY:
                    yield ToolUse(id=tu["id"], name=tu["name"], args=tu["args"])
                    result = ToolResultData(
                        content=f"Permission denied: {tu['name']} is not allowed "
                        f"in {self._config.permission_mode.value} mode.",
                        is_error=True,
                    )
                    yield ToolResult(
                        tool_use_id=tu["id"],
                        content=result.content,
                        is_error=True,
                    )

                elif decision == PermissionDecision.ASK:
                    approved = await self._request_approval(tu["name"], tu["args"])
                    if approved:
                        async for msg in self._execute_and_yield_tool(tu):
                            yield msg
                            if isinstance(msg, ToolResult):
                                result = ToolResultData(
                                    content=msg.content,
                                    is_error=msg.is_error,
                                )
                    else:
                        yield ToolUse(id=tu["id"], name=tu["name"], args=tu["args"])
                        result = ToolResultData(
                            content=f"Tool call {tu['name']} was denied by user.",
                            is_error=True,
                        )
                        yield ToolResult(
                            tool_use_id=tu["id"],
                            content=result.content,
                            is_error=True,
                        )

                else:  # ALLOW
                    async for msg in self._execute_and_yield_tool(tu):
                        yield msg
                        if isinstance(msg, ToolResult):
                            result = ToolResultData(
                                content=msg.content,
                                is_error=msg.is_error,
                            )

                tool_result_msg = self._provider.format_tool_result(
                    tu["id"], result.content, result.is_error,
                )
                tool_result_contents.append({
                    "role": tool_result_msg.role,
                    "content": tool_result_msg.content,
                    "tool_use_id": tu["id"],
                })

            # Add tool results as user messages
            for trc in tool_result_contents:
                msg = ChatMessage(
                    role=trc["role"],
                    content=trc["content"],
                    tool_use_id=trc.get("tool_use_id"),
                )
                self._session.add_message(msg)
                messages.append(msg)

        # Yield final result
        yield Result(
            text=final_text,
            session_id=self._session.session_id,
            turns=turn,
            tool_calls=tool_call_count,
            total_tokens=total_tokens,
            total_cost=total_cost,
            stop_reason=stop_reason if turn < self._config.max_turns else "max_turns",
        )

    async def _execute_and_yield_tool(
        self, tu: dict[str, Any],
    ) -> AsyncIterator[Message]:
        """Execute a tool call and yield ToolUse + ToolResult messages."""
        yield ToolUse(id=tu["id"], name=tu["name"], args=tu["args"])

        # Audit: log tool call
        if self._audit_logger:
            self._audit_logger.log_tool_call(tu["name"], tu["args"])

        await self._fire_hook(
            HookEvent.PRE_TOOL_USE,
            tool_name=tu["name"],
            tool_args=tu["args"],
        )

        result = await self._execute_tool(tu["name"], tu["args"])

        await self._fire_hook(
            HookEvent.POST_TOOL_USE,
            tool_name=tu["name"],
            tool_args=tu["args"],
            result=result.content,
            is_error=result.is_error,
        )

        # Audit: log tool result
        if self._audit_logger:
            self._audit_logger.log_tool_result(
                tu["name"], is_error=result.is_error,
                content_length=len(result.content),
            )

        # OTel: record tool call metric
        try:
            from harness.observability.metrics import record_tool_call
            record_tool_call(tu["name"], is_error=result.is_error)
        except ImportError:
            pass

        yield ToolResult(
            tool_use_id=tu["id"],
            content=result.content,
            is_error=result.is_error,
            display=result.display,
        )

    async def _request_approval(
        self, tool_name: str, args: dict[str, Any],
    ) -> bool:
        """Request user approval for a tool call. Returns True if approved."""
        if self._approval_callback is None:
            return False
        from harness.permissions.approval import describe_tool_call
        description = describe_tool_call(tool_name, args)
        try:
            return await self._approval_callback.request_approval(
                tool_name, args, description,
            )
        except Exception:
            return False

    def _check_permission(self, tool_name: str, args: dict[str, Any]) -> PermissionDecision:
        """Check permission for a tool call."""
        if self._permission_manager is None:
            return PermissionDecision.ALLOW
        return self._permission_manager.check(tool_name, args)

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> ToolResultData:
        """Execute a tool by name. Falls back to MCP if not a local tool."""
        tool = self._tools.get(name)
        if tool is not None:
            extra: dict[str, Any] = {}
            if self._sandbox_executor is not None:
                extra["sandbox_executor"] = self._sandbox_executor
            ctx = ToolContext(
                cwd=self._cwd,
                permission_mode=self._config.permission_mode.value,
                session_id=self._session.session_id,
                extra=extra,
            )
            try:
                return await tool.execute(args, ctx)
            except Exception as e:
                return ToolResultData(
                    content=f"Tool error: {type(e).__name__}: {e}",
                    is_error=True,
                )

        # Try MCP tools
        if self._mcp_manager is not None and name.startswith("mcp__"):
            return await self._mcp_manager.call_tool(name, args)

        return ToolResultData(content=f"Unknown tool: {name}", is_error=True)

    async def _fire_hook(
        self,
        event: HookEvent,
        *,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        result: str | None = None,
        is_error: bool = False,
    ) -> None:
        """Fire hooks for an event, if a hook manager is configured."""
        if self._hook_manager is None:
            return
        from harness.hooks.events import build_hook_context

        ctx = build_hook_context(
            event,
            tool_name=tool_name,
            tool_args=tool_args,
            result=result,
            is_error=is_error,
            session_id=self._session.session_id,
            cwd=self._cwd,
        )
        await self._hook_manager.fire(ctx)

    async def _check_steering(self) -> str | None:
        """Check for pending steering messages."""
        if self._steering is None:
            return None
        try:
            return await self._steering.receive()
        except Exception:
            return None
