"""Board command — bounded pipeline state for active work."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    BuilderConnectivityError,
    get_client,
    handle_api_error,
    request_json,
)
from autonomous_agent_builder.cli.local_fallback import load_local_board
from autonomous_agent_builder.cli.output import format_status, render

BOARD_SECTIONS = ("pending", "active", "review", "done", "blocked")


def _short_text(value: object, *, max_chars: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + " ... [truncated]"


def _compact_task(task: dict) -> dict:
    compact = {
        "id": str(task.get("id", "")),
        "title": _short_text(task.get("title"), max_chars=120),
        "status": str(task.get("status", "")),
        "phase": str(task.get("phase", "")),
        "feature_id": str(task.get("feature_id", "")),
        "feature_title": _short_text(task.get("feature_title"), max_chars=120),
        "runtime_sdk": str(task.get("runtime_sdk", "")),
        "blocked_reason": _short_text(task.get("blocked_reason"), max_chars=180),
    }
    latest_run_status = str(task.get("latest_run_status", "") or "")
    if latest_run_status and latest_run_status != "completed":
        compact["latest_run_status"] = latest_run_status
    pending_approval_count = task.get("pending_approval_count") or 0
    if pending_approval_count:
        compact["pending_approval_count"] = pending_approval_count
    cost = task.get("cost_usd") or task.get("total_cost") or 0
    if cost:
        compact["cost_usd"] = cost
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _bounded_full_task(task: dict) -> dict:
    bounded = dict(task)
    for key in ("description", "feature_description", "blocked_reason"):
        if key in bounded:
            bounded[key] = _short_text(bounded.get(key), max_chars=500)
    if isinstance(bounded.get("acceptance_criteria"), list):
        bounded["acceptance_criteria"] = [
            _short_text(item, max_chars=220) for item in bounded["acceptance_criteria"][:5]
        ]
        if len(task.get("acceptance_criteria", [])) > 5:
            bounded["acceptance_criteria_omitted"] = len(task["acceptance_criteria"]) - 5
    if isinstance(bounded.get("dependencies"), list):
        bounded["dependencies"] = bounded["dependencies"][:10]
        if len(task.get("dependencies", [])) > 10:
            bounded["dependencies_omitted"] = len(task["dependencies"]) - 10

    sprint_execution = bounded.pop("sprint_execution", None)
    if isinstance(sprint_execution, dict):
        summary = {
            key: sprint_execution.get(key)
            for key in ("mode", "runtime_sdk", "model", "effort", "status", "task_role")
            if sprint_execution.get(key)
        }
        summary["keys"] = sorted(str(key) for key in sprint_execution)[:12]
        bounded["sprint_execution_summary"] = summary

    observability = bounded.pop("observability", None)
    if isinstance(observability, dict):
        observability_summary = {
            key: observability.get(key)
            for key in (
                "runtime_sdk",
                "telemetry_source",
                "tokens_input",
                "tokens_output",
                "tokens_cached",
                "duration_ms",
                "stop_reason",
                "provider_limit",
            )
            if observability.get(key) not in (None, "", [], {})
        }
        if observability_summary:
            bounded["observability_summary"] = observability_summary

    agent_runs = bounded.pop("agent_runs", None)
    if isinstance(agent_runs, list):
        bounded["agent_runs_summary"] = {
            "count": len(agent_runs),
            "latest": [
                {
                    "id": str(run.get("id", "")),
                    "status": run.get("status"),
                    "runtime_sdk": run.get("runtime_sdk"),
                    "model": run.get("model"),
                }
                for run in agent_runs[:2]
                if isinstance(run, dict)
            ],
        }

    activity_timeline = bounded.pop("activity_timeline", None)
    if isinstance(activity_timeline, list):
        bounded["activity_timeline_summary"] = {
            "count": len(activity_timeline),
            "latest": [
                {
                    "event_type": event.get("event_type"),
                    "status": event.get("status"),
                    "action": _short_text(event.get("action"), max_chars=120),
                    "timestamp": event.get("timestamp"),
                }
                for event in activity_timeline[:3]
                if isinstance(event, dict)
            ],
        }
    return bounded


def _compact_sprint_item(item: dict) -> dict:
    compact = {
        "id": str(item.get("id", "")),
        "title": _short_text(item.get("title"), max_chars=120),
        "status": str(item.get("status", "")),
    }
    dependencies = item.get("dependencies")
    if isinstance(dependencies, list) and dependencies:
        compact["dependency_count"] = len(dependencies)
    sprint_execution = item.get("sprint_execution")
    if isinstance(sprint_execution, dict):
        for key in ("mode", "runtime_sdk", "model", "effort", "status"):
            if sprint_execution.get(key):
                compact[key] = sprint_execution[key]
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_current_sprint(value: object, *, limit: int) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {
        "sprint_id": value.get("sprint_id"),
        "label": value.get("label"),
        "active_phase": value.get("active_phase"),
        "phase_statuses": value.get("phase_statuses") or {},
        "task_counts": value.get("task_counts") or {},
        "verification_status": value.get("verification_status"),
        "runtime_sdk": value.get("runtime_sdk"),
        "model": value.get("model"),
        "effort": value.get("effort"),
    }
    for key in ("included_items", "generated_tasks"):
        items = value.get(key)
        if isinstance(items, list):
            compact[key] = [
                _compact_sprint_item(item) for item in items[:limit] if isinstance(item, dict)
            ]
            omitted = max(len(items) - len(compact[key]), 0)
            if omitted:
                compact[f"{key}_omitted"] = omitted
    return {key: val for key, val in compact.items() if val not in (None, "", [], {})}


def _compact_sprint_plan(value: object, *, limit: int) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {
        "plan_id": value.get("plan_id"),
        "design_id": value.get("design_id"),
        "sprint_number": value.get("sprint_number"),
        "mode": value.get("mode"),
        "model": value.get("model"),
        "effort": value.get("effort"),
        "strategy": value.get("strategy"),
        "batch_count": value.get("batch_count"),
        "sequential_count": value.get("sequential_count"),
        "parallel_count": value.get("parallel_count"),
        "context_strategy": value.get("context_strategy"),
    }
    batches = value.get("batches")
    if isinstance(batches, list):
        compact["batches"] = [
            {
                "id": str(batch.get("id", "")),
                "title": _short_text(batch.get("title"), max_chars=120),
                "execution_mode": batch.get("execution_mode"),
                "model": batch.get("model"),
                "effort": batch.get("effort"),
            }
            for batch in batches[:limit]
            if isinstance(batch, dict)
        ]
        omitted = max(len(batches) - len(compact["batches"]), 0)
        if omitted:
            compact["batches_omitted"] = omitted
    return {key: val for key, val in compact.items() if val not in (None, "", [], {})}


def _compact_board_payload(data: dict, *, limit: int) -> dict:
    payload = {
        key: data[key]
        for key in ("ok", "status", "exit_code", "degraded", "source", "schema_version")
        if key in data
    }
    counts = data.get("counts")
    if not isinstance(counts, dict):
        counts = {
            section: len(data.get(section, [])) if isinstance(data.get(section), list) else 0
            for section in BOARD_SECTIONS
        }
    payload["counts"] = counts

    truncation: dict[str, dict[str, int]] = {}
    for section in BOARD_SECTIONS:
        items = data.get(section)
        if not isinstance(items, list):
            payload[section] = []
            continue
        compact_items = [_compact_task(item) for item in items[:limit] if isinstance(item, dict)]
        payload[section] = compact_items
        section_count = counts.get(section) if isinstance(counts.get(section), int) else len(items)
        omitted = max(section_count - len(compact_items), len(items) - len(compact_items), 0)
        if omitted:
            truncation[section] = {"returned": len(compact_items), "omitted": omitted}

    sprint_plan = _compact_sprint_plan(data.get("sprint_plan"), limit=min(limit, 10))
    if sprint_plan:
        payload["sprint_plan"] = sprint_plan
    current_sprint = _compact_current_sprint(data.get("current_sprint"), limit=min(limit, 10))
    if current_sprint:
        payload["current_sprint"] = current_sprint
    sprints = data.get("sprints")
    if isinstance(sprints, list) and sprints:
        payload["sprints_summary"] = {
            "count": len(sprints),
            "latest": [
                {
                    "sprint_id": str(sprint.get("sprint_id", "")),
                    "label": sprint.get("label"),
                    "active_phase": sprint.get("active_phase"),
                    "task_counts": sprint.get("task_counts") or {},
                    "verification_status": sprint.get("verification_status"),
                }
                for sprint in sprints[:3]
                if isinstance(sprint, dict)
            ],
            "focused_read": "builder backlog task status <task-id> --json",
        }

    if truncation:
        payload["sections_truncated"] = truncation
    payload["truncated"] = bool(truncation)
    payload["next_step"] = data.get("next_step") or "builder backlog task status <task-id> --json"
    payload["raw_evidence"] = {
        "full_payload_command": f"builder board show --json --full --limit {limit}",
        "focused_task_command": "builder backlog task status <task-id> --json",
    }
    return payload


def _bounded_full_board_payload(data: dict, *, limit: int) -> dict:
    payload = dict(data)
    for section in BOARD_SECTIONS:
        if section in payload and isinstance(payload[section], list):
            payload[section] = [
                _bounded_full_task(item) if isinstance(item, dict) else item
                for item in payload[section][:limit]
            ]

    sprint_plan = _compact_sprint_plan(data.get("sprint_plan"), limit=min(limit, 10))
    if sprint_plan:
        payload["sprint_plan"] = sprint_plan
    current_sprint = _compact_current_sprint(data.get("current_sprint"), limit=min(limit, 10))
    if current_sprint:
        payload["current_sprint"] = current_sprint
    sprints = data.get("sprints")
    if isinstance(sprints, list) and sprints:
        payload["sprints_summary"] = {
            "count": len(sprints),
            "latest": [
                {
                    "sprint_id": str(sprint.get("sprint_id", "")),
                    "label": sprint.get("label"),
                    "active_phase": sprint.get("active_phase"),
                    "task_counts": sprint.get("task_counts") or {},
                    "verification_status": sprint.get("verification_status"),
                }
                for sprint in sprints[:3]
                if isinstance(sprint, dict)
            ],
            "focused_read": "builder backlog task status <task-id> --json",
        }
        payload.pop("sprints", None)
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    payload["truncated"] = any(
        (
            isinstance(data.get(section), list)
            and max(int(counts.get(section, 0) or 0), len(data[section])) > limit
        )
        for section in BOARD_SECTIONS
    )
    payload["raw_evidence"] = {
        "note": (
            "Full expands board task fields for the section limit; "
            "use focused commands for task details."
        ),
        "focused_task_command": "builder backlog task status <task-id> --json",
    }
    return payload


app = typer.Typer(
    help=(
        "Task pipeline board.\n\n"
        "Start here:\n"
        "  builder board show --json\n"
        "  builder backlog task status <task-id> --json\n"
        "  builder backlog approval list --task <task-id> --json\n"
    )
)


@app.command("show")
def show(
    limit: int = typer.Option(5, help="Max tasks per section."),
    full: bool = typer.Option(
        False,
        "--full",
        help="Return full board item fields for the selected section limit.",
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show the task pipeline board — Pending | Active | Review | Done | Blocked."""
    client = get_client(use_json=json)
    try:
        try:
            data = request_json(client, "GET", "/dashboard/board")
        except BuilderConnectivityError:
            data = load_local_board(limit)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        if "counts" not in data:
            data["counts"] = {section: len(data.get(section, [])) for section in BOARD_SECTIONS}
        data.setdefault("next_step", "builder backlog task status <task-id> --json")
        if full:
            render_data = _bounded_full_board_payload(data, limit=limit)
        else:
            render_data = _compact_board_payload(data, limit=limit)

        def fmt(d: dict) -> str:
            sections = []
            for section in BOARD_SECTIONS:
                items = d.get(section, [])
                if not items:
                    continue
                header = f"--- {section.upper()} ({len(items)}) ---"
                lines = [header]
                for task in items:
                    cost = task.get("cost_usd") or task.get("total_cost") or 0
                    line = (
                        f"  {str(task.get('id', ''))[:12]}  "
                        f"{task.get('title', '')[:35]}  "
                        f"{format_status(task.get('status', ''))}  "
                        f"${cost:.2f}"
                    )
                    if task.get("blocked_reason"):
                        line += f"  [{task['blocked_reason'][:30]}]"
                    lines.append(line)
                sections.append("\n".join(lines))
            if sections:
                sections.append("\nNext: " + str(d.get("next_step", "")))
                return "\n\n".join(sections)
            return "(board is empty)\n\nNext: builder backlog task list --json"

        render(render_data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
