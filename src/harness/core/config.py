"""Configuration loading (TOML, env vars, HARNESS.md)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from current directory (and parents), won't override existing env vars
load_dotenv()


def load_env_config() -> dict[str, Any]:
    """Load configuration from environment variables."""
    config: dict[str, Any] = {}

    if key := os.environ.get("ANTHROPIC_API_KEY"):
        config["anthropic_api_key"] = key
    if key := os.environ.get("OPENAI_API_KEY"):
        config["openai_api_key"] = key
    if key := os.environ.get("GOOGLE_API_KEY"):
        config["google_api_key"] = key
    if provider := os.environ.get("HARNESS_PROVIDER"):
        config["provider"] = provider
    if model := os.environ.get("HARNESS_MODEL"):
        config["model"] = model

    return config


def load_toml_config(cwd: str | None = None) -> dict[str, Any]:
    """Load configuration from .harness/config.toml if it exists."""
    search_dirs = []
    if cwd:
        search_dirs.append(Path(cwd))
    search_dirs.append(Path.cwd())
    search_dirs.append(Path.home() / ".harness")

    for d in search_dirs:
        toml_path = d / ".harness" / "config.toml"
        if toml_path.exists():
            try:
                import tomllib
                with open(toml_path, "rb") as f:
                    return tomllib.load(f)
            except Exception:
                pass
        # Also check direct path for ~/.harness/config.toml
        if d == Path.home() / ".harness":
            toml_path = d / "config.toml"
            if toml_path.exists():
                try:
                    import tomllib
                    with open(toml_path, "rb") as f:
                        return tomllib.load(f)
                except Exception:
                    pass
    return {}


def load_harness_md(cwd: str | None = None) -> str | None:
    """Load HARNESS.md from the project directory."""
    search_dirs = []
    if cwd:
        search_dirs.append(Path(cwd))
    search_dirs.append(Path.cwd())

    for d in search_dirs:
        for name in ("HARNESS.md", ".harness/HARNESS.md"):
            md_path = d / name
            if md_path.exists():
                try:
                    return md_path.read_text()
                except Exception:
                    pass
    return None


ENV_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def resolve_api_key(provider: str, explicit_key: str | None = None) -> str | None:
    """Resolve API key for a provider from explicit value, environment, or config file."""
    if explicit_key:
        return explicit_key

    env_var = ENV_MAP.get(provider)
    if env_var:
        val = os.environ.get(env_var)
        if val:
            return val

    # Fallback: check ~/.harness/config.toml
    config_path = Path.home() / ".harness" / "config.toml"
    if config_path.exists():
        try:
            import tomllib

            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            key = data.get("providers", {}).get(provider, {}).get("api_key")
            if key:
                return key
        except Exception:
            pass

    return None


def load_defaults() -> dict[str, str]:
    """Load saved defaults (provider, model) from ~/.harness/config.toml.

    Returns a dict with optional keys ``"provider"`` and ``"model"``.
    """
    config_path = Path.home() / ".harness" / "config.toml"
    if not config_path.exists():
        return {}
    try:
        import tomllib
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        return {k: v for k, v in data.get("defaults", {}).items() if isinstance(v, str)}
    except Exception:
        return {}


def resolve_saved_session() -> dict[str, str]:
    """Resolve the best (provider, api_key, model) from saved config.

    Checks multiple sources in priority order:

    1. ``[defaults]`` section for provider/model preferences.
    2. API key for the default provider (env var → config file).
    3. If no key found for the default provider, scans ``[providers.*]``
       for any provider that has a saved key.

    Returns a dict with optional keys ``"provider"``, ``"api_key"``, ``"model"``.
    An empty dict means nothing useful was found.
    """
    config_path = Path.home() / ".harness" / "config.toml"
    result: dict[str, str] = {}

    # Load defaults section if available
    defaults = load_defaults()
    provider = defaults.get("provider")
    model = defaults.get("model")

    if provider:
        result["provider"] = provider
    if model:
        result["model"] = model

    # Try to resolve an API key for the chosen provider
    target_provider = provider or "anthropic"

    # Check env var first
    env_var = ENV_MAP.get(target_provider)
    if env_var:
        val = os.environ.get(env_var)
        if val:
            result["api_key"] = val
            if "provider" not in result:
                result["provider"] = target_provider
            return result

    # Check config file for the target provider's key
    if config_path.exists():
        try:
            import tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            # Try the target provider first
            key = data.get("providers", {}).get(target_provider, {}).get("api_key")
            if key:
                result["api_key"] = key
                if "provider" not in result:
                    result["provider"] = target_provider
                return result

            # No key for target — scan all saved providers
            for prov, prov_conf in data.get("providers", {}).items():
                if isinstance(prov_conf, dict):
                    saved_key = prov_conf.get("api_key")
                    if saved_key:
                        result["provider"] = prov
                        result["api_key"] = saved_key
                        if "model" not in result:
                            # Don't leave model set to a different provider's model
                            pass
                        return result
        except Exception:
            pass

    # Last resort: check all env vars
    for prov, env_name in ENV_MAP.items():
        val = os.environ.get(env_name)
        if val:
            result["provider"] = prov
            result["api_key"] = val
            return result

    return result


def save_defaults(provider: str | None = None, model: str | None = None) -> Path:
    """Persist provider and/or model as the user's defaults.

    Writes to the ``[defaults]`` section of ``~/.harness/config.toml``.
    Only non-*None* values are written; existing keys are preserved.

    Returns the config file path.
    """
    config_dir = Path.home() / ".harness"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"

    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            import tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            pass

    if "defaults" not in data:
        data["defaults"] = {}
    if provider is not None:
        data["defaults"]["provider"] = provider
    if model is not None:
        data["defaults"]["model"] = model

    _write_toml(config_path, data)
    return config_path


def save_api_key(provider: str, api_key: str) -> Path:
    """Save an API key to ~/.harness/config.toml and set it in the current process.

    Returns the path written to.
    """
    config_dir = Path.home() / ".harness"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"

    # Read existing config or start fresh
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            import tomllib

            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            pass

    # Ensure providers section exists
    if "providers" not in data:
        data["providers"] = {}
    data["providers"].setdefault(provider, {})
    data["providers"][provider]["api_key"] = api_key

    # Write back as TOML
    _write_toml(config_path, data)

    # Set env var so it takes effect immediately in this process
    env_var = ENV_MAP.get(provider)
    if env_var:
        os.environ[env_var] = api_key

    return config_path


def _write_toml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict as TOML to *path* (minimal writer, no external dependency)."""
    lines: list[str] = []
    # Write top-level simple keys first
    for k, v in data.items():
        if not isinstance(v, dict):
            lines.append(f"{k} = {_toml_value(v)}")
    # Write sections
    for k, v in data.items():
        if isinstance(v, dict):
            _write_toml_section(lines, [k], v)
    path.write_text("\n".join(lines) + "\n")
    # Restrict permissions — config may contain API keys
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows or other OS that doesn't support chmod


def _write_toml_section(lines: list[str], prefix: list[str], d: dict[str, Any]) -> None:
    """Recursively write TOML sections."""
    simple: list[tuple[str, Any]] = []
    nested: list[tuple[str, dict[str, Any]]] = []
    for k, v in d.items():
        if isinstance(v, dict):
            nested.append((k, v))
        else:
            simple.append((k, v))
    if simple:
        lines.append(f"\n[{'.'.join(prefix)}]")
        for k, v in simple:
            lines.append(f"{k} = {_toml_value(v)}")
    for k, v in nested:
        _write_toml_section(lines, prefix + [k], v)


def _toml_value(v: Any) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(v, (list, tuple)):
        items = ", ".join(_toml_value(item) for item in v)
        return f"[{items}]"
    return repr(v)


def load_sandbox_config(cwd: str | None = None) -> dict[str, Any]:
    """Load [sandbox] section from config."""
    config = load_toml_config(cwd)
    return config.get("sandbox", {})


def load_policy_config(cwd: str | None = None) -> dict[str, Any]:
    """Load [policy] section from config."""
    config = load_toml_config(cwd)
    return config.get("policy", {})


def load_router_config(cwd: str | None = None) -> dict[str, Any]:
    """Load [router] section from config."""
    config = load_toml_config(cwd)
    return config.get("router", {})
