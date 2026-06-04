"""Documentation refresh gate support for orchestrator PR creation."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.models import AgentRun, Task
from autonomous_agent_builder.services.builder_tool_service import builder_kb_validate


def resolve_documentation_project_root(task: Task, workspace_path: str) -> Path:
    """Prefer a real project repo path, falling back to the task workspace."""
    workspace_root = Path(workspace_path or ".").resolve()
    project = getattr(getattr(task, "feature", None), "project", None)
    repo_root = getattr(project, "repo_url", "") if project is not None else ""
    if not isinstance(repo_root, str) or not repo_root.strip() or "://" in repo_root:
        return workspace_root

    candidate = Path(repo_root).expanduser().resolve()
    if candidate.exists():
        return candidate
    return workspace_root


async def load_kb_validation_payload(project_root: Path) -> dict[str, object]:
    response = await builder_kb_validate(project_root=str(project_root))
    content = response.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError("builder_kb_validate returned no content")
    item = content[0]
    if not isinstance(item, dict):
        raise RuntimeError("builder_kb_validate returned invalid content")
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("builder_kb_validate returned empty text payload")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError("builder_kb_validate returned a non-object payload")
    return payload


async def project_has_canonical_head(project_root: Path) -> bool:
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return True
    proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "--verify",
        "HEAD",
        cwd=str(project_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0


def forward_engineering_seed_docs_deferred(
    project_root: Path,
    validation_payload: dict[str, object],
) -> bool:
    from autonomous_agent_builder.onboarding import load_onboarding_state

    state = load_onboarding_state(project_root)
    if state.get("onboarding_mode") != "forward_engineering":
        return False
    checks = validation_payload.get("checks")
    if not isinstance(checks, list):
        return False
    freshness = next(
        (item for item in checks if isinstance(item, dict) and item.get("name") == "freshness"),
        None,
    )
    if freshness is not None and not bool(freshness.get("passed", False)):
        return False
    claim_failures = validation_payload.get("claim_failures")
    if not isinstance(claim_failures, list) or not claim_failures:
        return False
    return all(
        isinstance(item, dict) and item.get("reason") == "missing_document"
        for item in claim_failures
    )


def forward_engineering_sprint_doc_hash_drift_advisory(
    task: Task,
    project_root: Path,
    validation_payload: dict[str, object],
) -> bool:
    """Do not block generated feature delivery on non-actionable KB hash drift."""
    from autonomous_agent_builder.onboarding import load_onboarding_state

    state = load_onboarding_state(project_root)
    if state.get("onboarding_mode") != "forward_engineering":
        return False
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    sprint_execution = depends_on.get("sprint_execution")
    if not isinstance(sprint_execution, dict):
        return False
    if sprint_execution.get("mode") != "sprint_task_breakdown":
        return False
    if validation_payload.get("claim_failures"):
        return False

    checks = validation_payload.get("checks")
    if not isinstance(checks, list):
        return False
    failed_names = {
        str(check.get("name", "") or "").strip()
        for check in checks
        if isinstance(check, dict) and not bool(check.get("passed", False))
    }
    if not failed_names or not failed_names.issubset({"citation_validity", "freshness"}):
        return False

    freshness = next(
        (item for item in checks if isinstance(item, dict) and item.get("name") == "freshness"),
        None,
    )
    details = freshness.get("details") if isinstance(freshness, dict) else {}
    maintained_docs = details.get("maintained_docs") if isinstance(details, dict) else None
    return not (isinstance(maintained_docs, list) and maintained_docs)


def forward_engineering_non_actionable_doc_validation(
    project_root: Path,
    bridge_payload: dict[str, object],
) -> bool:
    from autonomous_agent_builder.onboarding import load_onboarding_state

    state = load_onboarding_state(project_root)
    if state.get("onboarding_mode") != "forward_engineering":
        return False
    if str(bridge_payload.get("status", "") or "").strip() != "manual_attention":
        return False
    actionable_doc_ids = bridge_payload.get("actionable_doc_ids")
    if isinstance(actionable_doc_ids, list) and actionable_doc_ids:
        return False
    reasons = bridge_payload.get("manual_attention_reasons")
    if not isinstance(reasons, list):
        reasons = [str(bridge_payload.get("remaining_gap", "") or "")]
    return any(
        str(reason).strip() == "validation failed without actionable stale maintained docs"
        for reason in reasons
    )


async def record_documentation_bridge_run(
    db: AsyncSession,
    task: Task,
    bridge_payload: dict[str, object],
) -> None:
    if not bool(bridge_payload.get("bridge_invoked", False)):
        return

    run_payload = bridge_payload.get("run")
    if not isinstance(run_payload, dict):
        run_payload = {}

    status = str(bridge_payload.get("status", "") or "").strip()
    error = None
    if status not in {"already_current", "updated_and_verified"}:
        error = documentation_gate_message(bridge_payload)

    run = AgentRun(
        task_id=task.id,
        agent_name="documentation-bridge",
        session_id=str(run_payload.get("session_id", "") or "") or None,
        runtime_sdk=str(run_payload.get("runtime_sdk", "") or ""),
        provider=str(run_payload.get("provider", "") or ""),
        model=str(run_payload.get("model", "") or ""),
        effort=str(run_payload.get("effort", "") or "") or None,
        cost_usd=float(run_payload.get("cost_usd", 0.0) or 0.0),
        tokens_input=int(run_payload.get("tokens_input", 0) or 0),
        tokens_output=int(run_payload.get("tokens_output", 0) or 0),
        tokens_cached=0,
        num_turns=int(run_payload.get("num_turns", 0) or 0),
        duration_ms=int(run_payload.get("duration_ms", 0) or 0),
        stop_reason=str(run_payload.get("stop_reason", "") or "") or None,
        status="completed" if status != "bridge_failed" else "failed",
        error=error,
        output_text=str(bridge_payload.get("summary", "") or ""),
        observability=(
            run_payload.get("observability") if isinstance(run_payload.get("observability"), dict) else None
        ),
        completed_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()


def documentation_gate_message(payload: dict[str, object]) -> str:
    remaining_gap = str(payload.get("remaining_gap", "") or "").strip()
    summary = str(payload.get("summary", "") or "").strip()
    detail = remaining_gap or summary or "documentation refresh did not complete"
    return f"documentation refresh gate blocked: {detail}"
