from __future__ import annotations

import json
from types import SimpleNamespace

from autonomous_agent_builder.orchestrator.build_verification import (
    browser_evidence_tier,
    build_verifier_failure,
    feature_verifier_failure,
    is_sprint_feature_verification_task,
    is_ui_task,
    sprint_branch_name,
    task_sprint_execution_payload,
    use_deterministic_build_verifier,
    use_deterministic_evidence_collector,
)
from autonomous_agent_builder.orchestrator.deterministic_verification import (
    build_verification_output,
    feature_acceptance_output,
)
from autonomous_agent_builder.services.sprint_execution import SPRINT_EXECUTION_KEY


def test_task_sprint_execution_payload_extracts_dict_payload() -> None:
    task = SimpleNamespace(depends_on={SPRINT_EXECUTION_KEY: {"sprint_id": "sprint-1"}})

    assert task_sprint_execution_payload(task) == {"sprint_id": "sprint-1"}
    assert task_sprint_execution_payload(SimpleNamespace(depends_on=None)) == {}


def test_deterministic_verifiers_require_sprint_payload_and_workspace_path() -> None:
    task = SimpleNamespace(
        depends_on={SPRINT_EXECUTION_KEY: {"sprint_id": "sprint-1"}},
        workspace=SimpleNamespace(path="/tmp/workspace"),
    )

    assert use_deterministic_evidence_collector(task) is True
    assert use_deterministic_build_verifier(task) is True
    task.workspace.path = ""
    assert use_deterministic_build_verifier(task) is False


def test_is_sprint_feature_verification_task_matches_known_task_keys() -> None:
    task = SimpleNamespace(depends_on={SPRINT_EXECUTION_KEY: {"task_key": "browser-verification"}})

    assert is_sprint_feature_verification_task(task) is True


def test_sprint_branch_name_uses_id_prefix_and_slug() -> None:
    sprint = SimpleNamespace(id="1234567890", label="QA Sprint 2")

    assert sprint_branch_name(sprint) == "sprint/12345678-qa-sprint-2"


def test_build_verifier_failure_detects_markdown_failures() -> None:
    failure = build_verifier_failure("`npm run test` - **FAIL** (1/41)")

    assert failure == "build_verification_failed: `npm run test` - **FAIL** (1/41)"


def test_build_verifier_failure_ignores_advisory_git_status_failure() -> None:
    assert build_verifier_failure("git status FAIL: not a git repository") is None


def test_feature_verifier_failure_reads_embedded_json_status() -> None:
    failure = feature_verifier_failure(
        'verifier result: {"status": "fail", "recommended_next_action": "add browser proof"}'
    )

    assert failure == "feature_acceptance_failed: verifier_status=fail: add browser proof"


def test_build_verification_output_summarizes_failed_check_tail() -> None:
    output = build_verification_output(
        {
            "success": False,
            "data": {
                "checks": [
                    {
                        "command": ["npm", "test"],
                        "status": "failed",
                        "stderr_tail": "expected button to be visible",
                    }
                ]
            },
        },
        "",
        success=False,
    )

    assert output == "npm test FAIL: expected button to be visible"


def test_feature_acceptance_output_includes_command_criteria_and_files() -> None:
    output = feature_acceptance_output(
        {
            "status": "passed",
            "command": ["npx", "playwright", "test"],
            "acceptance_criteria": ["Persists after reload"],
            "coverage": {"matched_files": ["tests/persistence.spec.ts"]},
        },
        {},
        "",
        success=True,
    )

    assert output == "\n".join(
        [
            "Feature acceptance tests PASS (passed).",
            "Command: `npx playwright test`.",
            "Acceptance criteria: Persists after reload",
            "Matched test files: tests/persistence.spec.ts",
        ]
    )


# ── IMP-019: is_ui_task and browser_evidence_tier queryable field ──────────


def test_is_ui_task_detects_ui_keywords_in_feature_title() -> None:
    task = SimpleNamespace(title="", description="")
    feature = SimpleNamespace(
        title="Add dashboard button",
        description="",
        acceptance_criteria=[],
    )
    assert is_ui_task(task, feature) is True


def test_is_ui_task_detects_ui_keywords_in_acceptance_criteria() -> None:
    task = SimpleNamespace(title="", description="")
    feature = SimpleNamespace(
        title="User registration",
        description="",
        acceptance_criteria=["The form should display validation errors"],
    )
    assert is_ui_task(task, feature) is True


def test_is_ui_task_returns_false_for_non_ui_task() -> None:
    task = SimpleNamespace(title="", description="")
    feature = SimpleNamespace(
        title="Batch export API endpoint",
        description="Expose a REST endpoint that returns JSON",
        acceptance_criteria=["Returns 200 with expected JSON payload"],
    )
    assert is_ui_task(task, feature) is False


def test_is_ui_task_checks_task_fields_without_feature() -> None:
    task = SimpleNamespace(title="Fix CSS layout bug", description="")
    assert is_ui_task(task) is True


def test_browser_evidence_tier_result_includes_queryable_field() -> None:
    # IMP-019: the returned dict must carry a ``browser_evidence_tier`` key
    # equal to ``tier`` so callers can read it without re-parsing output_text.
    output = json.dumps({"status": "pass", "browser_evidence": ["screenshot:/tmp/x.jpeg"]})
    result = browser_evidence_tier(output, bridge_available=True, is_ui=True)
    assert result["browser_evidence_tier"] == result["tier"] == "real_browser"


def test_browser_evidence_tier_ui_task_bridge_unavailable_emits_unavailable() -> None:
    # IMP-019 real-browser gate: UI task + bridge down → "unavailable" tier with
    # a warning advisory, not silent jsdom_fallback.
    output = json.dumps({"status": "pass", "browser_evidence": []})
    result = browser_evidence_tier(output, bridge_available=False, is_ui=True)
    assert result["tier"] == "unavailable"
    assert result["browser_evidence_tier"] == "unavailable"
    assert result["advisory"]  # must include warning message


def test_browser_evidence_tier_non_ui_task_bridge_unavailable_is_jsdom_fallback() -> None:
    # Non-UI tasks with no browser evidence + bridge down → jsdom_fallback (no warning needed).
    output = json.dumps({"status": "pass", "browser_evidence": []})
    result = browser_evidence_tier(output, bridge_available=False, is_ui=False)
    assert result["tier"] == "jsdom_fallback"
    assert result["browser_evidence_tier"] == "jsdom_fallback"
