"""Web tools — HTTP fetch and web search."""

from __future__ import annotations

import re
from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

MAX_CONTENT_LENGTH = 50_000


def _html_to_text(html: str) -> str:
    """Simple HTML to text conversion — strips tags and decodes entities."""
    # Remove script and style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block elements with newlines
    text = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


class WebFetchTool(BaseTool):
    """Fetch content from a URL via HTTP GET."""

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="WebFetch",
            description=(
                "Fetch content from a URL. Returns the page text (HTML converted to "
                "plain text). Useful for reading documentation, APIs, or web pages."
            ),
            parameters=(
                ToolParam(
                    name="url",
                    type="string",
                    description="The URL to fetch.",
                    required=True,
                ),
                ToolParam(
                    name="max_length",
                    type="integer",
                    description="Maximum content length to return (default 50000).",
                    required=False,
                    default=MAX_CONTENT_LENGTH,
                ),
            ),
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        url = args.get("url", "")
        if not url:
            return self._error("'url' parameter is required.")

        if not url.startswith(("http://", "https://")):
            return self._error("URL must start with http:// or https://")

        max_length = args.get("max_length", MAX_CONTENT_LENGTH)

        try:
            import httpx

            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                headers={"User-Agent": "Harness/0.1"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            body = resp.text

            # Convert HTML to text
            if "html" in content_type:
                body = _html_to_text(body)

            # Truncate if needed
            if len(body) > max_length:
                body = body[:max_length] + f"\n\n[Truncated — {len(resp.text):,} chars total]"

            return self._ok(body)
        except ImportError:
            return self._error("httpx is not installed. Run: pip install httpx")
        except Exception as e:
            return self._error(f"Fetch failed: {type(e).__name__}: {e}")


class WebSearchTool(BaseTool):
    """Web search stub — requires a search API key."""

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="WebSearch",
            description=(
                "Search the web for information. Note: requires a search API key "
                "to be configured."
            ),
            parameters=(
                ToolParam(
                    name="query",
                    type="string",
                    description="The search query.",
                    required=True,
                ),
            ),
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        return self._error(
            "Web search is not available — no search API key configured. "
            "Use WebFetch to retrieve content from a specific URL instead."
        )
