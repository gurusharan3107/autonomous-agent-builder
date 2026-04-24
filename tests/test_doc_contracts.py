from __future__ import annotations

from autonomous_agent_builder.cli.doc_contracts import check_quality_gate_wording


def test_quality_gate_wording_passes_for_review_contract(tmp_path):
    gate = tmp_path / "docs" / "quality-gate" / "builder-cli.md"
    gate.parent.mkdir(parents=True)
    gate.write_text(
        (
            "---\n"
            "title: Builder CLI quality gate\n"
            "surface: builder-cli\n"
            "summary: Verify builder CLI review expectations.\n"
            "commands:\n"
            "  - builder --help\n"
            "expectations:\n"
            "  - verification remains bounded\n"
            "---\n\n"
            "# Builder CLI quality gate\n\n"
            "## Purpose\n\n"
            "Review the CLI change.\n\n"
            "## When To Load\n\n"
            "- before changing help\n\n"
            "## Pass Signals\n\n"
            "- output stays bounded\n\n"
            "## Fail Signals\n\n"
            "- internal nouns leak\n"
        ),
        encoding="utf-8",
    )

    decision = check_quality_gate_wording(gate, repo_root=tmp_path)

    assert decision.decision == "PASS"


def test_quality_gate_wording_rejects_owner_split_heading(tmp_path):
    gate = tmp_path / "docs" / "quality-gate" / "architecture-boundary.md"
    gate.parent.mkdir(parents=True)
    gate.write_text(
        (
            "---\n"
            "title: Architecture boundary quality gate\n"
            "surface: architecture-boundary\n"
            "summary: Verify boundaries.\n"
            "commands:\n"
            "  - builder map --json\n"
            "expectations:\n"
            "  - runtime boundaries remain clear\n"
            "---\n\n"
            "# Architecture boundary quality gate\n\n"
            "## Purpose\n\n"
            "Review the boundary change.\n\n"
            "## When To Load\n\n"
            "- before changing runtime seams\n\n"
            "## Owner Split\n\n"
            "- builder should own product semantics\n\n"
            "## Pass Signals\n\n"
            "- docs stay aligned\n\n"
            "## Fail Signals\n\n"
            "- ownership blurs\n"
        ),
        encoding="utf-8",
    )

    decision = check_quality_gate_wording(gate, repo_root=tmp_path)

    assert decision.decision == "CONTENT_DRIFT"
    assert any("Forbidden owner-doc heading" in reason for reason in decision.reasons)


def test_quality_gate_wording_rejects_owner_language(tmp_path):
    gate = tmp_path / "docs" / "quality-gate" / "claude-agent-sdk.md"
    gate.parent.mkdir(parents=True)
    gate.write_text(
        (
            "---\n"
            "title: Claude Agent SDK gate\n"
            "surface: claude-agent-sdk\n"
            "summary: Verify runtime changes.\n"
            "commands:\n"
            "  - builder map --json\n"
            "expectations:\n"
            "  - runtime changes stay narrow\n"
            "---\n\n"
            "# Claude Agent SDK gate\n\n"
            "## Purpose\n\n"
            "Review the runtime change.\n\n"
            "## When To Load\n\n"
            "- before changing SDK hooks\n\n"
            "The SDK remains the single owner of runtime mechanics.\n\n"
            "## Pass Signals\n\n"
            "- runtime changes stay narrow\n\n"
            "## Fail Signals\n\n"
            "- runtime and product semantics blur\n"
        ),
        encoding="utf-8",
    )

    decision = check_quality_gate_wording(gate, repo_root=tmp_path)

    assert decision.decision == "CONTENT_DRIFT"
    assert any("owner" in reason.lower() for reason in decision.reasons)
