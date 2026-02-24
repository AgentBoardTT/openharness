"""Model registry and provider factory for Harness."""

from __future__ import annotations

from harness.types.providers import ModelInfo, ProviderAdapter

# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

MODELS: dict[str, ModelInfo] = {
    # -- Anthropic ----------------------------------------------------------
    "claude-opus-4-6": ModelInfo(
        id="claude-opus-4-6",
        provider="anthropic",
        display_name="Claude Opus 4.6",
        context_window=200_000,
        max_output_tokens=32_768,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=15.00,
        output_cost_per_mtok=75.00,
        aliases=("opus",),
    ),
    "claude-sonnet-4-6": ModelInfo(
        id="claude-sonnet-4-6",
        provider="anthropic",
        display_name="Claude Sonnet 4.6",
        context_window=200_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=3.00,
        output_cost_per_mtok=15.00,
        aliases=("sonnet",),
    ),
    "claude-haiku-4-5-20251001": ModelInfo(
        id="claude-haiku-4-5-20251001",
        provider="anthropic",
        display_name="Claude Haiku 4.5",
        context_window=200_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.80,
        output_cost_per_mtok=4.00,
        aliases=("haiku",),
    ),
    "claude-sonnet-4-5-20250514": ModelInfo(
        id="claude-sonnet-4-5-20250514",
        provider="anthropic",
        display_name="Claude Sonnet 4.5",
        context_window=200_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=3.00,
        output_cost_per_mtok=15.00,
        aliases=("sonnet-4.5",),
    ),
    "claude-3-5-sonnet-20241022": ModelInfo(
        id="claude-3-5-sonnet-20241022",
        provider="anthropic",
        display_name="Claude 3.5 Sonnet",
        context_window=200_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=3.00,
        output_cost_per_mtok=15.00,
        aliases=("sonnet-3.5",),
    ),
    "claude-3-5-haiku-20241022": ModelInfo(
        id="claude-3-5-haiku-20241022",
        provider="anthropic",
        display_name="Claude 3.5 Haiku",
        context_window=200_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.80,
        output_cost_per_mtok=4.00,
        aliases=("haiku-3.5",),
    ),
    "claude-3-opus-20240229": ModelInfo(
        id="claude-3-opus-20240229",
        provider="anthropic",
        display_name="Claude 3 Opus",
        context_window=200_000,
        max_output_tokens=4_096,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=15.00,
        output_cost_per_mtok=75.00,
        aliases=("opus-3",),
    ),
    # -- OpenAI ------------------------------------------------------------
    "gpt-5.2": ModelInfo(
        id="gpt-5.2",
        provider="openai",
        display_name="GPT-5.2",
        context_window=1_000_000,
        max_output_tokens=32_768,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=1.75,
        output_cost_per_mtok=14.00,
        aliases=("gpt52",),
    ),
    "gpt-5.2-codex": ModelInfo(
        id="gpt-5.2-codex",
        provider="openai",
        display_name="GPT-5.2 Codex",
        context_window=1_000_000,
        max_output_tokens=32_768,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=1.75,
        output_cost_per_mtok=14.00,
        aliases=("codex",),
    ),
    "gpt-4o": ModelInfo(
        id="gpt-4o",
        provider="openai",
        display_name="GPT-4o",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=2.50,
        output_cost_per_mtok=10.00,
        aliases=("gpt4o",),
    ),
    "gpt-4o-mini": ModelInfo(
        id="gpt-4o-mini",
        provider="openai",
        display_name="GPT-4o mini",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.15,
        output_cost_per_mtok=0.60,
        aliases=("gpt4o-mini",),
    ),
    "gpt-4.1": ModelInfo(
        id="gpt-4.1",
        provider="openai",
        display_name="GPT-4.1",
        context_window=1_000_000,
        max_output_tokens=32_768,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=2.00,
        output_cost_per_mtok=8.00,
        aliases=("gpt41",),
    ),
    "gpt-4.1-mini": ModelInfo(
        id="gpt-4.1-mini",
        provider="openai",
        display_name="GPT-4.1 Mini",
        context_window=1_000_000,
        max_output_tokens=32_768,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.40,
        output_cost_per_mtok=1.60,
        aliases=("gpt41-mini",),
    ),
    "gpt-4.1-nano": ModelInfo(
        id="gpt-4.1-nano",
        provider="openai",
        display_name="GPT-4.1 Nano",
        context_window=1_000_000,
        max_output_tokens=32_768,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.10,
        output_cost_per_mtok=0.40,
        aliases=("gpt41-nano",),
    ),
    "gpt-4-turbo": ModelInfo(
        id="gpt-4-turbo",
        provider="openai",
        display_name="GPT-4 Turbo",
        context_window=128_000,
        max_output_tokens=4_096,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=10.00,
        output_cost_per_mtok=30.00,
        aliases=("gpt4-turbo",),
    ),
    "gpt-3.5-turbo": ModelInfo(
        id="gpt-3.5-turbo",
        provider="openai",
        display_name="GPT-3.5 Turbo",
        context_window=16_385,
        max_output_tokens=4_096,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.50,
        output_cost_per_mtok=1.50,
        aliases=("gpt35",),
    ),
    "o3": ModelInfo(
        id="o3",
        provider="openai",
        display_name="o3",
        context_window=200_000,
        max_output_tokens=100_000,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=2.00,
        output_cost_per_mtok=8.00,
        aliases=(),
    ),
    "o3-mini": ModelInfo(
        id="o3-mini",
        provider="openai",
        display_name="o3 Mini",
        context_window=200_000,
        max_output_tokens=100_000,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=1.10,
        output_cost_per_mtok=4.40,
        aliases=(),
    ),
    "o4-mini": ModelInfo(
        id="o4-mini",
        provider="openai",
        display_name="o4 Mini",
        context_window=200_000,
        max_output_tokens=100_000,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=1.10,
        output_cost_per_mtok=4.40,
        aliases=(),
    ),
    # -- Google ------------------------------------------------------------
    "gemini-2.5-pro": ModelInfo(
        id="gemini-2.5-pro",
        provider="google",
        display_name="Gemini 2.5 Pro",
        context_window=1_000_000,
        max_output_tokens=65_536,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=1.25,
        output_cost_per_mtok=10.00,
        aliases=("gemini-pro",),
    ),
    "gemini-2.5-flash": ModelInfo(
        id="gemini-2.5-flash",
        provider="google",
        display_name="Gemini 2.5 Flash",
        context_window=1_000_000,
        max_output_tokens=65_536,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.15,
        output_cost_per_mtok=0.60,
        aliases=("gemini-flash",),
    ),
    "gemini-2.0-flash": ModelInfo(
        id="gemini-2.0-flash",
        provider="google",
        display_name="Gemini 2.0 Flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.075,
        output_cost_per_mtok=0.30,
        aliases=("flash",),
    ),
    "gemini-1.5-pro": ModelInfo(
        id="gemini-1.5-pro",
        provider="google",
        display_name="Gemini 1.5 Pro",
        context_window=2_000_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=1.25,
        output_cost_per_mtok=5.00,
        aliases=("gemini-15-pro",),
    ),
    "gemini-1.5-flash": ModelInfo(
        id="gemini-1.5-flash",
        provider="google",
        display_name="Gemini 1.5 Flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.075,
        output_cost_per_mtok=0.30,
        aliases=("gemini-15-flash",),
    ),
    # -- Ollama (local models) ---------------------------------------------
    "llama3.3": ModelInfo(
        id="llama3.3",
        provider="ollama",
        display_name="Llama 3.3 70B",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("llama",),
    ),
    "llama3.2": ModelInfo(
        id="llama3.2",
        provider="ollama",
        display_name="Llama 3.2 3B",
        context_window=128_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "llama3.1": ModelInfo(
        id="llama3.1",
        provider="ollama",
        display_name="Llama 3.1 8B",
        context_window=128_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "mistral": ModelInfo(
        id="mistral",
        provider="ollama",
        display_name="Mistral 7B",
        context_window=32_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "mistral-nemo": ModelInfo(
        id="mistral-nemo",
        provider="ollama",
        display_name="Mistral Nemo 12B",
        context_window=128_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("nemo",),
    ),
    "mistral-small": ModelInfo(
        id="mistral-small",
        provider="ollama",
        display_name="Mistral Small 24B",
        context_window=32_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "mixtral": ModelInfo(
        id="mixtral",
        provider="ollama",
        display_name="Mixtral 8x7B",
        context_window=32_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "codellama": ModelInfo(
        id="codellama",
        provider="ollama",
        display_name="Code Llama 7B",
        context_window=16_000,
        max_output_tokens=4_096,
        supports_tools=False,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "qwen2.5-coder": ModelInfo(
        id="qwen2.5-coder",
        provider="ollama",
        display_name="Qwen 2.5 Coder 7B",
        context_window=128_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("qwen-coder",),
    ),
    "qwen2.5": ModelInfo(
        id="qwen2.5",
        provider="ollama",
        display_name="Qwen 2.5 7B",
        context_window=128_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("qwen",),
    ),
    "phi4": ModelInfo(
        id="phi4",
        provider="ollama",
        display_name="Phi-4 14B",
        context_window=16_000,
        max_output_tokens=4_096,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("phi",),
    ),
    "gemma2": ModelInfo(
        id="gemma2",
        provider="ollama",
        display_name="Gemma 2 9B",
        context_window=8_000,
        max_output_tokens=4_096,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("gemma",),
    ),
    "deepseek-coder-v2": ModelInfo(
        id="deepseek-coder-v2",
        provider="ollama",
        display_name="DeepSeek Coder V2 16B",
        context_window=128_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("deepseek-coder",),
    ),
    "starcoder2": ModelInfo(
        id="starcoder2",
        provider="ollama",
        display_name="StarCoder2 7B",
        context_window=16_000,
        max_output_tokens=4_096,
        supports_tools=False,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "codegemma": ModelInfo(
        id="codegemma",
        provider="ollama",
        display_name="CodeGemma 7B",
        context_window=8_000,
        max_output_tokens=4_096,
        supports_tools=False,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "llava": ModelInfo(
        id="llava",
        provider="ollama",
        display_name="LLaVA 7B",
        context_window=4_096,
        max_output_tokens=2_048,
        supports_tools=False,
        supports_streaming=True,
        supports_vision=True,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "command-r": ModelInfo(
        id="command-r",
        provider="ollama",
        display_name="Command R 35B",
        context_window=128_000,
        max_output_tokens=4_096,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "nomic-embed-text": ModelInfo(
        id="nomic-embed-text",
        provider="ollama",
        display_name="Nomic Embed Text",
        context_window=8_192,
        max_output_tokens=0,
        supports_tools=False,
        supports_streaming=False,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "wizard-vicuna": ModelInfo(
        id="wizard-vicuna",
        provider="ollama",
        display_name="Wizard Vicuna 13B",
        context_window=4_096,
        max_output_tokens=2_048,
        supports_tools=False,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "yi": ModelInfo(
        id="yi",
        provider="ollama",
        display_name="Yi 34B",
        context_window=4_096,
        max_output_tokens=2_048,
        supports_tools=False,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "solar": ModelInfo(
        id="solar",
        provider="ollama",
        display_name="Solar 10.7B",
        context_window=4_096,
        max_output_tokens=2_048,
        supports_tools=False,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    "nous-hermes2": ModelInfo(
        id="nous-hermes2",
        provider="ollama",
        display_name="Nous Hermes 2 Mixtral",
        context_window=32_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=(),
    ),
    # -- OpenAI-Compatible (via base_url) ----------------------------------
    "deepseek-v3": ModelInfo(
        id="deepseek-v3",
        provider="openai",
        display_name="DeepSeek V3",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.27,
        output_cost_per_mtok=1.10,
        aliases=("deepseek",),
    ),
    "deepseek-r1": ModelInfo(
        id="deepseek-r1",
        provider="openai",
        display_name="DeepSeek R1",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.55,
        output_cost_per_mtok=2.19,
        aliases=(),
    ),
    "llama-3.3-70b": ModelInfo(
        id="llama-3.3-70b",
        provider="openai",
        display_name="Llama 3.3 70B (API)",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("llama-api",),
    ),
    "qwen-2.5-coder-32b": ModelInfo(
        id="qwen-2.5-coder-32b",
        provider="openai",
        display_name="Qwen 2.5 Coder 32B (API)",
        context_window=128_000,
        max_output_tokens=16_384,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.0,
        output_cost_per_mtok=0.0,
        aliases=("qwen-api",),
    ),
    "mistral-large": ModelInfo(
        id="mistral-large",
        provider="openai",
        display_name="Mistral Large",
        context_window=128_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=2.00,
        output_cost_per_mtok=6.00,
        aliases=(),
    ),
    "codestral": ModelInfo(
        id="codestral",
        provider="openai",
        display_name="Codestral",
        context_window=32_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_mtok=0.30,
        output_cost_per_mtok=0.90,
        aliases=(),
    ),
}

# ---------------------------------------------------------------------------
# Routing hints for ModelRouter decisions
# ---------------------------------------------------------------------------

ROUTING_HINTS: dict[str, dict[str, object]] = {
    "claude-opus-4-6": {
        "quality_tier": "premium", "speed_tier": "slow", "code_specialized": True,
    },
    "claude-sonnet-4-6": {
        "quality_tier": "high", "speed_tier": "medium", "code_specialized": True,
    },
    "claude-haiku-4-5-20251001": {
        "quality_tier": "medium", "speed_tier": "fast", "code_specialized": False,
    },
    "gpt-4o": {
        "quality_tier": "high", "speed_tier": "medium", "code_specialized": True,
    },
    "gpt-4o-mini": {
        "quality_tier": "medium", "speed_tier": "fast", "code_specialized": False,
    },
    "gemini-2.5-pro": {
        "quality_tier": "high", "speed_tier": "medium", "code_specialized": True,
    },
    "gemini-2.0-flash": {
        "quality_tier": "medium", "speed_tier": "fast", "code_specialized": False,
    },
    "o3": {
        "quality_tier": "premium", "speed_tier": "slow", "code_specialized": True,
    },
}

# ---------------------------------------------------------------------------
# Alias map — built automatically from ModelInfo.aliases, plus explicit extras
# ---------------------------------------------------------------------------

ALIASES: dict[str, str] = {}
for _model_id, _info in MODELS.items():
    for _alias in _info.aliases:
        ALIASES[_alias] = _model_id

# Sanity-check: every alias must resolve to a known model.
assert all(v in MODELS for v in ALIASES.values()), "Alias points to unknown model"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_model(name: str) -> ModelInfo:
    """Resolve a model name or alias to its :class:`ModelInfo`.

    Parameters
    ----------
    name:
        Either a full model ID (e.g. ``"claude-sonnet-4-6"``) or one of the
        short aliases defined in :data:`ALIASES` (e.g. ``"sonnet"``).

    Returns
    -------
    ModelInfo
        The matching model metadata.

    Raises
    ------
    KeyError
        When *name* does not match any known model or alias.

    Examples
    --------
    >>> resolve_model("sonnet").id
    'claude-sonnet-4-6'
    >>> resolve_model("claude-opus-4-6").provider
    'anthropic'
    """
    resolved_id = ALIASES.get(name, name)
    if resolved_id not in MODELS:
        known = sorted(list(MODELS.keys()) + list(ALIASES.keys()))
        raise KeyError(
            f"Unknown model {name!r}. "
            f"Known models and aliases: {known}"
        )
    return MODELS[resolved_id]


def create_provider(
    model_id: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ProviderAdapter:
    """Instantiate the correct provider adapter for *model_id*.

    Parameters
    ----------
    model_id:
        Full model ID or alias.  Aliases are resolved via :func:`resolve_model`.
    api_key:
        Optional API key.  When *None* the provider falls back to the
        appropriate environment variable (e.g. ``ANTHROPIC_API_KEY``).
    base_url:
        Optional custom base URL for self-hosted or proxy endpoints.

    Returns
    -------
    ProviderAdapter
        A ready-to-use provider adapter instance.

    Raises
    ------
    KeyError
        When *model_id* (or its resolved alias) is not in :data:`MODELS`.
    NotImplementedError
        When the provider for the given model has not yet been implemented.
    """
    info = resolve_model(model_id)
    resolved_id = info.id

    if resolved_id.startswith("claude-"):
        from harness.providers.anthropic import AnthropicProvider

        kwargs: dict = {"api_key": api_key, "model": resolved_id}
        if base_url is not None:
            kwargs["base_url"] = base_url  # type: ignore[assignment]
        try:
            return AnthropicProvider(**kwargs)  # type: ignore[arg-type]
        except TypeError:
            return AnthropicProvider(api_key=api_key, model=resolved_id)

    if info.provider == "ollama":
        from harness.providers.ollama import OllamaProvider

        return OllamaProvider(
            model=resolved_id,
            base_url=base_url,
            api_key=api_key,
        )

    if info.provider == "openai" or resolved_id.startswith("gpt-"):
        from harness.providers.openai import OpenAIProvider

        return OpenAIProvider(
            api_key=api_key, model=resolved_id, base_url=base_url,
        )

    if info.provider == "google" or resolved_id.startswith("gemini-"):
        from harness.providers.google import GoogleProvider

        return GoogleProvider(api_key=api_key, model=resolved_id)

    raise NotImplementedError(
        f"No provider implementation for model {resolved_id!r}"
    )
