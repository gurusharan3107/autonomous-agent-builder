"""Runtime settings persistence shared by CLI, onboarding, and dashboard APIs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from autonomous_agent_builder.builder_env import builder_source_env_path
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.observability.codex_otel import (
    codex_otel_config_path,
    codex_otel_status,
    ensure_project_codex_otel_config,
)
from autonomous_agent_builder.runtime import create_runtime
from autonomous_agent_builder.runtime.factory import (
    DEFAULT_MODEL_BY_SDK,
    DEFAULT_PROVIDER_BY_SDK,
    normalize_sdk,
    resolve_runtime_config,
    validate_runtime_config,
)

RUNTIME_ENV_KEYS = (
    "RUNTIME_SDK",
    "RUNTIME_PROVIDER",
    "RUNTIME_MODEL",
    "RUNTIME_API_BASE_URL",
    "RUNTIME_API_KEY_ENV",
    "RUNTIME_CODEX_PROFILE",
    "RUNTIME_SANDBOX_MODE",
    "RUNTIME_APPROVAL_POLICY",
    "RUNTIME_TRACING",
)

TELEMETRY_ENV_KEYS = (
    "AAB_CLAUDE_OTEL_ENABLED",
    "AAB_CLAUDE_OTEL_ENDPOINT",
    "AAB_CLAUDE_OTEL_SERVICE_NAME",
    "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID",
    "AAB_CLAUDE_OTEL_RESOURCE_ATTRIBUTES",
    "AAB_CLAUDE_OTEL_DETAILED_BETA_TRACING",
    "AAB_CLAUDE_OTEL_BETA_TRACING_ENDPOINT",
    "AAB_CLAUDE_OTEL_LOG_USER_PROMPTS",
    "AAB_CLAUDE_OTEL_LOG_TOOL_DETAILS",
    "AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT",
    "AAB_CLAUDE_OTEL_LOG_RAW_API_BODIES",
    "AAB_CODEX_RUNTIME_TELEMETRY_ENABLED",
    "AAB_CODEX_JSONL_TELEMETRY_ENABLED",
    "AAB_CODEX_TELEMETRY_SOURCE",
    "AAB_CODEX_TELEMETRY_COST_SOURCE",
)

DEFAULT_OTEL_ENDPOINT = "http://localhost:4318"
HISTORICAL_TELEMETRY_SURFACES = (
    "builder logs --error --json",
    "builder logs --info --compact --json",
    "builder logs analyze --session <id-or-prefix> --json",
    "builder metrics show --json",
)


def runtime_settings_payload(
    project_root: Path,
    config: dict[str, Any] | None = None,
    *,
    include_capabilities: bool = True,
) -> dict[str, Any]:
    """Return the active runtime settings plus telemetry-lane state."""
    resolved = config or resolve_project_runtime_config(project_root)
    errors = validate_runtime_config(resolved)
    payload: dict[str, Any] = {
        "sdk": resolved["sdk"],
        "raw_sdk": resolved.get("raw_sdk"),
        "provider": resolved["provider"],
        "model": resolved["model"],
        "api_base_url": resolved.get("api_base_url"),
        "api_key_env": resolved.get("api_key_env"),
        "codex_profile": resolved.get("codex_profile"),
        "sandbox_mode": resolved.get("sandbox_mode"),
        "approval_policy": resolved.get("approval_policy"),
        "tracing": resolved.get("tracing"),
        "auth": _runtime_auth_state(project_root, resolved),
        "telemetry": telemetry_state(project_root, resolved),
        "errors": errors,
        "ok": not errors,
        "schema_version": "1",
        "next": "builder agent runtime probe --json" if not errors else errors[0]["next"],
    }
    if include_capabilities and not errors:
        runtime = create_runtime(**resolved)
        payload["capabilities"] = asdict(runtime.capabilities())
    return payload


def _runtime_auth_state(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Return redacted auth readiness for the active runtime."""
    sdk = str(config.get("sdk") or "")
    env = parse_env_file(builder_source_env_path())
    if sdk == "claude":
        oauth_configured = bool(env.get("CLAUDE_CODE_OAUTH_TOKEN"))
        return {
            "method": "claude_code_oauth_token",
            "configured": oauth_configured,
            "source": "builder_source_env" if oauth_configured else "builder_source_env_missing",
            "api_key_required": False,
            "api_key_used": False,
            "next": (
                ""
                if oauth_configured
                else (
                    "Set CLAUDE_CODE_OAUTH_TOKEN in the autonomous-agent-builder "
                    f"source env: {builder_source_env_path()}"
                )
            ),
        }
    if sdk.startswith("codex"):
        return {
            "method": "codex_subscription",
            "configured": True,
            "api_key_required": False,
            "api_key_used": False,
            "next": "",
        }
    api_key_env = str(config.get("api_key_env") or "")
    return {
        "method": "provider_api_key",
        "configured": bool(api_key_env and env.get(api_key_env)),
        "api_key_required": bool(api_key_env),
        "api_key_used": bool(api_key_env and env.get(api_key_env)),
        "source": "builder_source_env",
        "next": f"Set {api_key_env} in {builder_source_env_path()}" if api_key_env else "",
    }


def resolve_project_runtime_config(project_root: Path) -> dict[str, Any]:
    """Resolve runtime config from the Builder source `.env`."""
    env = parse_env_file(builder_source_env_path())
    overrides = _runtime_overrides_from_env(env)
    return resolve_runtime_config(get_settings(), **overrides)


def persist_runtime_settings(
    project_root: Path,
    *,
    sdk: str,
    provider: str | None = None,
    model: str | None = None,
    api_base_url: str | None = None,
    api_key_env: str | None = None,
    codex_profile: str | None = None,
    sandbox_mode: str | None = None,
    approval_policy: str | None = None,
    tracing: str | None = None,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Persist runtime and active telemetry-lane settings to Builder source `.env`."""
    canonical_sdk = normalize_sdk(sdk)
    overrides = {
        "sdk": canonical_sdk,
        "provider": provider or DEFAULT_PROVIDER_BY_SDK.get(canonical_sdk),
        "model": model or DEFAULT_MODEL_BY_SDK.get(canonical_sdk),
        "api_base_url": api_base_url,
        "api_key_env": api_key_env,
        "codex_profile": codex_profile,
        "sandbox_mode": sandbox_mode,
        "approval_policy": approval_policy,
        "tracing": tracing,
    }
    config = resolve_runtime_config(
        get_settings(),
        **{key: value for key, value in overrides.items() if value is not None},
    )
    errors = validate_runtime_config(config)
    if errors:
        payload = runtime_settings_payload(project_root, config, include_capabilities=False)
        payload.update(
            {
                "status": "error",
                "code": errors[0]["code"],
                "message": errors[0]["message"],
            }
        )
        return payload

    env_path = builder_source_env_path()
    changed = write_runtime_env(env_path, config, project_name=project_name or project_root.name)
    if str(config.get("sdk") or "") == "codex_sdk":
        changed.extend(_ensure_project_codex_otel_after_env(project_root.resolve(), env_path))
    payload = runtime_settings_payload(project_root, config)
    payload.update({"status": "updated", "settings_file": str(env_path), "changed_keys": changed})
    return payload


def reconcile_runtime_project_state(project_root: Path) -> dict[str, Any]:
    """Repair deterministic project state after a runtime switch.

    Runtime changes rewrite the Builder source `.env`, which intentionally
    changes readiness inputs. The switch itself is deterministic, so the
    dashboard should repair runtime guidance, telemetry lane state, and
    readiness immediately instead of sending an already-onboarded project back
    through onboarding.
    """
    root = project_root.resolve()
    raw_state = _load_onboarding_state_file(root)
    if raw_state is None:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "onboarding_state_missing",
            "readiness": None,
        }

    from autonomous_agent_builder.onboarding import save_onboarding_state
    from autonomous_agent_builder.services.readiness import READY_STATE, assess_readiness
    from autonomous_agent_builder.services.runtime_guidance import (
        ensure_project_runtime_guidance,
        ensure_project_telemetry_env,
        infer_runtime_guidance_context,
    )

    repo = raw_state.get("repo", {}) if isinstance(raw_state.get("repo"), dict) else {}
    language = str(repo.get("language") or _detect_language(root) or "unknown")
    framework = str(repo.get("framework") or _detect_framework(root, language) or "")
    mode = str(raw_state.get("onboarding_mode") or _classify_onboarding_mode(root))
    if _was_ready(raw_state) and _forward_kb_deferred_from_state(raw_state):
        mode = "forward_engineering"
        raw_state["onboarding_mode"] = mode
    scan_summary = (
        raw_state.get("scan_summary") if isinstance(raw_state.get("scan_summary"), dict) else {}
    )
    project_name = str(repo.get("name") or root.name)

    guidance_context = infer_runtime_guidance_context(
        root,
        mode=mode,
        language=language,
        framework=framework,
        scan_summary=scan_summary,
    )
    runtime_guidance = ensure_project_runtime_guidance(
        root,
        project_name=project_name,
        **guidance_context,
    )
    telemetry = ensure_project_telemetry_env(root, project_name=project_name)

    if _was_ready(raw_state):
        raw_state["ready"] = True
        raw_state["current_phase"] = "ready"
        _mark_ready_phase(raw_state)
        raw_state["errors"] = []

    save_onboarding_state(root, raw_state)
    readiness = assess_readiness(root, onboarding_state=raw_state, write=True)
    return {
        "ok": readiness.get("state") == READY_STATE,
        "status": "ready" if readiness.get("state") == READY_STATE else "blocked",
        "runtime_guidance": runtime_guidance,
        "telemetry": telemetry,
        "readiness": {
            "state": readiness.get("state"),
            "can_continue": readiness.get("can_continue"),
            "blocking_reasons": readiness.get("blocking_reasons", []),
            "invalidated_by": readiness.get("invalidated_by", []),
        },
    }


def ensure_runtime_env(
    project_root: Path,
    *,
    project_name: str,
    config: dict[str, Any] | None = None,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Ensure Builder source `.env` has runtime and telemetry settings."""
    root = project_root.resolve()
    env_path = builder_source_env_path()
    existed = env_path.exists()
    resolved = config or resolve_runtime_config(get_settings())
    changed = write_runtime_env(env_path, resolved, project_name=project_name, endpoint=endpoint)
    if str(resolved.get("sdk") or "") == "codex_sdk":
        changed.extend(_ensure_project_codex_otel_after_env(root, env_path))
    if not existed:
        status = "created"
    elif changed:
        status = "updated"
    else:
        status = "existing"
    return {
        "created": not existed,
        "status": status,
        "path": str(env_path),
        "relative_path": ".env",
        "changed_keys": changed,
        "runtime_sdk": resolved["sdk"],
        "active_telemetry": telemetry_state(root, resolved)["active_lane"],
    }


def _ensure_project_codex_otel_after_env(project_root: Path, env_path: Path) -> list[str]:
    """Keep project-local Codex telemetry ready without activating Codex runtime env."""
    otel_endpoint = parse_env_file(env_path).get("AAB_CLAUDE_OTEL_ENDPOINT", DEFAULT_OTEL_ENDPOINT)
    codex_otel = ensure_project_codex_otel_config(project_root, endpoint=otel_endpoint)
    return ["CODEX_OTEL_CONFIG"] if codex_otel.get("changed") else []


def write_runtime_env(
    path: Path,
    config: dict[str, Any],
    *,
    project_name: str,
    endpoint: str | None = None,
) -> list[str]:
    """Upsert runtime and telemetry env keys while preserving unrelated values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_env = parse_env_file(path)
    values = _runtime_env_values(config)
    values.update(
        _telemetry_env_values(
            config,
            existing_env=existing_env,
            project_name=project_name,
            endpoint=endpoint,
        )
    )

    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    managed_keys = set(values)
    kept: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            kept.append(line)
            continue
        key = line.split("=", 1)[0].strip() if "=" in line else stripped
        if key not in managed_keys:
            kept.append(line)

    changed: list[str] = []
    for key, value in values.items():
        current = existing_env.get(key)
        if value in (None, ""):
            if current is not None:
                changed.append(key)
                os.environ.pop(key, None)
            continue
        rendered = str(value)
        if current != rendered:
            changed.append(key)
        kept.append(f"{key}={_env_quote(rendered)}")
        os.environ[key] = rendered

    path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    return changed


def telemetry_state(project_root: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return safe telemetry-lane state for the active runtime."""
    env = parse_env_file(builder_source_env_path())
    if config is None:
        overrides = _runtime_overrides_from_env(env)
        resolved = resolve_runtime_config(get_settings(), **overrides)
    else:
        resolved = config
    sdk = str(resolved.get("sdk") or "")
    active_lane = "codex" if sdk.startswith("codex") else "claude" if sdk == "claude" else "api"
    claude_enabled = _truthy(env.get("AAB_CLAUDE_OTEL_ENABLED"))
    codex_enabled = _truthy(
        env.get("AAB_CODEX_RUNTIME_TELEMETRY_ENABLED")
        or env.get("AAB_CODEX_JSONL_TELEMETRY_ENABLED")
    )
    endpoint = str(env.get("AAB_CLAUDE_OTEL_ENDPOINT") or "").strip()
    if active_lane == "claude":
        active_enabled = claude_enabled and bool(endpoint)
        inactive_disabled = not codex_enabled
    elif active_lane == "codex":
        active_enabled = codex_enabled
        inactive_disabled = not claude_enabled
    else:
        active_enabled = not claude_enabled and not codex_enabled
        inactive_disabled = True
    codex_otel = (
        codex_otel_status(project_root)
        if active_lane == "codex" and codex_enabled
        else _inactive_codex_otel_status(project_root)
    )
    return {
        "active_lane": active_lane,
        "active_enabled": active_enabled,
        "inactive_disabled": inactive_disabled,
        "historical_access": {
            "available": True,
            "applies_to_inactive_lanes": True,
            "surfaces": list(HISTORICAL_TELEMETRY_SURFACES),
        },
        "claude": {
            "enabled": claude_enabled,
            "endpoint": endpoint,
            "service_name": env.get("AAB_CLAUDE_OTEL_SERVICE_NAME", ""),
            "include_session_id": env.get("AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID", ""),
            "history_accessible": True,
        },
        "codex": {
            "enabled": codex_enabled,
            "source": env.get("AAB_CODEX_TELEMETRY_SOURCE", ""),
            "cost_source": env.get("AAB_CODEX_TELEMETRY_COST_SOURCE", ""),
            "history_accessible": True,
            "otel": codex_otel,
        },
    }


def _inactive_codex_otel_status(project_root: Path) -> dict[str, Any]:
    path = codex_otel_config_path(project_root)
    status = codex_otel_status(project_root) if path.exists() else {}
    inactive = {
        **status,
        "configured": bool(status.get("configured", path.exists())),
        "enabled": False,
        "endpoint": "",
        "collector": {
            "configured": False,
            "local": False,
            "checked": False,
            "reachable": False,
            "status": "inactive",
            "endpoint": "",
            "error": "",
        },
        "collector_status": "inactive",
        "collector_reachable": False,
        "emitted_signals": {
            "logs": False,
            "metrics": False,
            "traces": False,
            "trace_metadata": False,
            "review_feedback": False,
            "analytics": False,
            "native_event_names": False,
        },
        "config_path": str(path),
        "project_local": True,
        "current_emission_enabled": False,
        "historical_accessible": True,
        "historical_surfaces": list(HISTORICAL_TELEMETRY_SURFACES),
        "reason": "inactive_runtime",
    }
    if not status or not inactive["configured"]:
        inactive.update(
            {
                "exporter": "missing",
                "span_attributes_configured": False,
                "tracestate_configured": False,
                "trace_metadata_configured": False,
                "feedback_configured": False,
                "feedback_enabled": False,
                "analytics_configured": False,
                "analytics_enabled": False,
            }
        )
    return inactive


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple dotenv file without expanding values."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _runtime_overrides_from_env(env: dict[str, str]) -> dict[str, str]:
    return {
        key: env[env_key]
        for key, env_key in (
            ("sdk", "RUNTIME_SDK"),
            ("provider", "RUNTIME_PROVIDER"),
            ("model", "RUNTIME_MODEL"),
            ("api_base_url", "RUNTIME_API_BASE_URL"),
            ("api_key_env", "RUNTIME_API_KEY_ENV"),
            ("codex_profile", "RUNTIME_CODEX_PROFILE"),
            ("sandbox_mode", "RUNTIME_SANDBOX_MODE"),
            ("approval_policy", "RUNTIME_APPROVAL_POLICY"),
            ("tracing", "RUNTIME_TRACING"),
        )
        if env.get(env_key)
    }


def _runtime_env_values(config: dict[str, Any]) -> dict[str, str | None]:
    values: dict[str, str | None] = {
        "RUNTIME_SDK": str(config["sdk"]),
        "RUNTIME_PROVIDER": str(config["provider"]),
        "RUNTIME_MODEL": str(config["model"]),
        "RUNTIME_API_BASE_URL": config.get("api_base_url"),
        "RUNTIME_API_KEY_ENV": config.get("api_key_env"),
        "RUNTIME_CODEX_PROFILE": config.get("codex_profile"),
        "RUNTIME_SANDBOX_MODE": config.get("sandbox_mode"),
        "RUNTIME_APPROVAL_POLICY": config.get("approval_policy"),
        "RUNTIME_TRACING": config.get("tracing"),
    }
    if config["sdk"] == "codex_sdk":
        values["RUNTIME_API_BASE_URL"] = None
        values["RUNTIME_API_KEY_ENV"] = None
    return values


def _telemetry_env_values(
    config: dict[str, Any],
    *,
    existing_env: dict[str, str],
    project_name: str,
    endpoint: str | None,
) -> dict[str, str | None]:
    sdk = str(config.get("sdk") or "")
    codex_source = "codex_app_server_jsonrpc" if sdk == "codex_sdk" else "codex_exec_jsonl"
    otel_endpoint = endpoint or existing_env.get("AAB_CLAUDE_OTEL_ENDPOINT", DEFAULT_OTEL_ENDPOINT)
    service_name = existing_env.get("AAB_CLAUDE_OTEL_SERVICE_NAME", _slug(project_name))
    resource_attributes = existing_env.get(
        "AAB_CLAUDE_OTEL_RESOURCE_ATTRIBUTES",
        ",".join(
            [
                "service.version=0.1.0",
                "deployment.environment=local",
                f"builder.project={_slug(project_name)}",
                "builder.runtime=claude_agent_sdk",
                "builder.goal=voice_first_delivery_os",
            ]
        ),
    )
    return {
        "AAB_CLAUDE_OTEL_ENABLED": "1" if sdk == "claude" else "0",
        "AAB_CLAUDE_OTEL_ENDPOINT": otel_endpoint,
        "AAB_CLAUDE_OTEL_SERVICE_NAME": service_name,
        "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID": existing_env.get(
            "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID", "true"
        ),
        "AAB_CLAUDE_OTEL_RESOURCE_ATTRIBUTES": resource_attributes,
        "AAB_CLAUDE_OTEL_DETAILED_BETA_TRACING": existing_env.get(
            "AAB_CLAUDE_OTEL_DETAILED_BETA_TRACING", "1" if sdk == "claude" else "0"
        ),
        "AAB_CLAUDE_OTEL_BETA_TRACING_ENDPOINT": existing_env.get(
            "AAB_CLAUDE_OTEL_BETA_TRACING_ENDPOINT", otel_endpoint
        ),
        "AAB_CLAUDE_OTEL_LOG_USER_PROMPTS": existing_env.get(
            "AAB_CLAUDE_OTEL_LOG_USER_PROMPTS", "0"
        ),
        "AAB_CLAUDE_OTEL_LOG_TOOL_DETAILS": existing_env.get(
            "AAB_CLAUDE_OTEL_LOG_TOOL_DETAILS", "0"
        ),
        "AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT": existing_env.get(
            "AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT", "0"
        ),
        "AAB_CLAUDE_OTEL_LOG_RAW_API_BODIES": existing_env.get(
            "AAB_CLAUDE_OTEL_LOG_RAW_API_BODIES", "0"
        ),
        "AAB_CODEX_RUNTIME_TELEMETRY_ENABLED": "1" if sdk == "codex_sdk" else "0",
        "AAB_CODEX_JSONL_TELEMETRY_ENABLED": None,
        "AAB_CODEX_TELEMETRY_SOURCE": codex_source,
        "AAB_CODEX_TELEMETRY_COST_SOURCE": "subscription_unmetered",
    }


def _env_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_onboarding_state_file(project_root: Path) -> dict[str, Any] | None:
    path = project_root / ".agent-builder" / "onboarding-state.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _was_ready(state: dict[str, Any]) -> bool:
    if state.get("ready") is True or state.get("current_phase") == "ready":
        return True
    for phase in state.get("phases", []):
        if not isinstance(phase, dict):
            continue
        result = phase.get("result") if isinstance(phase.get("result"), dict) else {}
        if phase.get("id") == "ready" and (
            phase.get("status") == "passed" or result.get("ready") is True
        ):
            return True
    return False


def _mark_ready_phase(state: dict[str, Any]) -> None:
    phases = state.setdefault("phases", [])
    for phase in phases:
        if isinstance(phase, dict) and phase.get("id") == "ready":
            phase["status"] = "passed"
            phase["message"] = phase.get("message") or "Runtime switch repaired readiness."
            phase["error"] = None
            result = phase.get("result") if isinstance(phase.get("result"), dict) else {}
            result["ready"] = True
            phase["result"] = result
            return
    phases.append(
        {
            "id": "ready",
            "title": "Ready",
            "status": "passed",
            "message": "Runtime switch repaired readiness.",
            "started_at": None,
            "finished_at": None,
            "result": {"ready": True},
            "error": None,
        }
    )


def _forward_kb_deferred_from_state(state: dict[str, Any]) -> bool:
    phases = state.get("phases", [])
    if not isinstance(phases, list):
        return False
    for phase_id in ("kb_extract", "kb_validate"):
        phase = next(
            (item for item in phases if isinstance(item, dict) and item.get("id") == phase_id),
            {},
        )
        result = phase.get("result") if isinstance(phase.get("result"), dict) else {}
        if result.get("reason") != "forward_engineering_onboarding":
            return False
    return True


def _detect_language(project_root: Path) -> str:
    from autonomous_agent_builder.onboarding import _detect_language as detect

    return detect(project_root)


def _detect_framework(project_root: Path, language: str) -> str:
    from autonomous_agent_builder.onboarding import _detect_framework as detect

    return detect(project_root, language)


def _classify_onboarding_mode(project_root: Path) -> str:
    from autonomous_agent_builder.onboarding import _classify_onboarding_mode as classify

    return classify(project_root)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "autonomous-builder-project"
