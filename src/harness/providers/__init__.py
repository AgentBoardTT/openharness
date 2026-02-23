"""Provider adapters for Harness.

Public surface
--------------
- :class:`BaseProvider`      — abstract base with shared utilities
- :class:`AnthropicProvider` — Claude adapter (Anthropic SDK)
- :class:`GoogleProvider`    — Gemini adapter (google-genai SDK)
- :class:`OpenAIProvider`    — OpenAI / compatible adapter (openai SDK)
- :func:`resolve_model`      — resolve model name / alias to :class:`ModelInfo`
- :func:`create_provider`    — factory that returns the right adapter
- :data:`MODELS`             — full model catalogue
- :data:`ALIASES`            — short-name → model-id mapping
"""

from __future__ import annotations

from harness.providers.anthropic import AnthropicProvider
from harness.providers.base import BaseProvider
from harness.providers.google import GoogleProvider
from harness.providers.ollama import OllamaProvider
from harness.providers.openai import OpenAIProvider
from harness.providers.registry import ALIASES, MODELS, create_provider, resolve_model

__all__ = [
    "ALIASES",
    "AnthropicProvider",
    "BaseProvider",
    "GoogleProvider",
    "MODELS",
    "OllamaProvider",
    "OpenAIProvider",
    "create_provider",
    "resolve_model",
]
