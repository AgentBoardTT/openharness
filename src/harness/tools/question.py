"""Question tool — agent-initiated user prompts."""

from __future__ import annotations

from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData


class QuestionTool(BaseTool):
    """Ask the user a question mid-task.

    In interactive mode, prompts via stdin. In non-interactive mode, returns an error.
    """

    def __init__(self, *, interactive: bool = False) -> None:
        self._interactive = interactive

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="AskUser",
            description=(
                "Ask the user a question to gather information or clarify requirements. "
                "Use this when you need user input to proceed."
            ),
            parameters=(
                ToolParam(
                    name="question",
                    type="string",
                    description="The question to ask the user.",
                    required=True,
                ),
                ToolParam(
                    name="options",
                    type="array",
                    description="Optional list of choices to present.",
                    required=False,
                ),
            ),
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        question = args.get("question", "")
        if not question:
            return self._error("'question' parameter is required.")

        if not self._interactive:
            return self._error(
                "Cannot ask user questions in non-interactive mode. "
                "Make your best judgment and proceed."
            )

        options = args.get("options")

        try:
            answer = await self._prompt_user(question, options)
            return self._ok(answer)
        except (EOFError, KeyboardInterrupt):
            return self._error("User cancelled the prompt.")

    async def _prompt_user(
        self, question: str, options: list[str] | None = None,
    ) -> str:
        """Prompt the user and return their answer."""
        import asyncio

        loop = asyncio.get_event_loop()

        def _do_prompt() -> str:
            print(f"\n--- Agent Question ---\n{question}")
            if options:
                for i, opt in enumerate(options, 1):
                    print(f"  {i}. {opt}")
                print()
                raw = input("Your choice (number or text): ").strip()
                # If they entered a number, map to option
                try:
                    idx = int(raw) - 1
                    if 0 <= idx < len(options):
                        return options[idx]
                except ValueError:
                    pass
                return raw
            else:
                return input("Your answer: ").strip()

        return await loop.run_in_executor(None, _do_prompt)
