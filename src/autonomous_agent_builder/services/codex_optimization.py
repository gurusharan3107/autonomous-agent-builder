"""Compact optimization summaries for Codex SDK and builder run metrics."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

APP_SERVER_CHUNK_RISK_BYTES = 24_000
LARGE_OUTPUT_BYTES = 20_000
RECENT_SIGNAL_WINDOW = 5
TOKEN_ESTIMATE_CHARS = 4

PHASE_TOKEN_BUDGETS: dict[str, int] = {
    "agent-chat": 30_000,
    "chat": 30_000,
    "planner": 15_000,
    "designer": 15_000,
    "code-gen": 35_000,
    "evidence-collector": 5_000,
    "pr-creator": 5_000,
    "build-verifier": 40_000,
}

CEREMONY_AGENTS = {"planner", "designer", "pr-creator"}
IMPLEMENTATION_AGENTS = {"code-gen"}
VERIFICATION_AGENTS = {"build-verifier"}


def estimate_tokens(text: Any) -> int:
    if text is None:
        return 0
    return max(0, len(str(text)) // TOKEN_ESTIMATE_CHARS)


def prompt_budget_breakdown(
    *,
    agent_name: str,
    prompt: str,
    template_vars: Mapping[str, Any],
    agent_definition: str = "",
) -> dict[str, Any]:
    segments = {
        "agent_definition": estimate_tokens(agent_definition),
        "tool_context": estimate_tokens(template_vars.get("tool_context")),
        "sprint_plan": estimate_tokens(template_vars.get("planning_context")),
        "sprint_design": estimate_tokens(template_vars.get("design_context")),
        "design_directive": estimate_tokens(template_vars.get("design_directive")),
        "task_brief": estimate_tokens(template_vars.get("task_description")),
        "repo_context": estimate_tokens(template_vars.get("knowledge_requirements")),
        "gate_feedback": estimate_tokens(template_vars.get("gate_feedback")),
    }
    total = estimate_tokens(prompt)
    known = sum(segments.values())
    segments["system_or_instructions"] = max(total - known, 0)
    budget = PHASE_TOKEN_BUDGETS.get(agent_name, 35_000)
    return {
        "schema_version": "1",
        "agent_name": agent_name,
        "estimated_total_tokens": total,
        "budget_tokens": budget,
        "over_budget": total > budget,
        "segments": segments,
    }


def codex_run_optimization_summary(
    *,
    events: list[dict[str, Any]],
    metrics: Mapping[str, int],
    agent_name: str,
    prompt_text: str = "",
    output_text: str = "",
    status: str = "completed",
    prompt_budget: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    total_tokens = int(metrics.get("total_tokens") or 0)
    input_tokens = int(metrics.get("input_tokens") or 0)
    output_tokens = int(metrics.get("output_tokens") or 0)
    cached_tokens = int(metrics.get("cached_input_tokens") or 0)
    noncached_plus_output = max(input_tokens - cached_tokens, 0) + output_tokens
    _cr_denom = cached_tokens + input_tokens
    cache_ratio = min(1.0, max(0.0, cached_tokens / _cr_denom)) if _cr_denom > 0 else 0.0

    event_sizes = [_json_size(event) for event in events]
    command_output_sizes = [_command_output_size(event) for event in events]
    largest_event_bytes = max(event_sizes, default=0)
    largest_command_output_bytes = max(command_output_sizes, default=0)

    tool_counts = _tool_counts(events)
    flags = _avoidable_flags(
        agent_name=agent_name,
        status=status,
        total_tokens=total_tokens,
        output_tokens=output_tokens,
        prompt_budget=prompt_budget or {},
        largest_event_bytes=largest_event_bytes,
        largest_command_output_bytes=largest_command_output_bytes,
        tool_counts=tool_counts,
    )

    return {
        "schema_version": "1",
        "primary_score": "raw_tokens",
        "prompt_budget": dict(prompt_budget or {}),
        "token_accounting": {
            "raw_total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_tokens,
            "noncached_plus_output_tokens": noncached_plus_output,
            "reasoning_output_tokens": int(metrics.get("reasoning_output_tokens") or 0),
            "cache_ratio": round(cache_ratio, 4),
        },
        "event_accounting": {
            "raw_event_count": len(events),
            "largest_event_bytes": largest_event_bytes,
            "largest_command_output_bytes": largest_command_output_bytes,
            "chunk_pressure_risk": largest_event_bytes >= APP_SERVER_CHUNK_RISK_BYTES
            or largest_command_output_bytes >= APP_SERVER_CHUNK_RISK_BYTES,
        },
        "tool_accounting": tool_counts,
        "avoidable_cost_flags": flags,
        "avoidable_token_estimate": _avoidable_token_estimate(
            total_tokens=total_tokens,
            noncached_plus_output=noncached_plus_output,
            flags=flags,
        ),
        "final_response_tokens_estimate": estimate_tokens(output_text),
        "prompt_tokens_estimate": estimate_tokens(prompt_text),
    }


def summarize_runs_for_optimization(runs: Iterable[Any]) -> dict[str, Any]:
    rows = [_run_row(run) for run in runs]
    recent_rows = rows[:RECENT_SIGNAL_WINDOW]
    raw_total = sum(row["raw_tokens"] for row in rows)
    cached_total = sum(row["cached_tokens"] for row in rows)
    input_total = sum(row["input_tokens"] for row in rows)
    output_total = sum(row["output_tokens"] for row in rows)
    noncached_plus_output = sum(row["noncached_plus_output"] for row in rows)
    flags = Counter(flag for row in rows for flag in row["flags"])
    active_flags = Counter(flag for row in recent_rows for flag in row["flags"])
    chunk_rows = [
        row["chunk_pressure"]
        for row in rows
        if isinstance(row.get("chunk_pressure"), dict) and row["chunk_pressure"].get("available")
    ]
    recent_chunk_rows = [
        row["chunk_pressure"]
        for row in recent_rows
        if isinstance(row.get("chunk_pressure"), dict) and row["chunk_pressure"].get("available")
    ]
    by_agent: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "runs": 0,
            "raw_tokens": 0,
            "noncached_plus_output_tokens": 0,
            "cached_tokens": 0,
            "avoidable_token_estimate": 0,
        }
    )
    active_by_agent: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "runs": 0,
            "raw_tokens": 0,
            "noncached_plus_output_tokens": 0,
            "cached_tokens": 0,
            "avoidable_token_estimate": 0,
        }
    )
    by_phase = {
        "ceremony": 0,
        "implementation": 0,
        "verification": 0,
        "other": 0,
    }
    for row in rows:
        agent = row["agent_name"]
        item = by_agent[agent]
        item["runs"] += 1
        item["raw_tokens"] += row["raw_tokens"]
        item["noncached_plus_output_tokens"] += row["noncached_plus_output"]
        item["cached_tokens"] += row["cached_tokens"]
        item["avoidable_token_estimate"] += row["avoidable_token_estimate"]
        by_phase[_agent_phase(agent)] += row["raw_tokens"]

    for row in recent_rows:
        agent = row["agent_name"]
        item = active_by_agent[agent]
        item["runs"] += 1
        item["raw_tokens"] += row["raw_tokens"]
        item["noncached_plus_output_tokens"] += row["noncached_plus_output"]
        item["cached_tokens"] += row["cached_tokens"]
        item["avoidable_token_estimate"] += row["avoidable_token_estimate"]

    top_cost_drivers = sorted(
        [
            {
                "agent_name": agent,
                **values,
            }
            for agent, values in by_agent.items()
        ],
        key=lambda item: int(item["raw_tokens"]),
        reverse=True,
    )[:5]
    active_top_cost_drivers = sorted(
        [
            {
                "agent_name": agent,
                **values,
            }
            for agent, values in active_by_agent.items()
        ],
        key=lambda item: int(item["raw_tokens"]),
        reverse=True,
    )[:5]
    target_min = 80_000
    target_max = 185_000
    _cr_denom_total = cached_total + input_total
    cache_ratio = min(1.0, max(0.0, cached_total / _cr_denom_total)) if _cr_denom_total > 0 else 0.0
    active_raw_total = sum(row["raw_tokens"] for row in recent_rows)
    active_cached_total = sum(row["cached_tokens"] for row in recent_rows)
    active_noncached_plus_output = sum(row["noncached_plus_output"] for row in recent_rows)
    rework_token_total = int(by_agent.get("gate-remediator", {}).get("raw_tokens", 0))
    rework_share = round(rework_token_total / raw_total, 4) if raw_total > 0 else 0.0
    return {
        "schema_version": "1",
        "primary_score": "raw_tokens",
        "raw_token_total": raw_total,
        "noncached_plus_output_tokens": noncached_plus_output,
        "cached_tokens": cached_total,
        "output_tokens": output_total,
        "cache_ratio": round(cache_ratio, 4),
        "active_raw_token_total": active_raw_total,
        "active_noncached_plus_output_tokens": active_noncached_plus_output,
        "active_cached_tokens": active_cached_total,
        "phase_ceremony_tokens": by_phase["ceremony"],
        "phase_token_breakdown": by_phase,
        "avoidable_token_estimate": sum(row["avoidable_token_estimate"] for row in rows),
        "avoidable_cost_flags": [
            {"flag": flag, "count": count} for flag, count in flags.most_common()
        ],
        "active_avoidable_cost_flags": [
            {"flag": flag, "count": count} for flag, count in active_flags.most_common()
        ],
        "chunk_pressure": {
            "available": bool(chunk_rows),
            "runs_with_signal": len(chunk_rows),
            "risky_runs": sum(1 for row in chunk_rows if row.get("chunk_pressure_risk")),
            "large_output_runs": sum(
                1
                for row in chunk_rows
                if int(row.get("largest_command_output_bytes") or 0) >= LARGE_OUTPUT_BYTES
            ),
            "large_event_runs": sum(
                1
                for row in chunk_rows
                if int(row.get("largest_event_bytes") or 0) >= APP_SERVER_CHUNK_RISK_BYTES
            ),
            "largest_event_bytes": max(
                (int(row.get("largest_event_bytes") or 0) for row in chunk_rows),
                default=0,
            ),
            "largest_command_output_bytes": max(
                (int(row.get("largest_command_output_bytes") or 0) for row in chunk_rows),
                default=0,
            ),
            "chunk_pressure_risk": any(bool(row.get("chunk_pressure_risk")) for row in chunk_rows),
            "recent_window_runs": len(recent_rows),
            "recent_runs_with_signal": len(recent_chunk_rows),
            "recent_risky_runs": sum(
                1 for row in recent_chunk_rows if row.get("chunk_pressure_risk")
            ),
            "recent_large_output_runs": sum(
                1
                for row in recent_chunk_rows
                if int(row.get("largest_command_output_bytes") or 0) >= LARGE_OUTPUT_BYTES
            ),
            "recent_large_event_runs": sum(
                1
                for row in recent_chunk_rows
                if int(row.get("largest_event_bytes") or 0) >= APP_SERVER_CHUNK_RISK_BYTES
            ),
        },
        "top_cost_drivers": top_cost_drivers,
        "active_top_cost_drivers": active_top_cost_drivers,
        "benchmark": {
            "target_min_raw_tokens": target_min,
            "target_max_raw_tokens": target_max,
            "status": (
                "within_target"
                if target_min <= raw_total <= target_max
                else "over_target"
                if raw_total > target_max
                else "under_target"
            ),
        },
        "rework_token_total": rework_token_total,
        "rework_share": rework_share,
        "recommended_next_change": _recommended_next_change(
            top_cost_drivers,
            flags,
            raw_total,
            active_flags=active_flags,
            active_top_cost_drivers=active_top_cost_drivers,
            rework_share=rework_share,
        ),
    }


def _run_row(run: Any) -> dict[str, Any]:
    observability = _dict_value(_value(run, "observability"))
    optimization = _dict_value(observability.get("optimization_summary"))
    tokens = _dict_value(optimization.get("token_accounting"))
    raw_tokens = int(
        tokens.get("raw_total_tokens")
        or _value(run, "tokens_input", 0) + _value(run, "tokens_output", 0)
    )
    cached_tokens = int(tokens.get("cached_input_tokens") or _value(run, "tokens_cached", 0))
    input_tokens = int(tokens.get("input_tokens") or _value(run, "tokens_input", 0))
    output_tokens = int(tokens.get("output_tokens") or _value(run, "tokens_output", 0))
    noncached_plus_output = int(
        tokens.get("noncached_plus_output_tokens")
        or max(input_tokens - cached_tokens, 0) + output_tokens
    )
    flags = optimization.get("avoidable_cost_flags")
    event_accounting = _dict_value(optimization.get("event_accounting"))
    return {
        "agent_name": str(_value(run, "agent_name", "") or ""),
        "raw_tokens": raw_tokens,
        "cached_tokens": cached_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "noncached_plus_output": noncached_plus_output,
        "flags": [str(flag) for flag in flags] if isinstance(flags, list) else [],
        "avoidable_token_estimate": int(optimization.get("avoidable_token_estimate") or 0),
        "chunk_pressure": {
            "available": bool(event_accounting),
            "raw_event_count": int(event_accounting.get("raw_event_count") or 0),
            "largest_event_bytes": int(event_accounting.get("largest_event_bytes") or 0),
            "largest_command_output_bytes": int(
                event_accounting.get("largest_command_output_bytes") or 0
            ),
            "chunk_pressure_risk": bool(event_accounting.get("chunk_pressure_risk")),
        },
    }


def _tool_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "command_count": 0,
        "file_read_or_search_count": 0,
        "edit_count": 0,
        "deterministic_check_count": 0,
    }
    for event in events:
        method = str(event.get("method") or "")
        _params_raw = event.get("params")
        params: dict = _params_raw if isinstance(_params_raw, dict) else {}
        _item_raw = params.get("item")
        item: dict = _item_raw if isinstance(_item_raw, dict) else {}
        item_type = str(item.get("type") or params.get("type") or "").lower()
        tool_name = str(
            item.get("name")
            or item.get("toolName")
            or item.get("tool_name")
            or item.get("title")
            or params.get("name")
            or ""
        ).lower()
        method_lower = method.lower()
        is_tool_event = (
            "tool" in method_lower
            or "commandexecution" in method_lower
            or "filechange" in method_lower
            or "tool" in item_type
            or "command" in item_type
            or bool(tool_name)
        )
        command_text = _tool_command_text(item, params)
        command_haystack = f"{tool_name} {item_type} {command_text}".lower()
        if "commandexecution" in method_lower or any(
            marker in command_haystack for marker in ("bash", "shell", "exec_command")
        ):
            counts["command_count"] += 1
        if is_tool_event and (
            tool_name in {"read", "grep", "glob"}
            or any(marker in command_haystack for marker in ("rg ", "grep ", "sed -n", "cat "))
        ):
            counts["file_read_or_search_count"] += 1
        if is_tool_event and (
            tool_name in {"edit", "write", "apply_patch"}
            or "apply_patch" in command_haystack
        ):
            counts["edit_count"] += 1
        if any(name in command_haystack for name in ("pytest", "npm test", "npm run build", "lint")):
            counts["deterministic_check_count"] += 1
    return counts


def _tool_command_text(item: Mapping[str, Any], params: Mapping[str, Any]) -> str:
    input_value = item.get("input") or params.get("input") or params.get("arguments")
    if isinstance(input_value, str):
        return input_value
    if isinstance(input_value, Mapping):
        return _first_text_value(
            input_value,
            ("cmd", "command", "query", "pattern", "file_path", "path", "text", "content"),
        ) or json.dumps(input_value, ensure_ascii=True, sort_keys=True)
    if isinstance(input_value, list):
        return json.dumps(input_value, ensure_ascii=True, sort_keys=True)
    return _first_text_value(
        item,
        ("cmd", "command", "query", "pattern", "file_path", "path"),
    ) or _first_text_value(params, ("cmd", "command", "query", "pattern", "file_path", "path"))


def _avoidable_flags(
    *,
    agent_name: str,
    status: str,
    total_tokens: int,
    output_tokens: int,
    prompt_budget: Mapping[str, Any],
    largest_event_bytes: int,
    largest_command_output_bytes: int,
    tool_counts: Mapping[str, int],
) -> list[str]:
    flags: list[str] = []
    if status == "failed" and total_tokens == 0:
        flags.append("failed_zero_token_runtime_run")
    if agent_name == "pr-creator":
        flags.append("pr_lane_without_explicit_pr_target")
    if prompt_budget.get("over_budget"):
        flags.append("prompt_over_phase_budget")
    if largest_event_bytes >= APP_SERVER_CHUNK_RISK_BYTES:
        flags.append("chunk_pressure_large_event")
    if largest_command_output_bytes >= LARGE_OUTPUT_BYTES:
        flags.append("large_command_output")
    if int(tool_counts.get("file_read_or_search_count") or 0) >= 8:
        flags.append("redundant_scan")
    if output_tokens > 2_000:
        flags.append("large_final_response")
    return flags


def _avoidable_token_estimate(
    *,
    total_tokens: int,
    noncached_plus_output: int,
    flags: list[str],
) -> int:
    if not flags:
        return 0
    if "pr_lane_without_explicit_pr_target" in flags:
        return max(total_tokens, noncached_plus_output)
    if "failed_zero_token_runtime_run" in flags:
        return 0
    return max(noncached_plus_output, total_tokens // 10)


def _recommended_next_change(
    top_cost_drivers: list[dict[str, Any]],
    flags: Counter[str],
    raw_total: int,
    *,
    active_flags: Counter[str] | None = None,
    active_top_cost_drivers: list[dict[str, Any]] | None = None,
    rework_share: float = 0.0,
) -> str:
    active_flags = active_flags or Counter()
    effective_flags = active_flags or flags
    if effective_flags.get("pr_lane_without_explicit_pr_target"):
        return "skip_model_pr_creator_for_low_risk_local_sprints"
    if effective_flags.get("prompt_over_phase_budget"):
        return "trim_prompt_segments_over_phase_budget"
    if active_flags.get("large_command_output") or active_flags.get("chunk_pressure_large_event"):
        return "truncate_tool_output_before_reinjection"
    active_driver = _first_meaningful_driver(active_top_cost_drivers or [])
    if active_driver:
        avoidable = int(active_driver.get("avoidable_token_estimate") or 0)
        noncached_plus_output = int(active_driver.get("noncached_plus_output_tokens") or 0)
        if avoidable > 0 or noncached_plus_output > 80_000:
            return f"reduce_{active_driver['agent_name']}_raw_tokens"
    if rework_share >= 0.25:
        return "reduce_rework_before_token_band"
    if raw_total > 185_000 and top_cost_drivers and not active_top_cost_drivers:
        return f"reduce_{top_cost_drivers[0]['agent_name']}_raw_tokens"
    return "maintain_current_flow"


def _first_meaningful_driver(drivers: list[dict[str, Any]]) -> dict[str, Any]:
    for driver in drivers:
        if not isinstance(driver, dict):
            continue
        if int(driver.get("raw_tokens") or 0) <= 0:
            continue
        if not str(driver.get("agent_name") or "").strip():
            continue
        return driver
    return {}


def _agent_phase(agent_name: str) -> str:
    if agent_name in CEREMONY_AGENTS:
        return "ceremony"
    if agent_name in IMPLEMENTATION_AGENTS:
        return "implementation"
    if agent_name in VERIFICATION_AGENTS:
        return "verification"
    return "other"


def _command_output_size(event: dict[str, Any]) -> int:
    method = str(event.get("method") or "")
    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    if "commandExecution" in method:
        return len(json.dumps(params, ensure_ascii=True))

    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    item_type = str(item.get("type") or params.get("type") or "").lower()
    tool_name = str(
        item.get("name") or item.get("toolName") or item.get("tool_name") or item.get("title") or ""
    ).lower()
    haystack = f"{method.lower()} {item_type} {tool_name}"
    if not any(marker in haystack for marker in ("command", "bash", "shell", "exec", "terminal")):
        return 0

    output = _first_text_value(
        item,
        ("output", "text", "content", "stdout", "stderr", "delta"),
    ) or _first_text_value(params, ("output", "text", "content", "stdout", "stderr", "delta"))
    if output:
        return len(output)
    return len(json.dumps(item or params, ensure_ascii=True))


def _first_text_value(value: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if isinstance(item, str):
            return item
        if isinstance(item, (dict, list)):
            return json.dumps(item, ensure_ascii=True, sort_keys=True)
    return ""


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=True, sort_keys=True))


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)
