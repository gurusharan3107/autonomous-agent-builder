from __future__ import annotations

from autonomous_agent_builder.knowledge.documentation_freshness_ci import (
    prepare_documentation_freshness_plan,
)


def test_prepare_plan_skips_agent_when_validation_already_passes() -> None:
    plan = prepare_documentation_freshness_plan(
        {
            "passed": True,
            "summary": "All blocking docs are fresh.",
            "checks": [{"name": "freshness", "passed": True, "details": {"maintained_docs": []}}],
            "freshness_report": [],
        }
    )

    assert plan.mode == "no_op"
    assert plan.prompt == ""
    assert plan.actionable_docs == ()


def test_prepare_plan_routes_only_bounded_freshness_failures_to_agent(tmp_path) -> None:
    payload = {
        "passed": False,
        "summary": "1 freshness issue detected",
        "checks": [{"name": "freshness", "passed": False, "details": {}}],
        "freshness_report": [
            {
                "doc_id": "feature-onboarding",
                "doc_type": "feature",
                "status": "stale",
                "blocking": True,
                "stale_reason": "owned_paths changed on main since documented baseline",
                "owned_paths": ["src/onboarding", "frontend/src/pages/OnboardingPage.tsx"],
                "matched_changed_paths": ["src/onboarding/service.py"],
                "documented_against_commit": "abc123",
                "current_main_commit": "def456",
            }
        ],
    }

    plan = prepare_documentation_freshness_plan(payload, workspace_path=tmp_path)

    assert plan.mode == "run_agent"
    assert plan.actionable_docs[0].doc_id == "feature-onboarding"
    assert "Refresh only the maintained docs listed below." in plan.prompt
    assert "feature-onboarding" in plan.prompt
    assert str(tmp_path.resolve()) in plan.prompt


def test_prepare_plan_requires_manual_attention_for_non_freshness_failures() -> None:
    payload = {
        "passed": False,
        "summary": "validation failed",
        "checks": [
            {"name": "freshness", "passed": False, "details": {}},
            {"name": "claim_validation", "passed": False, "details": {}},
        ],
        "freshness_report": [
            {
                "doc_id": "feature-onboarding",
                "doc_type": "feature",
                "status": "stale",
                "blocking": True,
                "stale_reason": "owned_paths changed on main since documented baseline",
                "owned_paths": ["src/onboarding"],
                "matched_changed_paths": ["src/onboarding/service.py"],
                "documented_against_commit": "abc123",
                "current_main_commit": "def456",
            }
        ],
    }

    plan = prepare_documentation_freshness_plan(payload)

    assert plan.mode == "manual_attention"
    assert "claim_validation" in plan.manual_attention_reasons[0]


def test_prepare_plan_requires_manual_attention_when_main_head_is_unresolved() -> None:
    payload = {
        "passed": False,
        "summary": "freshness blocked",
        "checks": [{"name": "freshness", "passed": False, "details": {}}],
        "freshness_report": [
            {
                "doc_id": "feature-onboarding",
                "doc_type": "feature",
                "status": "blocked",
                "blocking": True,
                "stale_reason": "unable to resolve main head",
                "owned_paths": ["src/onboarding"],
                "matched_changed_paths": [],
                "documented_against_commit": "abc123",
                "current_main_commit": "",
            }
        ],
    }

    plan = prepare_documentation_freshness_plan(payload)

    assert plan.mode == "manual_attention"
    assert "unable to resolve main head" in plan.manual_attention_reasons[0]
