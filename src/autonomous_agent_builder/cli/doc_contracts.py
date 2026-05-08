"""Deterministic content checks for reserved documentation contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from autonomous_agent_builder.cli.doc_ownership import check_doc_ownership

_QUALITY_GATE_REQUIRED_HEADINGS = (
    "## Purpose",
    "## When To Load",
    "## Pass Signals",
    "## Fail Signals",
)
_QUALITY_GATE_FORBIDDEN_HEADINGS = (
    "## Owner Split",
    "## Ownership Contract",
    "## Canonical Ownership",
    "## Source Of Truth",
)
_QUALITY_GATE_FORBIDDEN_PATTERNS = (
    re.compile(r"^\s*#+\s+.*owner split", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bshould own\b", re.IGNORECASE),
    re.compile(r"\bis the source of truth\b", re.IGNORECASE),
    re.compile(r"\bremains the single owner of\b", re.IGNORECASE),
    re.compile(r"\bowns the repo-local product contract\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class DocContractDecision:
    decision: str
    target: str
    doc_class: str
    reasons: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "target": self.target,
            "doc_class": self.doc_class,
            "reasons": list(self.reasons),
        }


def _load_text(path: Path, content_override: str | None) -> str:
    if content_override is not None:
        return content_override
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def check_quality_gate_wording(
    target: Path,
    *,
    repo_root: Path | None = None,
    content_override: str | None = None,
) -> DocContractDecision:
    ownership = check_doc_ownership(target, repo_root=repo_root, doc_class="quality-gate")
    if ownership.decision == "NOT_APPLICABLE":
        return DocContractDecision(
            decision="NOT_APPLICABLE",
            target=str(target),
            doc_class="quality-gate",
            reasons=("Target does not look like a quality-gate doc.",),
        )

    text = _load_text(target, content_override)
    reasons: list[str] = []

    for heading in _QUALITY_GATE_REQUIRED_HEADINGS:
        if heading not in text:
            reasons.append(f"Missing required gate heading: {heading}")

    for heading in _QUALITY_GATE_FORBIDDEN_HEADINGS:
        if heading in text:
            reasons.append(f"Forbidden owner-doc heading in quality gate: {heading}")

    for pattern in _QUALITY_GATE_FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        if match:
            reasons.append(
                "Owner-doc wording detected in quality gate: "
                + " ".join(match.group(0).split())
            )

    if reasons:
        return DocContractDecision(
            decision="CONTENT_DRIFT",
            target=str(target),
            doc_class="quality-gate",
            reasons=tuple(reasons),
        )

    return DocContractDecision(
        decision="PASS",
        target=str(target),
        doc_class="quality-gate",
        reasons=("Quality-gate wording matches the review-contract shape.",),
    )
