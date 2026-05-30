"""Runtime factory for creating runtime instances based on config."""

from __future__ import annotations

from typing import Any

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.runtime.interface import AgentRuntime

DEFAULT_PROVIDER_BY_SDK = {
    "claude": "claude_agent_sdk",
    "codex_sdk": "codex_subscription",
}

DEFAULT_MODEL_BY_SDK = {
    "claude": "sonnet",
    "codex_sdk": "gpt-5.5",
}

DEFAULT_API_BY_PROVIDER: dict[str, dict[str, str]] = {}

DEPRECATED_SDK_ALIASES: dict[str, str] = {}

DEPRECATED_PROVIDER_ALIASES = {
    "claude_code": "claude_agent_sdk",
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    return getattr(obj, key, default)


def normalize_sdk(sdk: str | None) -> str:
    """Return canonical SDK vocabulary."""
    value = str(sdk or "claude").strip() or "claude"
    return DEPRECATED_SDK_ALIASES.get(value, value)


def resolve_runtime_config(settings: Any | None = None, **overrides: Any) -> dict[str, Any]:
    """Resolve SDK/provider/model defaults without importing inactive runtimes."""
    settings = settings or get_settings()
    runtime = getattr(settings, "runtime", settings)
    raw_sdk = overrides.get("sdk", _get(runtime, "sdk", "claude"))
    sdk = normalize_sdk(raw_sdk)

    provider = overrides.get("provider")
    if provider is None:
        provider = _get(runtime, "provider", None)
    if provider is None:
        provider = _get(runtime, "subscription", None)
    if provider in (None, "", "claude"):
        provider = DEFAULT_PROVIDER_BY_SDK.get(sdk, str(provider or ""))
    provider = DEPRECATED_PROVIDER_ALIASES.get(str(provider), provider)

    model = overrides.get("model", _get(runtime, "model", None))
    if not model or (sdk != "claude" and str(model).startswith("anthropic/")):
        model = DEFAULT_MODEL_BY_SDK.get(sdk, str(model or ""))

    provider_defaults = DEFAULT_API_BY_PROVIDER.get(str(provider), {})
    api_base_url = overrides.get(
        "api_base_url",
        _get(runtime, "api_base_url", None) or provider_defaults.get("api_base_url"),
    )
    api_key_env = overrides.get(
        "api_key_env",
        _get(runtime, "api_key_env", None) or provider_defaults.get("api_key_env"),
    )

    return {
        "sdk": sdk,
        "raw_sdk": raw_sdk,
        "provider": provider,
        "model": model,
        "api_base_url": api_base_url,
        "api_key_env": api_key_env,
        "codex_profile": overrides.get("codex_profile", _get(runtime, "codex_profile", None)),
        "sandbox_mode": overrides.get(
            "sandbox_mode", _get(runtime, "sandbox_mode", "workspace-write")
        ),
        "approval_policy": overrides.get(
            "approval_policy", _get(runtime, "approval_policy", "never")
        ),
        "tracing": overrides.get("tracing", _get(runtime, "tracing", "builder")),
    }


def validate_runtime_config(config: dict[str, Any]) -> list[dict[str, str]]:
    """Return deterministic validation errors for illegal runtime selections."""
    sdk = str(config.get("sdk") or "")
    provider = str(config.get("provider") or "")
    errors: list[dict[str, str]] = []

    if sdk not in get_available_runtimes():
        errors.append(
            {
                "code": "invalid_sdk",
                "message": (
                    f"Unsupported user-facing runtime sdk '{sdk}'. "
                    "Use Claude Agent SDK or Codex SDK."
                ),
                "next": (
                    "builder agent runtime set --sdk codex_sdk --provider codex_subscription --json"
                ),
            }
        )
        return errors

    legal_pairs = {
        "claude": {"claude_agent_sdk"},
        "codex_sdk": {"codex_subscription"},
    }
    if provider not in legal_pairs[sdk]:
        errors.append(
            {
                "code": "invalid_provider",
                "message": f"Provider '{provider}' is not legal for sdk '{sdk}'.",
                "next": f"builder agent runtime set --sdk {sdk} --provider "
                f"{DEFAULT_PROVIDER_BY_SDK[sdk]} --json",
            }
        )

    if sdk == "codex_sdk" and (config.get("api_base_url") or config.get("api_key_env")):
        errors.append(
            {
                "code": "invalid_codex_api_config",
                "message": (
                    f"{sdk} uses Codex subscription auth and must not require "
                    "an API endpoint or API key."
                ),
                "next": (
                    "unset RUNTIME_API_BASE_URL RUNTIME_API_KEY_ENV; "
                    "builder agent runtime probe --json"
                ),
            }
        )

    return errors


def create_runtime(**kwargs: Any) -> AgentRuntime:
    """Create the selected runtime without importing inactive SDK adapters."""
    settings = get_settings()
    config = resolve_runtime_config(settings, **kwargs)
    sdk = config["sdk"]

    if sdk == "codex_sdk":
        from autonomous_agent_builder.runtime.codex_app_server_runtime import CodexAppServerRuntime

        return CodexAppServerRuntime(
            model=config["model"],
            provider=config["provider"],
            codex_profile=config["codex_profile"],
            sandbox_mode=config["sandbox_mode"],
            approval_policy=config["approval_policy"],
        )

    from autonomous_agent_builder.runtime.claude_runtime import ClaudeRuntime

    return ClaudeRuntime(
        model=config["model"],
        provider=config["provider"],
    )


def get_available_runtimes() -> list[str]:
    """List user-facing runtime lanes available through Builder controls."""
    return ["claude", "codex_sdk"]


def get_implemented_runtimes() -> list[str]:
    """List concrete adapters. Equals the user-facing lanes; no hidden adapters."""
    return ["claude", "codex_sdk"]


def get_current_runtime_name() -> str:
    """Get the current canonical runtime name from config."""
    settings = get_settings()
    return normalize_sdk(settings.runtime.sdk)
