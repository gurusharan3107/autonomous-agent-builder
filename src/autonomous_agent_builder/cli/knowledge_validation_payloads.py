"""Payload shaping for `builder knowledge validate`."""

from __future__ import annotations

from typing import Any

from autonomous_agent_builder.cli.output import truncate


def default_agent_advisory_payload() -> dict[str, Any]:
    return {
        "available": False,
        "passed": False,
        "score": 0.0,
        "summary": "",
        "recommendations": [],
    }


def validate_output_payload(
    deterministic_result: Any,
    *,
    agent_advisory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    freshness_report = next(
        (
            list((check.details or {}).get("maintained_docs", []))
            for check in getattr(deterministic_result, "checks", [])
            if getattr(check, "name", "") == "freshness"
        ),
        [],
    )
    return {
        "passed": bool(deterministic_result.passed),
        "score": float(deterministic_result.score),
        "summary": str(deterministic_result.summary),
        "blocking_docs": list(getattr(deterministic_result, "blocking_docs", [])),
        "non_blocking_docs": list(getattr(deterministic_result, "non_blocking_docs", [])),
        "claim_failures": list(getattr(deterministic_result, "claim_failures", [])),
        "unresolved_claims": list(getattr(deterministic_result, "unresolved_claims", [])),
        "contradicted_claims": list(getattr(deterministic_result, "contradicted_claims", [])),
        "workspace_profile": str(getattr(deterministic_result, "workspace_profile", "")),
        "graph_artifact": str(getattr(deterministic_result, "graph_artifact", "")),
        "blocking_render_status": dict(getattr(deterministic_result, "blocking_render_status", {})),
        "unresolved_item_counts": dict(getattr(deterministic_result, "unresolved_item_counts", {})),
        "freshness_report": freshness_report,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "score": check.score,
                "message": check.message,
                "details": check.details,
            }
            for check in getattr(deterministic_result, "checks", [])
        ],
        "agent_advisory": agent_advisory or default_agent_advisory_payload(),
    }


def compact_validate_output_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    compact_checks = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        compact_checks.append(
            {
                "name": check.get("name", ""),
                "passed": bool(check.get("passed")),
                "score": check.get("score", 0),
                "message": truncate(str(check.get("message", "") or ""), 240),
            }
        )
    blocking_docs = [str(item) for item in (payload.get("blocking_docs", []) or [])[:10]]
    claim_failures = [
        truncate(str(item), 260) for item in (payload.get("claim_failures", []) or [])[:10]
    ]
    unresolved_claims = [
        truncate(str(item), 260) for item in (payload.get("unresolved_claims", []) or [])[:10]
    ]
    next_step = (
        "Open blocking docs with `builder knowledge show <doc-id> --section 'Change guidance' "
        "or rerun `builder knowledge validate --json --full` for nested evidence."
    )
    doc_hint = blocking_docs[0] if blocking_docs else "<doc-id>"
    return {
        "passed": bool(payload.get("passed")),
        "score": payload.get("score", 0),
        "summary": truncate(str(payload.get("summary", "") or ""), 360),
        "workspace_profile": payload.get("workspace_profile", ""),
        "blocking_doc_count": len(payload.get("blocking_docs", []) or []),
        "blocking_docs": blocking_docs,
        "non_blocking_doc_count": len(payload.get("non_blocking_docs", []) or []),
        "claim_failure_count": len(payload.get("claim_failures", []) or []),
        "claim_failures": claim_failures,
        "unresolved_claim_count": len(payload.get("unresolved_claims", []) or []),
        "unresolved_claims": unresolved_claims,
        "contradicted_claim_count": len(payload.get("contradicted_claims", []) or []),
        "checks": compact_checks,
        "actionable_next": next_step,
        "next_step": next_step,
        "progressive_disclosure": [
            {
                "when": "inspect the most relevant repo-local doc summary",
                "command": "builder knowledge summary <query>",
            },
            {
                "when": "inspect change guidance for a blocking or changed doc",
                "command": f"builder knowledge show {doc_hint} --section 'Change guidance' --json",
            },
            {
                "when": "refresh extracted docs after code or manifest changes",
                "command": "builder knowledge extract --force --json",
            },
            {
                "when": "inspect nested validation evidence, claim details, freshness, and graph artifact",
                "command": "builder knowledge validate --json --full",
            },
        ],
        "diagnostics": {
            "full_payload_command": "builder knowledge validate --json --full",
            "contains": [
                "blocking doc ids",
                "claim failure details",
                "freshness report",
                "check details",
                "graph artifact",
            ],
        },
        "agent_advisory": payload.get("agent_advisory", default_agent_advisory_payload()),
    }
