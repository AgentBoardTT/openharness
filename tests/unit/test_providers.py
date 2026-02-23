"""Tests for harness.providers module."""

import pytest

from harness.providers.registry import MODELS, create_provider, resolve_model
from harness.types.tools import ToolDef, ToolParam


class TestRegistry:
    def test_models_exist(self):
        assert "claude-sonnet-4-6" in MODELS
        assert "gpt-4o" in MODELS
        assert "gemini-2.0-flash" in MODELS

    def test_resolve_alias(self):
        info = resolve_model("sonnet")
        assert info.id == "claude-sonnet-4-6"
        assert info.provider == "anthropic"

    def test_resolve_direct(self):
        info = resolve_model("gpt-4o")
        assert info.id == "gpt-4o"
        assert info.provider == "openai"

    def test_resolve_unknown(self):
        with pytest.raises(KeyError):
            resolve_model("nonexistent-model")

    def test_create_anthropic_provider(self):
        p = create_provider("claude-sonnet-4-6", api_key="test-key")
        assert p.model_id == "claude-sonnet-4-6"

    def test_create_openai_provider(self):
        p = create_provider("gpt-4o", api_key="test-key")
        assert p.model_id == "gpt-4o"

    def test_create_google_provider(self):
        p = create_provider("gemini-2.0-flash", api_key="test-key")
        assert p.model_id == "gemini-2.0-flash"

    def test_expanded_models(self):
        assert len(MODELS) >= 50
        assert "gpt-4.1" in MODELS
        assert "gemini-2.5-pro" in MODELS
        assert "deepseek-v3" in MODELS

    def test_expanded_aliases(self):
        assert resolve_model("llama").id == "llama3.3"
        assert resolve_model("deepseek").id == "deepseek-v3"
        assert resolve_model("gemini-pro").id == "gemini-2.5-pro"

    def test_ollama_models_in_registry(self):
        ollama_models = [m for m in MODELS.values() if m.provider == "ollama"]
        assert len(ollama_models) >= 10
        names = {m.id for m in ollama_models}
        assert "llama3.3" in names
        assert "mistral" in names
        assert "qwen2.5-coder" in names

    def test_anthropic_model_variants(self):
        assert "claude-3-5-sonnet-20241022" in MODELS
        assert "claude-3-opus-20240229" in MODELS
        assert resolve_model("sonnet-3.5").id == "claude-3-5-sonnet-20241022"

    def test_openai_model_variants(self):
        assert "gpt-4-turbo" in MODELS
        assert "gpt-3.5-turbo" in MODELS
        assert resolve_model("gpt35").id == "gpt-3.5-turbo"

    def test_google_model_variants(self):
        assert "gemini-1.5-pro" in MODELS
        assert "gemini-1.5-flash" in MODELS

    def test_create_ollama_provider(self):
        p = create_provider("llama3.3")
        assert p.model_id == "llama3.3"

    def test_all_aliases_unique(self):
        from harness.providers.registry import ALIASES
        # No alias collides with a model ID
        for alias in ALIASES:
            if alias in MODELS:
                assert ALIASES[alias] == alias, (
                    f"Alias {alias!r} collides with model ID"
                )
        # Every alias points to a valid model
        for alias, model_id in ALIASES.items():
            assert model_id in MODELS, f"Alias {alias!r} -> unknown model {model_id!r}"


class TestBaseProvider:
    def test_estimate_tokens(self):
        from harness.providers.base import BaseProvider

        class TestProvider(BaseProvider):
            async def chat_completion_stream(self, messages, tools, system, max_tokens):
                return
                yield  # type: ignore

        p = TestProvider("test")
        assert p.estimate_tokens("") == 0
        assert p.estimate_tokens("hello") == 1  # 5 // 4
        assert p.estimate_tokens("a" * 400) == 100

    def test_format_tool_result(self):
        from harness.providers.base import BaseProvider

        class TestProvider(BaseProvider):
            async def chat_completion_stream(self, messages, tools, system, max_tokens):
                return
                yield  # type: ignore

        p = TestProvider("test")
        msg = p.format_tool_result("id1", "result text")
        assert msg.role == "user"

    def test_format_tool_use(self):
        from harness.providers.base import BaseProvider

        class TestProvider(BaseProvider):
            async def chat_completion_stream(self, messages, tools, system, max_tokens):
                return
                yield  # type: ignore

        p = TestProvider("test")
        block = p.format_tool_use("id1", "my_tool", {"x": 1})
        assert block["type"] == "tool_use"
        assert block["name"] == "my_tool"

    def test_make_tool_defs(self):
        from harness.providers.base import BaseProvider

        class TestProvider(BaseProvider):
            async def chat_completion_stream(self, messages, tools, system, max_tokens):
                return
                yield  # type: ignore

        p = TestProvider("test")
        tool = ToolDef(
            name="read_file",
            description="Read a file.",
            parameters=(
                ToolParam("path", "string", "File path", required=True),
                ToolParam("encoding", "string", "Encoding", required=False, default="utf-8"),
            ),
        )
        defs = p._make_tool_defs([tool])
        assert len(defs) == 1
        assert defs[0]["name"] == "read_file"
        assert "path" in defs[0]["input_schema"]["properties"]
