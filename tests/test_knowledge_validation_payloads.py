"""Tests for Builder knowledge validation payload shaping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autonomous_agent_builder.cli.knowledge_validation_payloads import (
    compact_validate_output_payload,
    default_agent_advisory_payload,
    validate_output_payload,
)


@dataclass
class _Check:
    name: str
    passed: bool
    score: float
    message: str
    details: dict[str, Any] | None = None


@dataclass
class _Result:
    passed: bool
    score: float
    summary: str
    checks: list[_Check]
    blocking_docs: list[str]
    non_blocking_docs: list[str]
    claim_failures: list[str]
    unresolved_claims: list[str]
    contradicted_claims: list[str]
    workspace_profile: str = "repo"
    graph_artifact: str = ".evidence/graph.json"
    blocking_render_status: dict[str, str] | None = None
    unresolved_item_counts: dict[str, int] | None = None


def test_validate_output_payload_preserves_deterministic_evidence() -> None:
    payload = validate_output_payload(
        _Result(
            passed=False,
            score=0.5,
            summary="needs work",
            checks=[
                _Check(
                    name="freshness",
                    passed=False,
                    score=0.25,
                    message="stale",
                    details={"maintained_docs": [{"doc_id": "docs/runtime.md"}]},
                )
            ],
            blocking_docs=["docs/runtime.md"],
            non_blocking_docs=["docs/notes.md"],
            claim_failures=["claim failed"],
            unresolved_claims=["claim unresolved"],
            contradicted_claims=["claim contradicted"],
            blocking_render_status={"docs/runtime.md": "missing"},
            unresolved_item_counts={"docs/runtime.md": 1},
        )
    )

    assert payload["passed"] is False
    assert payload["freshness_report"] == [{"doc_id": "docs/runtime.md"}]
    assert payload["agent_advisory"] == default_agent_advisory_payload()
    assert payload["checks"][0]["name"] == "freshness"


def test_compact_validate_output_payload_keeps_next_actions_and_counts() -> None:
    compact = compact_validate_output_payload(
        {
            "passed": False,
            "score": 0.5,
            "summary": "needs work",
            "workspace_profile": "repo",
            "blocking_docs": ["docs/runtime.md"],
            "non_blocking_docs": ["docs/notes.md"],
            "claim_failures": ["claim failed"],
            "unresolved_claims": ["claim unresolved"],
            "contradicted_claims": ["claim contradicted"],
            "checks": [
                {
                    "name": "freshness",
                    "passed": False,
                    "score": 0.25,
                    "message": "stale",
                }
            ],
        }
    )

    assert compact["blocking_doc_count"] == 1
    assert compact["claim_failure_count"] == 1
    assert compact["unresolved_claim_count"] == 1
    assert compact["contradicted_claim_count"] == 1
    assert compact["checks"] == [
        {"name": "freshness", "passed": False, "score": 0.25, "message": "stale"}
    ]
    assert (
        "builder knowledge show docs/runtime.md" in compact["progressive_disclosure"][1]["command"]
    )
