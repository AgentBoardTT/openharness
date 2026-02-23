"""Base tool class with shared logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from harness.types.tools import ToolContext, ToolDef, ToolResultData


class BaseTool(ABC):
    """Base class for all tools."""

    @property
    @abstractmethod
    def definition(self) -> ToolDef:
        ...

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        ...

    def _error(self, msg: str) -> ToolResultData:
        return ToolResultData(content=msg, is_error=True)

    def _ok(self, content: str, display: str | None = None) -> ToolResultData:
        return ToolResultData(content=content, display=display)
