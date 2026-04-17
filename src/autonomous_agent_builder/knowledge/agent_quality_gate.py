"""Agent-based quality gate for knowledge extraction validation.

Uses Claude Agent SDK to dynamically evaluate knowledge base quality.
More flexible and intelligent than hardcoded rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from claude_agent_sdk import Agent, query

log = structlog.get_logger()


@dataclass
class AgentQualityGateResult:
    """Result from agent-based quality gate."""

    passed: bool
    score: float  # 0.0 to 1.0
    summary: str
    evaluation: dict[str, Any]
    recommendations: list[str]
    agent_reasoning: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "passed": self.passed,
            "score": self.score,
            "summary": self.summary,
            "evaluation": self.evaluation,
            "recommendations": self.recommendations,
            "agent_reasoning": self.agent_reasoning,
        }


class AgentKnowledgeQualityGate:
    """Agent-based quality gate using Claude SDK for dynamic evaluation."""

    EVALUATION_PROMPT = """You are a technical documentation quality evaluator. Your task is to assess the quality of an automatically generated knowledge base.

## Context

A knowledge extraction system has analyzed a codebase and generated documentation. You need to evaluate the quality of this documentation to ensure it's useful for AI agents and developers.

## Knowledge Base Contents

{kb_summary}

## Evaluation Criteria

Evaluate the knowledge base across these dimensions:

### 1. Completeness (25%)
- Are all expected document types present?
- Expected: project-overview, technology-stack, dependencies, system-architecture, code-structure, database-models, api-endpoints, business-overview, workflows-and-orchestration, configuration, agent-system
- Is critical information missing?

### 2. Content Quality (25%)
- Is there sufficient detail in each document?
- Are sections well-populated (not empty or stub)?
- Is the information accurate and specific (not generic)?
- Are code examples, diagrams, or data included where appropriate?

### 3. Usefulness (20%)
- Would this documentation help an AI agent understand the codebase?
- Would this help a new developer onboard?
- Are the right level of abstraction and detail provided?
- Is the information actionable?

### 4. Structure & Clarity (15%)
- Is the documentation well-organized?
- Are headers and sections logical?
- Is the markdown properly formatted?
- Is the writing clear and concise?

### 5. Accuracy (10%)
- Does the information appear correct based on the content?
- Are there obvious errors or inconsistencies?
- Do technical details make sense?

### 6. Searchability (5%)
- Are documents properly tagged?
- Are key terms and concepts highlighted?
- Would someone be able to find information easily?

## Your Task

1. Review the knowledge base summary and sample documents
2. Evaluate each criterion (score 0-100 for each)
3. Calculate overall score (weighted average)
4. Determine if quality gate PASSES (score >= 75) or FAILS
5. Provide specific recommendations for improvement

## Output Format

Respond with a JSON object:

```json
{{
  "passed": true/false,
  "overall_score": 0-100,
  "criteria_scores": {{
    "completeness": 0-100,
    "content_quality": 0-100,
    "usefulness": 0-100,
    "structure_clarity": 0-100,
    "accuracy": 0-100,
    "searchability": 0-100
  }},
  "strengths": ["strength 1", "strength 2", ...],
  "weaknesses": ["weakness 1", "weakness 2", ...],
  "recommendations": ["recommendation 1", "recommendation 2", ...],
  "reasoning": "Brief explanation of your evaluation"
}}
```

Be thorough but concise. Focus on actionable feedback.
"""

    def __init__(self, kb_path: Path, workspace_path: Path):
        """Initialize agent-based quality gate.

        Args:
            kb_path: Path to knowledge base directory
            workspace_path: Path to workspace being analyzed
        """
        self.kb_path = kb_path
        self.workspace_path = workspace_path

    def validate(self, model: str = "claude-sonnet-4-20250514") -> AgentQualityGateResult:
        """Run agent-based quality evaluation.

        Args:
            model: Claude model to use for evaluation

        Returns:
            AgentQualityGateResult with evaluation details
        """
        # Gather knowledge base summary
        kb_summary = self._gather_kb_summary()

        # Build evaluation prompt
        prompt = self.EVALUATION_PROMPT.format(kb_summary=kb_summary)

        # Query Claude agent
        log.info("agent_quality_gate_start", kb_path=str(self.kb_path))

        try:
            response = query(
                prompt=prompt,
                model=model,
                max_turns=5,
                tools=[],  # No tools needed for evaluation
            )

            # Parse response
            result = self._parse_agent_response(response)

            log.info(
                "agent_quality_gate_complete",
                passed=result.passed,
                score=result.score,
            )

            return result

        except Exception as e:
            log.error("agent_quality_gate_error", error=str(e))
            # Fallback to basic validation
            return AgentQualityGateResult(
                passed=False,
                score=0.0,
                summary=f"Quality gate error: {e}",
                evaluation={},
                recommendations=["Fix quality gate execution error"],
                agent_reasoning=f"Error during evaluation: {e}",
            )

    def _gather_kb_summary(self) -> str:
        """Gather summary of knowledge base for agent evaluation."""
        if not self.kb_path.exists():
            return "ERROR: Knowledge base directory does not exist"

        summary_parts = []

        # List all documents
        doc_files = sorted(self.kb_path.glob("*.md"))
        summary_parts.append(f"## Documents Generated ({len(doc_files)} total)\n")

        for doc_file in doc_files:
            if doc_file.stem == "extraction-metadata":
                continue

            content = doc_file.read_text(encoding="utf-8")

            # Extract frontmatter
            frontmatter = self._extract_frontmatter(content)
            title = frontmatter.get("title", doc_file.stem)
            tags = frontmatter.get("tags", [])

            # Get content preview (first 500 chars of body)
            body = self._extract_body(content)
            preview = body[:500] + "..." if len(body) > 500 else body

            # Count sections
            section_count = body.count("\n## ")

            summary_parts.append(f"### {title}")
            summary_parts.append(f"- **File**: {doc_file.name}")
            summary_parts.append(f"- **Tags**: {', '.join(tags)}")
            summary_parts.append(f"- **Length**: {len(body)} characters")
            summary_parts.append(f"- **Sections**: {section_count}")
            summary_parts.append(f"- **Preview**:\n```\n{preview}\n```\n")

        # Add metadata if exists
        metadata_file = self.kb_path / "extraction-metadata.md"
        if metadata_file.exists():
            metadata_content = metadata_file.read_text(encoding="utf-8")
            summary_parts.append("## Extraction Metadata\n")
            summary_parts.append(f"```\n{metadata_content[:1000]}\n```\n")

        return "\n".join(summary_parts)

    def _extract_frontmatter(self, content: str) -> dict[str, Any]:
        """Extract YAML frontmatter as dict."""
        if not content.startswith("---"):
            return {}

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}

        frontmatter_text = parts[1]
        result = {}

        # Simple YAML parsing (just key: value pairs)
        for line in frontmatter_text.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"')

                # Handle tags array
                if key == "tags" and "[" in value:
                    tags = value.strip("[]").split(",")
                    result[key] = [t.strip().strip('"') for t in tags]
                else:
                    result[key] = value

        return result

    def _extract_body(self, content: str) -> str:
        """Extract body content (remove frontmatter)."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content

    def _parse_agent_response(self, response: str) -> AgentQualityGateResult:
        """Parse agent response into structured result."""
        # Extract JSON from response
        try:
            # Try to find JSON block
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_text = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                json_text = response[json_start:json_end].strip()
            else:
                # Try to parse entire response as JSON
                json_text = response.strip()

            evaluation = json.loads(json_text)

            # Extract fields
            passed = evaluation.get("passed", False)
            overall_score = evaluation.get("overall_score", 0)
            criteria_scores = evaluation.get("criteria_scores", {})
            strengths = evaluation.get("strengths", [])
            weaknesses = evaluation.get("weaknesses", [])
            recommendations = evaluation.get("recommendations", [])
            reasoning = evaluation.get("reasoning", "")

            # Normalize score to 0-1
            score = overall_score / 100.0

            # Build summary
            summary = f"Quality Gate: {'PASSED' if passed else 'FAILED'} (score: {overall_score}/100)"

            return AgentQualityGateResult(
                passed=passed,
                score=score,
                summary=summary,
                evaluation={
                    "criteria_scores": criteria_scores,
                    "strengths": strengths,
                    "weaknesses": weaknesses,
                },
                recommendations=recommendations,
                agent_reasoning=reasoning,
            )

        except Exception as e:
            log.error("agent_response_parse_error", error=str(e), response=response[:500])

            # Fallback: try to extract pass/fail from text
            passed = "pass" in response.lower() and "fail" not in response.lower()
            score = 0.5

            return AgentQualityGateResult(
                passed=passed,
                score=score,
                summary=f"Quality Gate: {'PASSED' if passed else 'FAILED'} (parse error)",
                evaluation={"raw_response": response[:1000]},
                recommendations=["Review agent response manually"],
                agent_reasoning=response[:500],
            )
