from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from autonomous_agent_builder.knowledge.agent_quality_gate import (
    AgentKnowledgeQualityGate,
)


def _write_kb_doc(kb_path: Path) -> None:
    kb_path.mkdir(parents=True)
    (kb_path / "project-overview.md").write_text(
        """---
title: Project Overview
tags:
  - system-docs
  - local
doc_type: system-docs
---

## Overview
This is enough content for the quality gate test.
""",
        encoding="utf-8",
    )


def test_validate_async_consumes_streamed_sdk_messages(tmp_path, monkeypatch):
    kb_path = tmp_path / "knowledge"
    _write_kb_doc(kb_path)

    gate = AgentKnowledgeQualityGate(kb_path, tmp_path)

    async def fake_run(prompt, *, workspace_path, model, allowed_tools):
        assert "Project Overview" in prompt
        assert workspace_path == tmp_path
        assert model == "claude-haiku-4-5-20251001"
        assert allowed_tools == []
        return """```json
{
  "passed": true,
  "overall_score": 91,
  "criteria_scores": {"completeness": 90},
  "strengths": ["Clear structure"],
  "weaknesses": [],
  "recommendations": ["Keep the current contract"],
  "reasoning": "The generated document is detailed and specific."
}
```"""

    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.agent_quality_gate.run_claude_prompt",
        fake_run,
    )

    result = asyncio.run(gate.validate_async())

    assert result.passed is True
    assert result.score == 0.91
    assert result.summary == "Quality Gate: PASSED (score: 91/100)"
    assert result.evaluation["criteria_scores"] == {"completeness": 90}
    assert result.recommendations == ["Keep the current contract"]
    assert result.agent_reasoning == "The generated document is detailed and specific."


def test_validate_async_falls_back_to_rule_based_gate_on_sdk_error(tmp_path, monkeypatch):
    kb_path = tmp_path / "knowledge"
    _write_kb_doc(kb_path)

    gate = AgentKnowledgeQualityGate(kb_path, tmp_path)

    async def failing_run(prompt, *, workspace_path, model, allowed_tools):
        raise RuntimeError("Not logged in · Please run /login")

    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.agent_quality_gate.run_claude_prompt",
        failing_run,
    )

    result = asyncio.run(gate.validate_async())

    assert result.passed is False
    assert result.score > 0.0
    assert result.evaluation["fallback"] == "rule-based"
    assert result.evaluation["checks"]
    assert "Not logged in" in result.summary
    assert result.recommendations == [
        "Run `/login` in Claude Code to restore agent-based evaluation."
    ]
    assert "Rule-based fallback used instead" in result.agent_reasoning


def test_validate_raises_inside_existing_event_loop(tmp_path):
    kb_path = tmp_path / "knowledge"
    _write_kb_doc(kb_path)

    gate = AgentKnowledgeQualityGate(kb_path, tmp_path)

    async def call_validate() -> None:
        with pytest.raises(RuntimeError, match="validate_async"):
            gate.validate()

    asyncio.run(call_validate())
