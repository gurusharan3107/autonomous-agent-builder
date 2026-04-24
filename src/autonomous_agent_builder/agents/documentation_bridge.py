"""Repo-owned bridge for bounded documentation-agent automation."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.runner import AgentRunner
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.knowledge.documentation_freshness_ci import (
    DocumentationFreshnessPlan,
    prepare_documentation_freshness_plan,
)


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("No JSON object found in agent output.")


@contextmanager
def _project_scope(project_root: Path):
    resolved_root = str(project_root.resolve())
    scoped_env = {
        "AAB_PROJECT_ROOT": resolved_root,
        "AAB_LOCAL_KB_ROOT": str(Path(resolved_root) / ".agent-builder" / "knowledge"),
        "AAB_MEMORY_ROOT": str(Path(resolved_root) / ".memory"),
    }
    previous = {key: os.environ.get(key) for key in scoped_env}
    os.environ.update(scoped_env)
    try:
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


async def run_documentation_refresh_bridge(
    validation_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    plan = prepare_documentation_freshness_plan(validation_payload, workspace_path=project_root)
    base_payload = {
        "status": "",
        "mode": plan.mode,
        "summary": plan.summary,
        "specialist": "documentation-agent",
        "bridge": "builder agent documentation-refresh",
        "actionable_doc_ids": [doc.doc_id for doc in plan.actionable_docs],
        "manual_attention_reasons": list(plan.manual_attention_reasons),
        "bridge_invoked": False,
        "run": {},
        "result": {},
        "next_step": "builder knowledge validate --json",
    }

    if plan.mode == "no_op":
        return {
            **base_payload,
            "status": "already_current",
            "summary": plan.summary or "Maintained docs are already current.",
        }

    if plan.mode == "manual_attention":
        return {
            **base_payload,
            "status": "manual_attention",
            "summary": plan.summary,
            "remaining_gap": "; ".join(plan.manual_attention_reasons),
        }

    result = await _run_bridge_agent(plan, project_root=project_root)
    bridge_payload = {
        **base_payload,
        "bridge_invoked": True,
        "run": {
            "session_id": result.session_id,
            "cost_usd": result.cost_usd,
            "tokens_input": result.tokens_input,
            "tokens_output": result.tokens_output,
            "num_turns": result.num_turns,
            "duration_ms": result.duration_ms,
            "stop_reason": result.stop_reason,
        },
    }

    if result.error:
        return {
            **bridge_payload,
            "status": "bridge_failed",
            "summary": result.error,
            "remaining_gap": result.error,
        }

    try:
        agent_payload = _extract_json_object(result.output_text)
    except ValueError as exc:
        return {
            **bridge_payload,
            "status": "bridge_failed",
            "summary": str(exc),
            "remaining_gap": result.output_text.strip() or str(exc),
        }

    status = str(agent_payload.get("status", "") or "").strip()
    validation_status = str(agent_payload.get("validation_status", "") or "").strip()
    summary = str(agent_payload.get("summary", "") or "").strip()
    return {
        **bridge_payload,
        "status": status or "bridge_failed",
        "summary": summary or "Documentation-agent bridge completed without summary.",
        "validation_status": validation_status,
        "result": agent_payload,
        "remaining_gap": str(agent_payload.get("remaining_gap", "") or "").strip(),
    }


async def _run_bridge_agent(
    plan: DocumentationFreshnessPlan,
    *,
    project_root: Path,
):
    runner = AgentRunner(get_settings())
    with _project_scope(project_root):
        return await runner.run_phase(
            agent_name="documentation-bridge",
            prompt=plan.prompt,
            workspace_path=str(project_root.resolve()),
            subagents=("documentation-agent",),
        )
