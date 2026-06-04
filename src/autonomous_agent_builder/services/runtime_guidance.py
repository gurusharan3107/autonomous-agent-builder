"""Project runtime guidance managed by builder initialization."""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CLAUDE_ROOT_GUIDANCE = "CLAUDE.md"
CLAUDE_NESTED_GUIDANCE = Path(".claude") / "CLAUDE.md"
CODEX_ROOT_GUIDANCE = "AGENTS.md"
ROOT_GUIDANCE = CLAUDE_ROOT_GUIDANCE
NESTED_GUIDANCE = CLAUDE_NESTED_GUIDANCE
ENV_FILE = ".env"

_COMMAND_KEYS = (
    "setup",
    "dev_server",
    "test",
    "lint",
    "typecheck",
    "build",
    "format",
    "smoke_browser_check",
)

_CONTENT_TELEMETRY_KEYS = (
    "AAB_CLAUDE_OTEL_LOG_USER_PROMPTS",
    "AAB_CLAUDE_OTEL_LOG_TOOL_DETAILS",
    "AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT",
    "AAB_CLAUDE_OTEL_LOG_RAW_API_BODIES",
    "OTEL_LOG_USER_PROMPTS",
    "OTEL_LOG_TOOL_DETAILS",
    "OTEL_LOG_TOOL_CONTENT",
    "OTEL_LOG_RAW_API_BODIES",
)

_REQUIRED_DAY0_SECTIONS = (
    "## Project Context",
    "## Builder Contract",
    "## Deterministic Commands",
    "## Builder Agent Runtime Guidance",
    "## Validation Contract",
    "## Telemetry And Observability",
    "## Context Discipline",
    "## Update Rules",
)


def _active_runtime_sdk(project_root: Path) -> str:
    from autonomous_agent_builder.builder_env import builder_source_env_path

    env = _parse_env_file(builder_source_env_path())
    raw_sdk = env.get("RUNTIME_SDK")
    if not raw_sdk:
        try:
            from autonomous_agent_builder.config import get_settings

            raw_sdk = get_settings().runtime.sdk
        except Exception:
            raw_sdk = "claude"
    return _normalize_sdk_value(raw_sdk)


def _normalize_sdk_value(sdk: str | None) -> str:
    try:
        from autonomous_agent_builder.runtime.factory import normalize_sdk

        return normalize_sdk(sdk)
    except Exception:
        return str(sdk or "claude").strip() or "claude"


def _runtime_guidance_kind(sdk: str) -> str:
    return "codex" if str(sdk).startswith("codex") else "claude"


def _runtime_guidance_root_filename(sdk: str) -> str:
    return CODEX_ROOT_GUIDANCE if _runtime_guidance_kind(sdk) == "codex" else CLAUDE_ROOT_GUIDANCE


def _runtime_guidance_paths(project_root: Path) -> tuple[Path, ...]:
    sdk = _active_runtime_sdk(project_root)
    if _runtime_guidance_kind(sdk) == "codex":
        return (Path(CODEX_ROOT_GUIDANCE),)
    return (Path(CLAUDE_ROOT_GUIDANCE), CLAUDE_NESTED_GUIDANCE)


def _inactive_runtime_guidance_paths(sdk: str) -> tuple[Path, ...]:
    if _runtime_guidance_kind(sdk) == "codex":
        return (Path(CLAUDE_ROOT_GUIDANCE), CLAUDE_NESTED_GUIDANCE)
    return (Path(CODEX_ROOT_GUIDANCE),)


def _builder_generated_marker(kind: str) -> str:
    if kind == "codex":
        return "Runtime guidance for Codex SDK agents working in this repository."
    return "Runtime guidance for Claude Agent SDK agents working in this repository."


def _is_builder_generated_text(text: str) -> bool:
    return _builder_generated_marker("claude") in text or _builder_generated_marker("codex") in text


def _migrate_builder_runtime_guidance(root: Path, *, sdk: str, rendered: str) -> Path | None:
    target = root / _runtime_guidance_root_filename(sdk)
    if target.exists():
        return None
    for relative_path in _inactive_runtime_guidance_paths(sdk):
        source = root / relative_path
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8", errors="ignore")
        if not _is_builder_generated_text(text):
            continue
        source.rename(target)
        target.write_text(rendered, encoding="utf-8")
        return source
    return None


def find_project_runtime_guidance(project_root: Path) -> Path | None:
    """Return the project guidance file loaded by the selected runtime."""
    root = project_root.resolve()
    for relative_path in _runtime_guidance_paths(root):
        path = root / relative_path
        if path.is_file():
            return path
    return None


def ensure_project_runtime_guidance(
    project_root: Path,
    *,
    project_name: str,
    language: str,
    framework: str | None = None,
    mode: str = "forward_engineering",
    app_type: str | None = None,
    persistence: str | None = None,
    package_manager: str | None = None,
    commands: dict[str, str] | None = None,
    entrypoints: list[str] | None = None,
    test_surfaces: list[str] | None = None,
) -> dict[str, Any]:
    """Create base project guidance for the selected runtime when missing."""
    root = project_root.resolve()
    sdk = _active_runtime_sdk(root)
    kind = _runtime_guidance_kind(sdk)
    rendered = render_project_runtime_guidance(
        project_name=project_name,
        sdk=sdk,
        language=language,
        framework=framework,
        mode=mode,
        app_type=app_type,
        persistence=persistence,
        package_manager=package_manager,
        commands=commands,
        entrypoints=entrypoints,
        test_surfaces=test_surfaces,
    )
    existing = find_project_runtime_guidance(root)
    if existing is not None:
        return {
            "created": False,
            "status": "existing",
            "sdk": sdk,
            "kind": kind,
            "path": str(existing),
            "relative_path": str(existing.relative_to(root)),
        }

    path = root / _runtime_guidance_root_filename(sdk)
    migrated_from = _migrate_builder_runtime_guidance(root, sdk=sdk, rendered=rendered)
    if migrated_from is not None:
        return {
            "created": False,
            "status": "migrated",
            "sdk": sdk,
            "kind": kind,
            "path": str(path),
            "relative_path": path.name,
            "previous_path": str(migrated_from),
        }

    path.write_text(rendered, encoding="utf-8")
    return {
        "created": True,
        "status": "created",
        "sdk": sdk,
        "kind": kind,
        "path": str(path),
        "relative_path": path.name,
    }


def refresh_project_runtime_guidance(
    project_root: Path,
    *,
    project_name: str | None = None,
    mode: str | None = None,
    language: str | None = None,
    framework: str | None = None,
    scan_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Refresh existing builder-generated runtime guidance with discovered app commands."""
    root = project_root.resolve()
    state = _read_onboarding_state(root)
    repo = state.get("repo") if isinstance(state.get("repo"), dict) else {}
    resolved_name = str(project_name or repo.get("name") or root.name)
    resolved_mode = str(mode or state.get("onboarding_mode") or "forward_engineering")
    if resolved_mode not in {"forward_engineering", "reverse_engineering"}:
        resolved_mode = "forward_engineering"
    resolved_language = str(language or repo.get("language") or _detect_language(root) or "unknown")
    resolved_framework = str(
        framework
        or repo.get("framework")
        or _detect_framework(root, resolved_language)
        or "unknown"
    )
    resolved_scan = (
        scan_summary
        if isinstance(scan_summary, dict)
        else state.get("scan_summary")
        if isinstance(state.get("scan_summary"), dict)
        else {}
    )
    context = infer_runtime_guidance_context(
        root,
        mode=resolved_mode,
        language=resolved_language,
        framework=resolved_framework,
        scan_summary=resolved_scan,
    )

    files = (
        ("claude", Path(CLAUDE_ROOT_GUIDANCE)),
        ("claude", CLAUDE_NESTED_GUIDANCE),
        ("codex_sdk", Path(CODEX_ROOT_GUIDANCE)),
    )
    updated: list[str] = []
    unchanged: list[str] = []
    skipped: list[dict[str, str]] = []
    missing: list[str] = []
    for sdk, relative_path in files:
        path = root / relative_path
        if not path.exists():
            missing.append(relative_path.as_posix())
            continue
        current = path.read_text(encoding="utf-8", errors="ignore")
        if not _is_builder_generated_text(current):
            skipped.append({"path": relative_path.as_posix(), "reason": "not_builder_generated"})
            continue
        rendered = render_project_runtime_guidance(
            project_name=resolved_name,
            sdk=sdk,
            **context,
        )
        if current == rendered:
            unchanged.append(relative_path.as_posix())
            continue
        path.write_text(rendered, encoding="utf-8")
        updated.append(relative_path.as_posix())

    return {
        "status": "updated" if updated else "unchanged",
        "project_root": str(root),
        "updated_files": updated,
        "unchanged_files": unchanged,
        "skipped_files": skipped,
        "missing_files": missing,
        "commands": context["commands"],
        "mode": context["mode"],
        "language": context["language"],
        "framework": context["framework"],
        "package_manager": context["package_manager"],
        "entrypoints": context.get("entrypoints", []),
        "test_surfaces": context.get("test_surfaces", []),
    }


def update_project_context_block(
    project_root: Path,
    *,
    language: str | None = None,
    framework: str | None = None,
    app_type: str | None = None,
    persistence: str | None = None,
    package_manager: str | None = None,
) -> dict[str, Any]:
    """Surgically rewrite the 5 Project Context fields in target CLAUDE.md.

    Preserves the heading, ``Mode`` line, the trailing ``AGENTS.md`` note,
    and every other section. Only fields with non-None values are updated.

    This is the deterministic post-chat handoff path: after
    ``init-project-chat`` completes its interview, the orchestrator maps
    the structured ``AskUserQuestion`` answers to project-context fields
    and calls this function. Full re-rendering via
    ``render_project_runtime_guidance`` would discard any
    ``## Deterministic Commands`` content code-gen has rightfully filled
    in, which is why this is surgical rather than full-rewrite.

    Returns a dict with ``status`` (``updated`` | ``unchanged`` |
    ``missing`` | ``skipped``), the ``path`` operated on, and the set of
    ``fields_changed``.
    """
    root = project_root.resolve()
    target = find_project_runtime_guidance(root)
    if target is None:
        return {
            "status": "missing",
            "path": str(root / CLAUDE_ROOT_GUIDANCE),
            "fields_changed": [],
        }

    text = target.read_text(encoding="utf-8")
    if not _is_builder_generated_text(text):
        return {
            "status": "skipped",
            "path": str(target),
            "reason": "not_builder_generated",
            "fields_changed": [],
        }

    updates: dict[str, str | None] = {
        "Language": language,
        "Framework": framework,
        "App type": app_type,
        "Persistence": persistence,
        "Package manager": package_manager,
    }
    # Drop None values — only fields the caller specified are touched.
    pending = {key: _known(value) for key, value in updates.items() if value is not None}
    if not pending:
        return {
            "status": "unchanged",
            "path": str(target),
            "fields_changed": [],
        }

    lines = text.splitlines(keepends=True)
    in_block = False
    changed: list[str] = []
    for idx, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped == "## Project Context":
            in_block = True
            continue
        if in_block and stripped.startswith("## "):
            # Reached the next section heading without finding all fields.
            break
        if not in_block:
            continue
        for field, new_value in list(pending.items()):
            prefix = f"- {field}: "
            if stripped.startswith(prefix):
                new_line = f"{prefix}{new_value}\n"
                if line != new_line:
                    lines[idx] = new_line
                    changed.append(field)
                pending.pop(field)
                break
        if not pending:
            break

    if not changed:
        return {
            "status": "unchanged",
            "path": str(target),
            "fields_changed": [],
        }

    target.write_text("".join(lines), encoding="utf-8")
    return {
        "status": "updated",
        "path": str(target),
        "fields_changed": changed,
    }


def ensure_project_telemetry_env(
    project_root: Path,
    *,
    project_name: str,
    endpoint: str = "http://localhost:4318",
) -> dict[str, Any]:
    """Ensure Builder source `.env` has runtime-specific telemetry defaults."""
    root = project_root.resolve()
    from autonomous_agent_builder.builder_env import builder_source_env_path
    from autonomous_agent_builder.runtime.factory import resolve_runtime_config
    from autonomous_agent_builder.services.runtime_settings import (
        ensure_runtime_env,
        parse_env_file,
    )

    env = parse_env_file(builder_source_env_path())
    overrides = {
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

    return ensure_runtime_env(
        root,
        project_name=project_name,
        config=resolve_runtime_config(**overrides),
        endpoint=endpoint,
    )


def render_project_telemetry_env(
    *,
    project_name: str,
    endpoint: str = "http://localhost:4318",
) -> str:
    """Render safe Builder-source runtime telemetry defaults for a project."""
    service_name = _slug(project_name)
    return (
        "# Autonomous Agent Builder runtime telemetry\n"
        'RUNTIME_SDK="claude"\n'
        'RUNTIME_PROVIDER="claude_agent_sdk"\n'
        'RUNTIME_MODEL="sonnet"\n'
        'RUNTIME_TRACING="builder"\n'
        "AAB_CLAUDE_OTEL_ENABLED=1\n"
        f"AAB_CLAUDE_OTEL_ENDPOINT={endpoint}\n"
        f"AAB_CLAUDE_OTEL_SERVICE_NAME={service_name}\n"
        "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID=true\n"
        "AAB_CLAUDE_OTEL_DETAILED_BETA_TRACING=1\n"
        f"AAB_CLAUDE_OTEL_BETA_TRACING_ENDPOINT={endpoint}\n"
        "AAB_CLAUDE_OTEL_RESOURCE_ATTRIBUTES="
        f"service.version=0.1.0,deployment.environment=local,builder.project={service_name},"
        "builder.runtime=claude_agent_sdk,builder.goal=voice_first_delivery_os\n"
        "AAB_CLAUDE_OTEL_LOG_USER_PROMPTS=0\n"
        "AAB_CLAUDE_OTEL_LOG_TOOL_DETAILS=0\n"
        "AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT=0\n"
        "AAB_CLAUDE_OTEL_LOG_RAW_API_BODIES=0\n"
        "AAB_CODEX_RUNTIME_TELEMETRY_ENABLED=0\n"
        "AAB_CODEX_TELEMETRY_SOURCE=codex_runtime_events\n"
        "AAB_CODEX_TELEMETRY_COST_SOURCE=subscription_unmetered\n"
    )


def render_project_runtime_guidance(
    *,
    project_name: str,
    sdk: str = "claude",
    language: str,
    framework: str | None = None,
    mode: str = "forward_engineering",
    app_type: str | None = None,
    persistence: str | None = None,
    package_manager: str | None = None,
    commands: dict[str, str] | None = None,
    entrypoints: list[str] | None = None,
    test_surfaces: list[str] | None = None,
) -> str:
    """Render the default target-repo guidance for the selected runtime."""
    resolved_mode = (
        mode if mode in {"forward_engineering", "reverse_engineering"} else "forward_engineering"
    )
    resolved_sdk = _normalize_sdk_value(sdk)
    command_values = _normalize_commands(commands)
    renderer = (
        _render_codex_guidance
        if _runtime_guidance_kind(resolved_sdk) == "codex"
        else _render_claude_guidance
    )
    if resolved_mode == "reverse_engineering":
        return renderer(
            project_name=project_name,
            mode=resolved_mode,
            language=language,
            framework=framework,
            app_type=app_type,
            persistence=persistence,
            package_manager=package_manager,
            commands=command_values,
            entrypoints=entrypoints or [],
            test_surfaces=test_surfaces or [],
        )
    return renderer(
        project_name=project_name,
        mode=resolved_mode,
        language=language,
        framework=framework,
        app_type=app_type,
        persistence=persistence,
        package_manager=package_manager,
        commands=command_values,
    )


def infer_runtime_guidance_context(
    project_root: Path,
    *,
    mode: str,
    language: str,
    framework: str | None = None,
    scan_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer deterministic, tech-stack-agnostic guidance fields from repo files."""
    root = project_root.resolve()
    package_manager = _detect_package_manager(root)
    commands = _discover_commands(root, language=language)
    entrypoints = _discover_entrypoints(root, scan_summary=scan_summary)
    test_surfaces = _discover_test_surfaces(root)
    return {
        "mode": mode,
        "language": language or "unknown",
        "framework": framework or _detect_framework(root, language),
        "app_type": _detect_app_type(root, scan_summary=scan_summary),
        "persistence": _detect_persistence(root),
        "package_manager": package_manager,
        "commands": commands,
        "entrypoints": entrypoints,
        "test_surfaces": test_surfaces,
    }


def runtime_guidance_contract_status(project_root: Path) -> dict[str, Any]:
    """Return a readiness-friendly summary of active Day-0 contract coverage."""
    sdk = _active_runtime_sdk(project_root)
    kind = _runtime_guidance_kind(sdk)
    path = find_project_runtime_guidance(project_root)
    if path is None:
        return {
            "ok": False,
            "status": "missing",
            "sdk": sdk,
            "kind": kind,
            "expected_path": _runtime_guidance_root_filename(sdk),
            "path": "",
            "builder_generated": False,
            "missing_sections": list(_REQUIRED_DAY0_SECTIONS),
            "deterministic_command_slots": False,
            "commands_filled": False,
            "unknown_command_count": len(list(_command_labels())),
        }
    text = path.read_text(encoding="utf-8", errors="ignore")
    builder_generated = _builder_generated_marker(kind) in text
    missing_sections = [section for section in _REQUIRED_DAY0_SECTIONS if section not in text]
    command_slots = all(f"- {label}:" in text for label in _command_labels())
    unknown_command_count = sum(
        1 for label in _command_labels()
        if re.search(rf"- {re.escape(label)}:.*`unknown`", text)
    )
    commands_filled = command_slots and unknown_command_count == 0
    if not builder_generated:
        return {
            "ok": True,
            "status": "preserved_existing",
            "sdk": sdk,
            "kind": kind,
            "expected_path": _runtime_guidance_root_filename(sdk),
            "path": str(path),
            "builder_generated": False,
            "missing_sections": missing_sections,
            "deterministic_command_slots": command_slots,
            "commands_filled": commands_filled,
            "unknown_command_count": unknown_command_count,
        }
    ok = not missing_sections and command_slots
    return {
        "ok": ok,
        "status": "generated_contract" if ok else "generated_contract_incomplete",
        "sdk": sdk,
        "kind": kind,
        "expected_path": _runtime_guidance_root_filename(sdk),
        "path": str(path),
        "builder_generated": True,
        "missing_sections": missing_sections,
        "deterministic_command_slots": command_slots,
        "commands_filled": commands_filled,
        "unknown_command_count": unknown_command_count,
    }


def telemetry_env_status(project_root: Path) -> dict[str, Any]:
    """Return readiness status for the Builder-owned runtime telemetry lane."""
    root = project_root.resolve()
    from autonomous_agent_builder.builder_env import builder_source_env_path

    path = builder_source_env_path()
    if not path.exists():
        return {
            "ok": False,
            "status": "missing",
            "path": str(path),
            "enabled": False,
            "endpoint": "",
            "content_safe": True,
            "unsafe_keys": [],
        }
    env = _parse_env_file(path)
    from autonomous_agent_builder.services.runtime_settings import telemetry_state

    state = telemetry_state(root)
    active_lane = str(state.get("active_lane") or "")
    active_enabled = bool(state.get("active_enabled"))
    inactive_disabled = bool(state.get("inactive_disabled"))
    claude = state.get("claude", {}) if isinstance(state.get("claude"), dict) else {}
    codex = state.get("codex", {}) if isinstance(state.get("codex"), dict) else {}
    endpoint = str(claude.get("endpoint") or "").strip()
    from autonomous_agent_builder.observability.collector import otel_collector_reachability

    collector = otel_collector_reachability(endpoint)
    unsafe_keys = [key for key in _CONTENT_TELEMETRY_KEYS if _truthy(env.get(key))]
    collector_ok = (
        active_lane != "claude"
        or not active_enabled
        or collector.get("reachable") is True
        or collector.get("checked") is False
    )
    config_ok = active_enabled and inactive_disabled and not unsafe_keys
    ok = config_ok and collector_ok
    if ok:
        status = "configured"
    elif active_lane == "claude" and active_enabled and collector.get("checked"):
        status = str(collector.get("status") or "collector_unreachable")
    else:
        status = "incomplete"
    return {
        "ok": ok,
        "config_ok": config_ok,
        "status": status,
        "path": str(path),
        "enabled": active_enabled,
        "active_lane": active_lane,
        "inactive_disabled": inactive_disabled,
        "endpoint": endpoint,
        "endpoint_configured": bool(endpoint),
        "collector": collector,
        "collector_reachable": collector.get("reachable"),
        "claude_enabled": bool(claude.get("enabled")),
        "codex_enabled": bool(codex.get("enabled")),
        "codex_source": str(codex.get("source") or ""),
        "content_safe": not unsafe_keys,
        "unsafe_keys": unsafe_keys,
    }


def _render_claude_guidance(
    *,
    project_name: str,
    mode: str,
    language: str,
    framework: str | None,
    app_type: str | None,
    persistence: str | None,
    package_manager: str | None,
    commands: dict[str, str],
    entrypoints: list[str] | None = None,
    test_surfaces: list[str] | None = None,
) -> str:
    if mode == "reverse_engineering":
        return _render_reverse_guidance(
            project_name=project_name,
            language=language,
            framework=framework,
            app_type=app_type,
            persistence=persistence,
            package_manager=package_manager,
            commands=commands,
            entrypoints=entrypoints or [],
            test_surfaces=test_surfaces or [],
        )
    return f"""# {project_name}

Runtime guidance for Claude Agent SDK agents working in this repository.

## Project Context
- Mode: forward_engineering
- Language: {_known(language)}
- Framework: {_known(framework)}
- App type: {_known(app_type)}
- Persistence: {_known(persistence)}
- Package manager: {_known(package_manager)}
- `AGENTS.md`, when present, is for Codex or other coding agents. This file is the Claude Agent SDK runtime contract.

## Builder Contract
- Autonomous Agent Builder owns workflow, model, effort, tool, MCP, context strategy, and recovery decisions.
- The user describes product intent; do not ask the user to choose internal phases, tools, models, MCPs, or effort levels.
- Keep backlog, task, approval, validation, and shipping state visible through builder-owned product state.
- If blocked, return the smallest actionable blocker with evidence and the next recoverable state.

## Deterministic Commands
{_render_command_lines(commands)}

When a command becomes known and repeatable, update this section. Prefer repo scripts over ad hoc shell snippets.

## Builder Agent Runtime Guidance
{_render_builder_agent_runtime_guidance()}

## Initial Implementation Rules
- Start with the smallest useful vertical slice.
- Create deterministic setup, test, lint, and run commands as early as possible.
- Add tests with the first meaningful behavior.
- Keep generated code simple, local-first, and easy to inspect unless the user requested otherwise.
- Do not introduce cloud services, auth, payments, queues, or external dependencies unless explicitly required.

## Validation Contract
- Do not report completion without running the narrowest meaningful validation.
- For UI work, verify through visible browser navigation and controls, not only direct URLs.
- A route is not accepted unless a user can discover it through visible app navigation or controls.
- If no validation command exists, add or recommend the smallest repeatable validation command.
- Record validation gaps as builder-owned backlog or memory only when they are reusable.

## Telemetry And Observability
- Selected runtime telemetry: enabled
- Claude SDK telemetry: enabled only when `RUNTIME_SDK=claude`
- Codex runtime telemetry: enabled only when `RUNTIME_SDK` starts with `codex_`
- OTEL endpoint: configured as `http://localhost:4318`; readiness must also show whether the local collector is reachable.
- Use builder-owned logs/history as the primary evidence lane.
- Do not export raw prompts, tool inputs, tool outputs, secrets, or user data by default.

## Context Discipline
- Read local manifests, nearby code, and maintained docs before broad search.
- Keep summaries compact and evidence-based.
- Do not duplicate backlog, transcript, or long design notes here.
- Promote stable project lessons here only when they affect future runtime behavior.

## Update Rules
Update this file when any of these become known:
- deterministic setup/run/test/lint/build commands
- app entrypoint or dev-server command
- smoke/browser validation path
- telemetry policy
- durable project constraints
- required local environment variables

Do not use this file as a changelog, transcript, backlog, or design document.
"""


def _render_codex_guidance(
    *,
    project_name: str,
    mode: str,
    language: str,
    framework: str | None,
    app_type: str | None,
    persistence: str | None,
    package_manager: str | None,
    commands: dict[str, str],
    entrypoints: list[str] | None = None,
    test_surfaces: list[str] | None = None,
) -> str:
    if mode == "reverse_engineering":
        primary_entrypoints = f"- Primary entrypoints: {_inline_list(entrypoints or [])}\n- Test surfaces: {_inline_list(test_surfaces or [])}\n"
        mode_rules = """## Reverse Engineering Rules
- Retrieve before changing code.
- Identify app entrypoints, data model, tests, runtime config, and deployment assumptions before implementation.
- Preserve existing architecture, scripts, conventions, and user work.
- If the repo has multiple apps or packages, prove the target workspace before editing.
"""
    else:
        primary_entrypoints = ""
        mode_rules = """## Forward Engineering Rules
- Start with product clarification in the top-level Agent page lane when requirements are incomplete.
- Convert agreed scope into backlog before implementation.
- Keep sprint planning and design as read-only artifacts before mutating task workspaces.
- During implementation, use the selected Codex model and effort for the task at hand.
- Ship only after validation evidence, approval state, and feature status are updated.
"""
    return f"""# {project_name}

Runtime guidance for Codex SDK agents working in this repository.

## Project Context
- Mode: {mode}
- Language: {_known(language)}
- Framework: {_known(framework)}
- App type: {_known(app_type)}
- Persistence: {_known(persistence)}
- Package manager: {_known(package_manager)}
{primary_entrypoints}- `CLAUDE.md`, when present, is for Claude Agent SDK agents. This file is the Codex runtime contract.

## Builder Contract
- Autonomous Agent Builder owns workflow, model, effort, tool, MCP, context strategy, and recovery decisions.
- Use Codex-native project instructions from this `AGENTS.md` file before doing work.
- Use Codex strengths for repository analysis, patching, tests, browser validation, and context-efficient implementation.
- Keep backlog, task, approval, validation, telemetry, and shipping state visible through builder-owned product state.
- If blocked, return the smallest actionable blocker with evidence and the next recoverable state.

## Deterministic Commands
{_render_command_lines(commands)}

## Builder Agent Runtime Guidance
{_render_builder_agent_runtime_guidance()}

{mode_rules}
## Validation Contract
- Do not report completion without running the narrowest meaningful existing validation.
- For web UI work, browser-visible proof is required; curl-only checks do not prove the user workflow.
- Capture failures as evidence and either fix them or mark the task blocked with the exact failing command.
- A route is not accepted unless a user can discover it through visible navigation or documented entrypoints.

## Telemetry And Observability
- Selected runtime telemetry: enabled.
- Codex runtime telemetry: enabled when `RUNTIME_SDK` starts with `codex_`.
- Claude OTEL telemetry: disabled while Codex is selected.
- Use builder-visible cost, turns, duration, runtime, model, and effort data when analyzing Codex runs.
- Do not export raw prompts, tool bodies, secrets, or credentials into telemetry.

## Context Discipline
- Retrieve local guidance before broad file walking.
- Keep implementation prompts compact and task-specific.
- Prefer existing commands, tests, and framework conventions over inventing new tooling.
- Keep sprint-level plan/design distinct from task-level implementation notes.

## Update Rules
Update this file only when stable project guidance changes, such as:
- project mission or first user journey
- canonical setup/test/build/browser commands
- validation and shipping rules
- telemetry policy
- durable project constraints
- required local environment variables

Do not use this file as a changelog, transcript, backlog, or design document.
"""


def _render_reverse_guidance(
    *,
    project_name: str,
    language: str,
    framework: str | None,
    app_type: str | None,
    persistence: str | None,
    package_manager: str | None,
    commands: dict[str, str],
    entrypoints: list[str],
    test_surfaces: list[str],
) -> str:
    return f"""# {project_name}

Runtime guidance for Claude Agent SDK agents working in this repository.

## Project Context
- Mode: reverse_engineering
- Language: {_known(language)}
- Framework: {_known(framework)}
- App type: {_known(app_type)}
- Persistence: {_known(persistence)}
- Package manager: {_known(package_manager)}
- Primary entrypoints: {_inline_list(entrypoints)}
- Test surfaces: {_inline_list(test_surfaces)}
- `AGENTS.md`, when present, is for Codex or other coding agents. This file is the Claude Agent SDK runtime contract.

## Builder Contract
- Autonomous Agent Builder owns workflow, model, effort, tool, MCP, context strategy, and recovery decisions.
- The user should not need to explain the repo structure if it can be discovered.
- Preserve existing architecture, scripts, conventions, and user work.
- Keep backlog, task, approval, validation, and shipping state visible through builder-owned product state.
- If blocked, return the smallest actionable blocker with evidence and the next recoverable state.

## Deterministic Commands
{_render_command_lines(commands)}

During onboarding, discover commands from manifests, README files, CI config, Makefiles, package scripts, task runners, and local docs. Prefer existing repo commands over inventing new ones.

## Builder Agent Runtime Guidance
{_render_builder_agent_runtime_guidance()}

## Reverse Engineering Rules
- Retrieve before changing code.
- Identify the app entrypoints, data model, test strategy, runtime configuration, and deployment assumptions before implementation.
- Do not replace existing architecture unless the task explicitly requires it.
- Do not normalize style, tooling, folder layout, or dependencies unrelated to the task.
- Preserve user changes and uncommitted work.
- If the repo has multiple apps or packages, prove the target workspace before editing.

## Validation Contract
- Do not report completion without running the narrowest meaningful existing validation.
- If existing validation is broken before your change, capture the baseline failure and avoid claiming you caused or fixed unrelated failures.
- For UI work, verify through visible browser navigation and controls when the app can run locally.
- For APIs, CLIs, and libraries, verify through existing tests or the smallest deterministic command.
- If validation commands are missing or unclear, document the gap and propose the smallest repo-native command to add.

## Knowledge And Documentation
- Use discovered repo docs as source of truth when they match code.
- If docs conflict with code, trust code/runtime evidence first and record the mismatch.
- Update maintained docs only when behavior or setup actually changes.
- Do not turn this file into a full architecture document; link to or create the owning doc instead.

## Telemetry And Observability
- Selected runtime telemetry: enabled
- Claude SDK telemetry: enabled only when `RUNTIME_SDK=claude`
- Codex runtime telemetry: enabled only when `RUNTIME_SDK` starts with `codex_`
- OTEL endpoint: configured as `http://localhost:4318`; readiness must also show whether the local collector is reachable.
- Runtime logs: unknown
- Error tracker: unknown
- Use builder-owned logs/history as the primary evidence lane.
- Do not export raw prompts, tool inputs, tool outputs, secrets, or user data by default.

## Context Discipline
- Read manifests, README, CI config, docs, and nearby code before broad search.
- Prefer bounded retrieval and exact commands over exploratory wandering.
- Keep summaries compact and evidence-based.
- Promote stable repo lessons here only when they affect future runtime behavior.

## Update Rules
Update this file when onboarding discovers:
- deterministic setup/run/test/lint/build commands
- app entrypoints
- package/workspace boundaries
- local environment requirements
- smoke/browser validation path
- telemetry/logging policy
- durable project constraints

Do not use this file as a changelog, transcript, backlog, or design document.
"""


def _normalize_commands(commands: dict[str, str] | None) -> dict[str, str]:
    values = {key: "unknown" for key in _COMMAND_KEYS}
    for key, value in (commands or {}).items():
        if key in values and str(value or "").strip():
            values[key] = str(value).strip()
    return values


def _render_builder_agent_runtime_guidance() -> str:
    return """- `code-gen`: read this file before implementation, prefer the listed setup/run/test/lint/build commands, and create or update repo-native scripts when repeatable validation is missing.
- `feature-verifier`: validate acceptance criteria through visible product behavior first, then add or repair durable Playwright/acceptance tests for the proven behavior.
- `build-verifier`: run the narrowest deterministic build, lint, test, and browser-smoke commands available here; if a command is unknown, report the validation gap instead of inventing an ad hoc proof.
- `pr-creator`: summarize exact changed files and validation evidence from prior agent runs; rerun only missing deterministic evidence needed for a trustworthy handoff.
- `optimization-agent`: start from builder preflight evidence, telemetry, observability, and logs, then update these command slots or add deterministic scripts only when the recommendation is workspace-scoped and command-validated.
- Any new script must have a trigger: record which builder phase or agent should use it, the exact command, and the evidence it replaces."""


def _render_command_lines(commands: dict[str, str]) -> str:
    return "\n".join(
        f"- {label}: `{commands[key]}`"
        for key, label in zip(_COMMAND_KEYS, _command_labels(), strict=True)
    )


def _command_labels() -> tuple[str, ...]:
    return (
        "Setup",
        "Dev server",
        "Test",
        "Lint",
        "Typecheck",
        "Build",
        "Format",
        "Smoke/browser check",
    )


def _known(value: str | None) -> str:
    text = str(value or "").strip()
    return text if text else "unknown"


def _inline_list(values: list[str]) -> str:
    clean = [value for value in values if str(value).strip()]
    return ", ".join(clean[:8]) if clean else "unknown"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "autonomous-builder-project"


def _parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return env
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _read_onboarding_state(project_root: Path) -> dict[str, Any]:
    path = project_root / ".agent-builder" / "onboarding-state.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _detect_language(project_root: Path) -> str:
    if (project_root / "package.json").exists():
        return "node"
    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        return "python"
    if (project_root / "go.mod").exists():
        return "go"
    if (project_root / "Cargo.toml").exists():
        return "rust"
    if any(
        (project_root / name).exists() for name in ("pom.xml", "build.gradle", "build.gradle.kts")
    ):
        return "java"
    return "unknown"


def _detect_package_manager(project_root: Path) -> str:
    if (project_root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_root / "yarn.lock").exists():
        return "yarn"
    if (project_root / "package-lock.json").exists() or (project_root / "package.json").exists():
        return "npm"
    if (project_root / "uv.lock").exists():
        return "uv"
    if (project_root / "poetry.lock").exists():
        return "poetry"
    if (project_root / "pyproject.toml").exists():
        return "pip"
    if (project_root / "requirements.txt").exists():
        return "pip"
    if (project_root / "Cargo.toml").exists():
        return "cargo"
    if (project_root / "go.mod").exists():
        return "go"
    if (project_root / "pom.xml").exists():
        return "maven"
    if (project_root / "build.gradle").exists() or (project_root / "build.gradle.kts").exists():
        return "gradle"
    return "unknown"


def _detect_framework(project_root: Path, language: str) -> str:
    if language == "python":
        text = (
            _read_text(project_root / "pyproject.toml")
            + "\n"
            + _read_text(project_root / "requirements.txt")
        )
        lowered = text.lower()
        if "fastapi" in lowered:
            return "fastapi"
        if "django" in lowered or (project_root / "manage.py").exists():
            return "django"
        if "flask" in lowered:
            return "flask"
    if language in {"node", "nodejs", "javascript", "typescript"}:
        package = _read_json(project_root / "package.json")
        deps = (
            {**package.get("dependencies", {}), **package.get("devDependencies", {})}
            if isinstance(package, dict)
            else {}
        )
        for framework in ("next", "vite", "express", "react", "svelte", "vue"):
            if framework in deps:
                return framework
    return "unknown"


def _detect_app_type(project_root: Path, scan_summary: dict[str, Any] | None = None) -> str:
    scan = scan_summary or {}
    if scan.get("has_frontend") or (project_root / "frontend").exists():
        return "web"
    if scan.get("has_api") or (project_root / "api").exists() or (project_root / "server").exists():
        return "api"
    if (project_root / "package.json").exists() or (project_root / "manage.py").exists():
        return "web"
    if any((project_root / name).exists() for name in ("main.py", "app.py", "server.py")):
        return "app"
    return "unknown"


def _detect_persistence(project_root: Path) -> str:
    text = "\n".join(
        _read_text(path)
        for path in (
            project_root / "pyproject.toml",
            project_root / "requirements.txt",
            project_root / "package.json",
            project_root / "README.md",
        )
    ).lower()
    if "sqlite" in text:
        return "sqlite"
    if "postgres" in text or "psycopg" in text:
        return "postgres"
    if "mysql" in text:
        return "mysql"
    return "unknown"


def _discover_commands(project_root: Path, *, language: str) -> dict[str, str]:
    commands = _normalize_commands(None)
    # The npm/pnpm script-derivation branch should only fire when there is an
    # actual `package.json`. Otherwise `_read_json` returns `{}`, scripts is
    # `{}`, and the branch still entered — synthesizing nonsense like
    # `Setup: unknown install` for empty/Python workspaces.
    package_json_path = project_root / "package.json"
    package = _read_json(package_json_path) if package_json_path.exists() else {}
    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
    if package_json_path.exists() and isinstance(scripts, dict):
        runner = _detect_package_manager(project_root)
        prefix = "pnpm" if runner == "pnpm" else "npm run"
        commands["dev_server"] = _script_command(prefix, scripts, ("dev", "start"))
        commands["test"] = _script_command(prefix, scripts, ("test",))
        commands["lint"] = _script_command(prefix, scripts, ("lint",))
        commands["typecheck"] = _script_command(prefix, scripts, ("typecheck", "tsc"))
        commands["build"] = _script_command(prefix, scripts, ("build",))
        commands["format"] = _script_command(prefix, scripts, ("format",))
        commands["setup"] = "npm install" if runner == "npm" else f"{runner} install"
    if language == "python":
        if (project_root / "pyproject.toml").exists():
            commands["setup"] = "python -m pip install -e ."
        elif (project_root / "requirements.txt").exists():
            commands["setup"] = "python -m pip install -r requirements.txt"
        if (project_root / "pytest.ini").exists() or (project_root / "tests").exists():
            commands["test"] = "pytest"
        if (project_root / "ruff.toml").exists() or "ruff" in _read_text(
            project_root / "pyproject.toml"
        ).lower():
            commands["lint"] = "ruff check ."
        if (project_root / "manage.py").exists():
            commands["dev_server"] = "python manage.py runserver"
    if language == "go":
        commands["test"] = "go test ./..."
        commands["build"] = "go build ./..."
    if language == "rust":
        commands["test"] = "cargo test"
        commands["build"] = "cargo build"
        commands["format"] = "cargo fmt"
    if language == "java":
        if (project_root / "pom.xml").exists():
            commands["test"] = "mvn test"
            commands["build"] = "mvn package"
        elif (project_root / "build.gradle").exists() or (
            project_root / "build.gradle.kts"
        ).exists():
            commands["test"] = "./gradlew test"
            commands["build"] = "./gradlew build"
    return commands


def _script_command(prefix: str, scripts: dict[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        if name in scripts:
            return f"{prefix} {name}" if prefix.endswith("run") else f"{prefix} {name}"
    return "unknown"


def _discover_entrypoints(
    project_root: Path, scan_summary: dict[str, Any] | None = None
) -> list[str]:
    scan = scan_summary or {}
    scanned = scan.get("entrypoints")
    if isinstance(scanned, list) and scanned:
        return [str(value) for value in scanned[:10]]
    matches: set[str] = set()
    for pattern in (
        "main.py",
        "app.py",
        "server.py",
        "manage.py",
        "src/**/main.py",
        "src/main.*",
        "cmd/**/main.go",
    ):
        for match in project_root.glob(pattern):
            if match.is_file():
                matches.add(match.relative_to(project_root).as_posix())
    return sorted(matches)[:10]


def _discover_test_surfaces(project_root: Path) -> list[str]:
    surfaces: list[str] = []
    for name in ("tests", "test", "__tests__", "spec"):
        if (project_root / name).exists():
            surfaces.append(name)
    for pattern in ("*.test.*", "*.spec.*", "src/**/*.test.*", "src/**/*.spec.*"):
        for match in project_root.glob(pattern):
            if match.is_file():
                surfaces.append(match.relative_to(project_root).as_posix())
                if len(surfaces) >= 8:
                    return surfaces
    return surfaces


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
