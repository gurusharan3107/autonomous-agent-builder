"""Agent commands — chat sessions and runtime metadata."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.agents.documentation_bridge import run_documentation_refresh_bridge
from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    BuilderConnectivityError,
    get_client,
    handle_api_error,
    request_json,
)
from autonomous_agent_builder.cli.local_fallback import (
    load_local_agent_history,
    load_local_agent_meta,
    load_local_agent_sessions,
)
from autonomous_agent_builder.cli.output import emit_error, render, table, truncate
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.runtime import (
    create_runtime,
    resolve_runtime_config,
    validate_runtime_config,
)
from autonomous_agent_builder.services.runtime_settings import (
    persist_runtime_settings,
    runtime_settings_payload,
)

app = typer.Typer(
    help=(
        "Agent chat sessions and runtime metadata.\n\n"
        "Start here:\n"
        "  builder agent sessions --json\n"
        "  builder agent history --json\n"
        "  builder agent meta --json\n"
        "  builder agent runtime show --json\n"
        "  builder agent documentation-refresh --validation kb-validate.json --json\n"
    )
)

runtime_app = typer.Typer(help="Show, probe, and update the active agent runtime.")
app.add_typer(runtime_app, name="runtime")

# Subgroup for Managed Agents (claude_managed lane) provisioning. Phase B
# adds `setup` for one-time + idempotent agent / environment / subagent
# creation. Phase C-E will extend this with `vault add`, `skill upload`, etc.
managed_agents_app = typer.Typer(
    help=(
        "Provision and inspect Anthropic Managed Agents resources for the "
        "claude_managed runtime lane (RUNTIME_SDK=claude_managed)."
    ),
)
runtime_app.add_typer(managed_agents_app, name="managed-agents")


@managed_agents_app.command("setup")
def managed_agents_setup_command(
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON output suitable for agent consumption."
    ),
    role: list[str] | None = typer.Option(
        None,
        "--role",
        help=(
            "Subset of top-level roles to provision (repeatable). Default: "
            "all 11 builder roles. Subagents are auto-resolved from the "
            "selected roles' rosters."
        ),
    ),
) -> None:
    """Provision MA environment + agents + subagents.

    Idempotent — re-running picks up existing IDs from
    `.agent-builder/managed_agents.json` and only creates what's missing.
    Requires ANTHROPIC_API_KEY with Managed Agents beta access.
    """
    from autonomous_agent_builder.services.managed_agents_setup import (
        ManagedAgentsSetupError,
        setup_managed_agents,
    )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        emit_error(
            "ANTHROPIC_API_KEY is not set",
            hint="export ANTHROPIC_API_KEY=...; retry",
            use_json=json_output,
        )
        raise typer.Exit(code=1)

    target_roles = tuple(role) if role else None

    try:
        config = asyncio.run(setup_managed_agents(roles=target_roles))
    except ManagedAgentsSetupError as exc:
        emit_error(str(exc), use_json=json_output)
        raise typer.Exit(code=1) from exc

    payload = {
        "environment_id": config.get("environment_id"),
        "agents": config.get("agents", {}),
        "subagents": config.get("subagents", {}),
        "agent_count": len(config.get("agents", {})),
        "subagent_count": len(config.get("subagents", {})),
    }
    if json_output:
        print(json.dumps(payload, indent=2))
    else:
        print(f"environment: {payload['environment_id']}")
        print(f"agents: {payload['agent_count']}")
        for role_name, agent_id in sorted(payload["agents"].items()):
            print(f"  - {role_name}: {agent_id}")
        print(f"subagents: {payload['subagent_count']}")
        for role_name, agent_id in sorted(payload["subagents"].items()):
            print(f"  - {role_name}: {agent_id}")
    raise typer.Exit(code=EXIT_SUCCESS)


@managed_agents_app.command("vault-add")
def managed_agents_vault_add_command(
    name: str = typer.Option(
        "github",
        "--name",
        help="Vault key under config['vaults'] (e.g. 'github').",
    ),
    credential_file: Path = typer.Option(
        ...,
        "--credential-file",
        exists=True,
        readable=True,
        help=(
            "Path to a JSON file containing the credential payload "
            "(display_name + auth.{type,mcp_server_url,access_token,refresh.*}). "
            "See MA docs §Vaults for the schema."
        ),
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Add an MCP credential to a vault for the claude_managed lane.

    Phase C: the GitHub MCP credential enables pr-creator to call
    `create_pull_request` and other GitHub MCP tools at session time.
    Sessions auto-attach all configured vaults via vault_ids.
    """
    from autonomous_agent_builder.services.managed_agents_setup import (
        ManagedAgentsSetupError,
        add_vault,
    )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        emit_error(
            "ANTHROPIC_API_KEY is not set",
            hint="export ANTHROPIC_API_KEY=...; retry",
            use_json=json_output,
        )
        raise typer.Exit(code=1)

    try:
        credential = json.loads(credential_file.read_text())
    except json.JSONDecodeError as exc:
        emit_error(
            f"--credential-file is not valid JSON: {exc}",
            use_json=json_output,
        )
        raise typer.Exit(code=1) from exc

    try:
        config = asyncio.run(add_vault(name=name, credential=credential))
    except ManagedAgentsSetupError as exc:
        emit_error(str(exc), use_json=json_output)
        raise typer.Exit(code=1) from exc

    payload = {
        "vaults": config.get("vaults", {}),
        "added": name,
    }
    if json_output:
        print(json.dumps(payload, indent=2))
    else:
        print(f"vault '{name}' updated; vault id = {payload['vaults'].get(name)}")
    raise typer.Exit(code=EXIT_SUCCESS)


@managed_agents_app.command("show")
def managed_agents_show_command(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Show currently-provisioned MA agent / environment / subagent IDs."""
    from autonomous_agent_builder.runtime.managed_agents_runtime import (
        ManagedAgentsConfigError,
        _load_managed_agents_config,
    )

    try:
        config = _load_managed_agents_config()
    except ManagedAgentsConfigError as exc:
        emit_error(str(exc), use_json=json_output)
        raise typer.Exit(code=1) from exc

    if json_output:
        print(json.dumps(config, indent=2, sort_keys=True))
    else:
        print(f"environment: {config.get('environment_id') or '(not provisioned)'}")
        agents = config.get("agents") or {}
        print(f"agents: {len(agents)}")
        for role_name, agent_id in sorted(agents.items()):
            print(f"  - {role_name}: {agent_id}")
        subagents = config.get("subagents") or {}
        print(f"subagents: {len(subagents)}")
        for role_name, agent_id in sorted(subagents.items()):
            print(f"  - {role_name}: {agent_id}")
        vaults = config.get("vaults") or {}
        print(f"vaults: {len(vaults)}")
        for vault_name, vault_id in sorted(vaults.items()):
            print(f"  - {vault_name}: {vault_id}")
    raise typer.Exit(code=EXIT_SUCCESS)


def _documentation_refresh_format(payload: dict[str, Any]) -> str:
    lines = [
        f"status: {payload.get('status', '')}",
        f"mode: {payload.get('mode', '')}",
        f"summary: {payload.get('summary', '')}",
    ]
    actionable = payload.get("actionable_doc_ids", [])
    if actionable:
        lines.append(f"actionable_doc_ids: {', '.join(str(item) for item in actionable)}")
    if payload.get("manual_attention_reasons"):
        lines.append("manual_attention_reasons:")
        for reason in payload["manual_attention_reasons"]:
            lines.append(f"  - {reason}")
    run = payload.get("run") or {}
    if run:
        lines.append(
            "run: "
            + ", ".join(
                f"{key}={value}"
                for key, value in run.items()
                if key in {"session_id", "cost_usd", "num_turns", "stop_reason"}
                and value not in ("", None)
            )
        )
    remaining_gap = str(payload.get("remaining_gap", "") or "").strip()
    if remaining_gap:
        lines.append(f"remaining_gap: {remaining_gap}")
    lines.append(f"Next: {payload.get('next_step', '')}")
    return "\n".join(lines)


def _runtime_format(payload: dict[str, Any]) -> str:
    lines = [
        f"sdk: {payload.get('sdk', '')}",
        f"provider: {payload.get('provider', '')}",
        f"model: {payload.get('model', '')}",
        f"ok: {payload.get('ok', True)}",
    ]
    if payload.get("code"):
        lines.append(f"code: {payload['code']}")
    if payload.get("message"):
        lines.append(f"message: {payload['message']}")
    if payload.get("next"):
        lines.append(f"Next: {payload['next']}")
    return "\n".join(lines)


def _runtime_payload(
    config: dict[str, Any],
    *,
    include_capabilities: bool = True,
) -> dict[str, Any]:
    return runtime_settings_payload(Path.cwd(), config, include_capabilities=include_capabilities)


@runtime_app.command("show")
def runtime_show(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show the selected runtime settings and capability map."""
    config = resolve_runtime_config(get_settings())
    payload = _runtime_payload(config)
    render(payload, _runtime_format, use_json=json_output)
    sys.exit(EXIT_SUCCESS if payload["ok"] else 2)


@runtime_app.command("probe")
def runtime_probe(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Probe the selected runtime without falling back to another runtime."""
    config = resolve_runtime_config(get_settings())
    errors = validate_runtime_config(config)
    if errors:
        payload = _runtime_payload(config, include_capabilities=False)
        payload.update(
            {
                "status": "error",
                "code": errors[0]["code"],
                "message": errors[0]["message"],
                "next": errors[0]["next"],
                "exit_code": 2,
            }
        )
        render(payload, _runtime_format, use_json=json_output)
        sys.exit(2)

    runtime = create_runtime(**config)
    result = asyncio.run(runtime.probe())
    payload = asdict(result)
    payload.update({"schema_version": "1", "exit_code": 0 if result.ok else 3})
    render(payload, _runtime_format, use_json=json_output)
    sys.exit(EXIT_SUCCESS if result.ok else 3)


@runtime_app.command("models")
def runtime_models(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List models when the selected provider exposes a model endpoint."""
    config = resolve_runtime_config(get_settings())
    errors = validate_runtime_config(config)
    if errors:
        payload = _runtime_payload(config, include_capabilities=False)
        payload.update({"code": errors[0]["code"], "message": errors[0]["message"]})
        render(payload, _runtime_format, use_json=json_output)
        sys.exit(2)

    runtime = create_runtime(**config)
    if hasattr(runtime, "list_models"):
        result = asyncio.run(runtime.list_models())
        payload = {
            "sdk": runtime.name,
            "provider": getattr(runtime, "provider", config["provider"]),
            "model": runtime.model,
            "model_listing": True,
            **result,
            "schema_version": "1",
            "exit_code": 0 if result.get("ok") else 3,
            "next": (
                "builder agent runtime set --sdk codex_sdk "
                "--provider codex_subscription --model <model> --json"
            ),
        }
        render(
            payload,
            lambda item: "\n".join(model["id"] for model in item["models"]),
            use_json=json_output,
        )
        sys.exit(EXIT_SUCCESS if payload["ok"] else 3)

    payload = {
        "ok": True,
        "sdk": runtime.name,
        "provider": config["provider"],
        "model": runtime.model,
        "model_listing": False,
        "models": [{"id": runtime.model}],
        "schema_version": "1",
        "next": "builder agent runtime probe --json",
    }
    render(payload, lambda item: item["model"], use_json=json_output)
    sys.exit(EXIT_SUCCESS)


@runtime_app.command("set")
def runtime_set(
    sdk: str = typer.Option(
        ...,
        "--sdk",
        help="Runtime SDK: claude or codex_sdk.",
    ),
    provider: str | None = typer.Option(None, "--provider", help="Runtime provider."),
    model: str | None = typer.Option(None, "--model", help="Model identifier."),
    api_base_url: str | None = typer.Option(None, "--api-base-url", help="Provider base URL."),
    api_key_env: str | None = typer.Option(None, "--api-key-env", help="API key environment name."),
    codex_profile: str | None = typer.Option(None, "--codex-profile", help="Codex config profile."),
    sandbox_mode: str | None = typer.Option(None, "--sandbox-mode", help="Codex sandbox mode."),
    approval_policy: str | None = typer.Option(
        None,
        "--approval-policy",
        help="Codex approval policy.",
    ),
    tracing: str | None = typer.Option(None, "--tracing", help="Runtime tracing policy."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Persist the selected runtime to the local `.env` settings surface."""
    overrides = {
        key: value
        for key, value in {
            "sdk": sdk,
            "provider": provider,
            "model": model,
            "api_base_url": api_base_url,
            "api_key_env": api_key_env,
            "codex_profile": codex_profile,
            "sandbox_mode": sandbox_mode,
            "approval_policy": approval_policy,
            "tracing": tracing,
        }.items()
        if value is not None
    }
    payload = persist_runtime_settings(
        Path.cwd(),
        sdk=str(overrides["sdk"]),
        provider=provider,
        model=model,
        api_base_url=api_base_url,
        api_key_env=api_key_env,
        codex_profile=codex_profile,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        tracing=tracing,
    )
    render(payload, _runtime_format, use_json=json_output)
    sys.exit(EXIT_SUCCESS if payload.get("ok") else 2)


@app.command("sessions")
def list_sessions(
    limit: int = typer.Option(20, help="Max sessions."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List saved agent chat sessions."""
    client = get_client(use_json=json)
    try:
        try:
            data = request_json(client, "GET", "/agent/chat/sessions")
        except BuilderConnectivityError:
            data = load_local_agent_sessions(limit)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        raw_items = (
            data.get("results", [])
            if isinstance(data, dict) and "results" in data
            else data.get("sessions", []) if isinstance(data, dict) else []
        )
        items = list(raw_items)[:limit]
        payload = dict(data) if isinstance(data, dict) else {}
        payload.update(
            {
                "status": "ok",
                "count": len(items),
                "results": items,
                "schema_version": "1",
                "next_step": "builder agent history --session <id> --json",
            }
        )

        def fmt(data: dict[str, Any]) -> str:
            rows = list(data.get("results", []))
            headers = ["ID", "SDK SESSION", "UPDATED", "MESSAGES", "PREVIEW"]
            body = [
                [
                    str(item.get("id", ""))[:12],
                    str(item.get("sdk_session_id", "") or "")[:12],
                    str(item.get("updated_at", ""))[:19],
                    str(item.get("message_count", 0)),
                    truncate(str(item.get("preview", "") or ""), 60),
                ]
                for item in rows
            ]
            return table(headers, body) + f"\n\nNext: {data.get('next_step', '')}"

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def history(
    session_id: str | None = typer.Option(None, "--session", help="Chat session ID."),
    full: bool = typer.Option(False, "--full", help="Include timeline items."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show agent chat history for one session."""
    client = get_client(use_json=json)
    try:
        params = {"session_id": session_id} if session_id else {}
        try:
            data = request_json(client, "GET", "/agent/chat/history", params=params)
        except BuilderConnectivityError:
            data = load_local_agent_history(session_id, full=full)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        payload = dict(data) if isinstance(data, dict) else {}
        if not full:
            payload.pop("items", None)
        payload["next_step"] = "builder logs --session <id> --compact --json"

        def fmt(item: dict[str, Any]) -> str:
            lines = [
                f"session_id: {item.get('session_id', '') or '(none)'}",
                f"sdk_session_id: {item.get('sdk_session_id', '') or '(none)'}",
                f"model: {item.get('model', '')}",
                f"messages: {len(item.get('messages', []))}",
            ]
            status = item.get("status")
            if status:
                lines.append(
                    "status: "
                    + ", ".join(
                        f"{key}={value}"
                        for key, value in status.items()
                        if key
                        in {
                            "running",
                            "current_turn",
                            "max_turns",
                            "tokens_used",
                            "cost_usd",
                            "duration_ms",
                            "stop_reason",
                            "sdk_session_id",
                            "error",
                        }
                        and value not in ("", None)
                    )
                )
            messages = item.get("messages", [])
            if messages:
                lines.append("")
                lines.append("--- MESSAGES ---")
                for message in messages[-10:]:
                    role = str(message.get("role", ""))
                    content = truncate(str(message.get("content", "") or ""), 220)
                    lines.append(f"[{role}] {content}")
            if full and item.get("items"):
                lines.append("")
                lines.append(f"timeline_items: {len(item['items'])}")
            lines.append("")
            lines.append(f"Next: {item.get('next_step', '')}")
            return "\n".join(lines)

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def meta(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show stable agent-lane metadata."""
    client = get_client(use_json=json)
    try:
        try:
            data = request_json(client, "GET", "/agent/chat/meta")
        except BuilderConnectivityError:
            data = load_local_agent_meta()
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        payload = dict(data) if isinstance(data, dict) else {"raw": data}
        payload["next_step"] = "builder agent sessions --json"
        render(
            payload,
            lambda item: (
                f"model: {item.get('model', '')}\n"
                f"Next: {item.get('next_step', '')}"
            ),
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command("documentation-refresh")
def documentation_refresh(
    validation: Path = typer.Option(
        ...,
        "--validation",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to `builder knowledge validate --json` output.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Run the repo-owned documentation-agent bridge for bounded freshness updates."""
    try:
        validation_payload = json.loads(validation.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        emit_error(
            f"Invalid validation JSON: {exc}",
            code="invalid_input",
            hint="Run `builder knowledge validate --json > kb-validate.json` and retry.",
            use_json=json_output,
        )
        sys.exit(2)

    project_root = Path(os.environ.get("AAB_PROJECT_ROOT", Path.cwd())).resolve()
    payload = asyncio.run(
        run_documentation_refresh_bridge(validation_payload, project_root=project_root)
    )
    render(payload, _documentation_refresh_format, use_json=json_output)

    status = str(payload.get("status", "") or "").strip()
    validation_status = str(payload.get("validation_status", "") or "").strip()
    if status in {"already_current", "updated_and_verified"} and (
        not validation_status or validation_status == "pass"
    ):
        sys.exit(EXIT_SUCCESS)
    if status == "already_current":
        sys.exit(EXIT_SUCCESS)
    sys.exit(1)
