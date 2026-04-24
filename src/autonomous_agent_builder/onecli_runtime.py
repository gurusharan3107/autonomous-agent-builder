"""OneCLI runtime bootstrap for Claude child processes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import httpx
import structlog

log = structlog.get_logger()

PROVIDER_AUTH_ENV_KEYS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


@dataclass(frozen=True)
class OneCLIRuntimeEnv:
    active: bool
    env: dict[str, str] = field(default_factory=dict)
    message: str = ""


def _env_enabled(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_explicit_disabled(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in {"0", "false", "no", "off"}


def _onecli_enabled() -> bool:
    # Explicit opt-out wins over URL/key presence so users can keep routing
    # values in .env without accidentally activating OneCLI.
    if _env_explicit_disabled("AAB_ONECLI_ENABLED"):
        return False
    return _env_enabled("AAB_ONECLI_ENABLED") or bool(
        os.environ.get("ONECLI_API_KEY") or os.environ.get("ONECLI_URL")
    )


def _onecli_url() -> str:
    return (
        os.environ.get("ONECLI_URL")
        or os.environ.get("AAB_ONECLI_URL")
        or "http://127.0.0.1:10254"
    ).rstrip("/")


def _onecli_agent_identifier() -> str | None:
    agent = os.environ.get("ONECLI_AGENT") or os.environ.get("AAB_ONECLI_AGENT")
    if not agent:
        return None
    return agent.strip() or None


def _onecli_fail_closed() -> bool:
    return _env_enabled("AAB_ONECLI_FAIL_CLOSED")


async def prepare_onecli_runtime_env() -> OneCLIRuntimeEnv:
    """Return OneCLI-derived env for a Claude runtime subprocess.

    OneCLI is intentionally opt-in. Set `AAB_ONECLI_ENABLED=true` or provide
    `ONECLI_URL` / `ONECLI_API_KEY` to activate it for local runs.
    """

    if not _onecli_enabled():
        return OneCLIRuntimeEnv(active=False, message="OneCLI disabled.")

    try:
        body = await _fetch_onecli_container_config(
            url=_onecli_url(),
            api_key=os.environ.get("ONECLI_API_KEY"),
            agent_identifier=_onecli_agent_identifier(),
        )
        env = _runtime_env_from_response(body)
    except Exception as exc:
        if _onecli_fail_closed():
            raise RuntimeError(f"OneCLI runtime bootstrap failed: {exc}") from exc
        log.warning("onecli_runtime_bootstrap_unavailable", error=str(exc))
        return OneCLIRuntimeEnv(active=False, message=str(exc))

    log.info("onecli_runtime_bootstrap_active", keys=sorted(env))
    return OneCLIRuntimeEnv(active=True, env=env)


async def _fetch_onecli_container_config(
    *,
    url: str,
    api_key: str | None,
    agent_identifier: str | None,
) -> dict[str, object]:
    params = {"agent": agent_identifier} if agent_identifier else None
    endpoint = f"{url}/api/container-config"
    if params:
        endpoint = f"{endpoint}?{urlencode(params)}"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.get(endpoint, headers=headers)
        response.raise_for_status()
        return response.json()


def _runtime_env_from_response(body: dict[str, object]) -> dict[str, str]:
    raw_env = body.get("env")
    if not isinstance(raw_env, dict):
        raise ValueError("OneCLI container-config response is missing env.")

    env = {str(key): str(value) for key, value in raw_env.items()}
    _write_ca_certificate(body)

    for key in PROVIDER_AUTH_ENV_KEYS:
        if key not in env and os.environ.get(key):
            env[key] = "placeholder"
    return env


def _write_ca_certificate(body: dict[str, object]) -> None:
    ca_certificate = body.get("caCertificate")
    ca_path = body.get("caCertificateContainerPath")
    if not ca_certificate:
        return
    if not isinstance(ca_certificate, str) or not isinstance(ca_path, str) or not ca_path:
        raise ValueError("OneCLI CA response is incomplete.")

    path = Path(ca_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ca_certificate, encoding="utf-8")
