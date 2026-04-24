"""Knowledge Base Document Format Specification and Linter.

This module defines the required format for all generated knowledge base documents
and provides validation/linting functionality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

STANDARD_DOC_TYPES = (
    "context",
    "adr",
    "api_contract",
    "schema",
    "runbook",
    "system-docs",
    "feature",
    "testing",
    "metadata",
    "raw",
)

# Single owner for the default contract surfaced by `builder knowledge contract`.
# System-docs is the repo's canonical local KB document family.
DEFAULT_KB_CONTRACT_TYPE = "system-docs"

BASE_CONTRACT_RULES = [
    "Start with valid YAML frontmatter bounded by --- lines.",
    "Body must include an H1 that matches the title and at least one substantive section.",
    "Write for the reading pane: strong title, lede paragraph, editorial sections, short metadata.",
    "Do not dump raw notes, prompts, or unstructured logs into the article body.",
    "Prefer readable paragraphs, concise bullet lists, and framed code blocks with language labels.",
]

DOC_TYPE_PRESENTATION_FIELDS: dict[str, list[dict[str, Any]]] = {
    "system-docs": [
        {
            "field": "card_summary",
            "max_words": 18,
            "purpose": "One concise result-card preview. Start with the repo-specific finding, not generic framing.",
        },
        {
            "field": "detail_summary",
            "max_words": 58,
            "purpose": "Longer reading-pane summary. Explain what the document covers and why it matters operationally.",
        },
    ],
    "feature": [
        {
            "field": "card_summary",
            "max_words": 18,
            "purpose": "Brief feature summary for fast scanning.",
        },
        {
            "field": "detail_summary",
            "max_words": 58,
            "purpose": "Longer summary of current behavior, boundaries, and verification state.",
        },
    ],
    "testing": [
        {
            "field": "card_summary",
            "max_words": 18,
            "purpose": "Short verification summary for operators and agents.",
        },
        {
            "field": "detail_summary",
            "max_words": 58,
            "purpose": "Summarize what this testing doc covers and how it should be used.",
        },
    ],
}

DOC_TYPE_SECTION_GUIDANCE: dict[str, list[str]] = {
    "context": [
        "# Title",
        "## Overview",
        "## Key points",
        "## Constraints or caveats",
        "## Operational next step",
    ],
    "adr": [
        "# Title",
        "## Status",
        "## Context",
        "## Decision",
        "## Consequences",
    ],
    "api_contract": [
        "# Title",
        "## Overview",
        "## Endpoints or operations",
        "## Request and response details",
        "## Failure modes",
    ],
    "schema": [
        "# Title",
        "## Overview",
        "## Entities or models",
        "## Relationships",
        "## Constraints",
    ],
    "runbook": [
        "# Title",
        "## Purpose",
        "## Preconditions",
        "## Procedure",
        "## Verification",
        "## Rollback or escalation",
    ],
    "system-docs": [
        "# Title",
        "## Overview",
        "## Boundaries",
        "## Invariants",
        "## Evidence",
        "## Change guidance",
    ],
    "feature": [
        "# Title",
        "## Overview",
        "## Current behavior",
        "## Boundaries",
        "## Verification",
        "## Change guidance",
    ],
    "testing": [
        "# Title",
        "## Purpose",
        "## Coverage",
        "## Preconditions",
        "## Procedure",
        "## Evidence and follow-up",
    ],
    "metadata": [
        "# Title",
        "## Summary",
        "## Generated artifacts",
        "## Usage",
    ],
    "raw": [
        "# Title",
        "## Insight",
        "## Evidence",
        "## Applicability",
    ],
}

DOC_TYPE_SECTION_BUDGETS: dict[str, list[dict[str, Any]]] = {
    "context": [
        {"heading": "Overview", "purpose": "State what the operator should understand first.", "min_words": 30, "max_words": 90},
        {"heading": "Key points", "purpose": "Capture the main reusable takeaways.", "min_words": 30, "max_words": 140},
        {"heading": "Constraints or caveats", "purpose": "List boundaries, risks, and things that change the decision.", "min_words": 20, "max_words": 120},
        {"heading": "Operational next step", "purpose": "Say what to do with this knowledge next.", "min_words": 12, "max_words": 60},
    ],
    "adr": [
        {"heading": "Status", "purpose": "Record the current ADR state in one concise line.", "min_words": 1, "max_words": 12},
        {"heading": "Context", "purpose": "Explain the problem and forcing conditions.", "min_words": 35, "max_words": 140},
        {"heading": "Decision", "purpose": "State the chosen path clearly.", "min_words": 35, "max_words": 160},
        {"heading": "Consequences", "purpose": "List expected benefits, costs, and tradeoffs.", "min_words": 20, "max_words": 140},
    ],
    "api_contract": [
        {"heading": "Overview", "purpose": "Describe the contract surface and intended use.", "min_words": 30, "max_words": 100},
        {"heading": "Endpoints or operations", "purpose": "List the callable surfaces that matter.", "min_words": 30, "max_words": 180},
        {"heading": "Request and response details", "purpose": "Show the fields, shapes, and important constraints.", "min_words": 35, "max_words": 220},
        {"heading": "Failure modes", "purpose": "Describe errors, edge cases, and expected handling.", "min_words": 20, "max_words": 120},
    ],
    "schema": [
        {"heading": "Overview", "purpose": "Summarize what this schema governs.", "min_words": 25, "max_words": 90},
        {"heading": "Entities or models", "purpose": "List the core entities and their responsibilities.", "min_words": 35, "max_words": 180},
        {"heading": "Relationships", "purpose": "Explain how entities connect.", "min_words": 20, "max_words": 120},
        {"heading": "Constraints", "purpose": "State integrity rules and invariants.", "min_words": 20, "max_words": 120},
    ],
    "runbook": [
        {"heading": "Purpose", "purpose": "State when to use this runbook.", "min_words": 20, "max_words": 70},
        {"heading": "Preconditions", "purpose": "List prerequisites and required state.", "min_words": 15, "max_words": 90},
        {"heading": "Procedure", "purpose": "Lay out the actual operating steps.", "min_words": 40, "max_words": 240},
        {"heading": "Verification", "purpose": "Explain how to confirm success.", "min_words": 15, "max_words": 90},
        {"heading": "Rollback or escalation", "purpose": "State fallback and escalation moves.", "min_words": 15, "max_words": 90},
    ],
    "system-docs": [
        {"heading": "Overview", "purpose": "Summarize the surface and why it matters.", "min_words": 30, "max_words": 80},
        {"heading": "Boundaries", "purpose": "Name the owning paths, entrypoints, and adjacent surfaces.", "min_words": 20, "max_words": 90},
        {"heading": "Invariants", "purpose": "List the facts or contracts that must remain true during changes.", "min_words": 20, "max_words": 120},
        {"heading": "Evidence", "purpose": "Preserve the detailed proof, subsections, diagrams, and examples.", "min_words": 60, "max_words": 420},
        {"heading": "Change guidance", "purpose": "Say how an operator or agent should change and verify this surface.", "min_words": 12, "max_words": 60},
    ],
    "feature": [
        {"heading": "Overview", "purpose": "Describe the capability and why it matters.", "min_words": 24, "max_words": 80},
        {"heading": "Current behavior", "purpose": "Explain the live implementation, outcomes, and constraints.", "min_words": 30, "max_words": 140},
        {"heading": "Boundaries", "purpose": "Name the owning paths, routes, jobs, and adjacent surfaces.", "min_words": 20, "max_words": 90},
        {"heading": "Verification", "purpose": "Point to the testing doc or exact checks that prove this feature works.", "min_words": 18, "max_words": 100},
        {"heading": "Change guidance", "purpose": "Explain when this doc must be refreshed after changes.", "min_words": 12, "max_words": 70},
    ],
    "testing": [
        {"heading": "Purpose", "purpose": "State the verification objective.", "min_words": 18, "max_words": 70},
        {"heading": "Coverage", "purpose": "List the flows, endpoints, or UI paths covered.", "min_words": 18, "max_words": 110},
        {"heading": "Preconditions", "purpose": "List data, services, credentials, and setup requirements.", "min_words": 12, "max_words": 90},
        {"heading": "Procedure", "purpose": "Lay out the exact validation steps the agent should follow.", "min_words": 30, "max_words": 200},
        {"heading": "Evidence and follow-up", "purpose": "Describe what proof to capture and what makes the doc stale.", "min_words": 18, "max_words": 120},
    ],
    "metadata": [
        {"heading": "Summary", "purpose": "Explain what was generated and when.", "min_words": 12, "max_words": 70},
        {"heading": "Generated artifacts", "purpose": "List the created documents.", "min_words": 15, "max_words": 140},
        {"heading": "Usage", "purpose": "Explain how to use the generated set.", "min_words": 12, "max_words": 70},
    ],
    "raw": [
        {"heading": "Insight", "purpose": "State the distilled claim or takeaway.", "min_words": 30, "max_words": 90},
        {"heading": "Evidence", "purpose": "Give the proof, quote context, or concrete support.", "min_words": 20, "max_words": 90},
        {"heading": "Applicability", "purpose": "Translate the insight into operational use.", "min_words": 20, "max_words": 90},
    ],
}

DOC_TYPE_SECTION_EXPECTATIONS: dict[str, list[dict[str, str]]] = {
    "system-docs": [
        {
            "heading": "Overview",
            "expectation": "Summarize the actual repository surface, subsystem, or workflow this document explains. Lead with the specific capability, not a generic seed-doc disclaimer.",
        },
        {
            "heading": "Boundaries",
            "expectation": "Name the code paths, entrypoints, route groups, models, or neighboring surfaces that define ownership and blast radius.",
        },
        {
            "heading": "Invariants",
            "expectation": "List the contracts or truths that must remain intact when modifying this surface. Prefer bullets with concrete constraints over descriptive prose.",
        },
        {
            "heading": "Evidence",
            "expectation": "Preserve the proof: concrete code paths, route groups, entities, config knobs, or execution steps. Keep each subsection factual and scannable.",
        },
        {
            "heading": "Change guidance",
            "expectation": "Say how to change, validate, or refresh this knowledge after code changes. Mention the exact builder command when that is the operator action.",
        },
    ],
    "feature": [
        {
            "heading": "Overview",
            "expectation": "Describe the user or operator capability in current product terms.",
        },
        {
            "heading": "Current behavior",
            "expectation": "Explain the live behavior and important branches without speculative scope.",
        },
        {
            "heading": "Boundaries",
            "expectation": "Name the routes, jobs, files, APIs, and adjacent surfaces that own this feature.",
        },
        {
            "heading": "Verification",
            "expectation": "Link the feature to its testing doc or exact validation procedure.",
        },
        {
            "heading": "Change guidance",
            "expectation": "Tell the agent when this feature doc must be refreshed after implementation work.",
        },
    ],
    "testing": [
        {
            "heading": "Purpose",
            "expectation": "State the exact verification goal and the linked feature or surface.",
        },
        {
            "heading": "Coverage",
            "expectation": "List the flows, endpoints, or UI paths this testing procedure covers.",
        },
        {
            "heading": "Preconditions",
            "expectation": "Record the setup and environment requirements needed before running checks.",
        },
        {
            "heading": "Procedure",
            "expectation": "Provide deterministic API/browser/test commands or steps the agent should follow.",
        },
        {
            "heading": "Evidence and follow-up",
            "expectation": "Specify what proof to capture and what changes make this testing doc stale.",
        },
    ],
}


def _normalize_doc_type(doc_type: str) -> str:
    normalized = doc_type.strip().lower()
    if normalized == "reverse-engineering":
        normalized = "system-docs"
    if normalized not in STANDARD_DOC_TYPES:
        raise ValueError(
            f"Unsupported doc_type '{doc_type}'. Expected one of: {', '.join(STANDARD_DOC_TYPES)}"
        )
    return normalized


def default_section_guidance(doc_type: str) -> list[str]:
    """Return the canonical section pattern for a document type."""
    return DOC_TYPE_SECTION_GUIDANCE[_normalize_doc_type(doc_type)]


def section_budget_guidance(doc_type: str) -> list[dict[str, Any]]:
    """Return the recommended section budgets and purposes for a document type."""
    return DOC_TYPE_SECTION_BUDGETS[_normalize_doc_type(doc_type)]


def presentation_field_guidance(doc_type: str) -> list[dict[str, Any]]:
    """Return optional UI-facing summary fields for a document type."""
    return DOC_TYPE_PRESENTATION_FIELDS.get(_normalize_doc_type(doc_type), [])


def section_expectations(doc_type: str) -> list[dict[str, str]]:
    """Return section-specific writing expectations for a document type."""
    return DOC_TYPE_SECTION_EXPECTATIONS.get(_normalize_doc_type(doc_type), [])


def build_frontmatter(
    *,
    title: str,
    tags: list[str],
    doc_type: str,
    created: str | None = None,
    auto_generated: bool = True,
    version: int = 1,
    updated: str | None = None,
    wikilinks: list[str] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> str:
    """Render canonical YAML frontmatter for a KB document."""
    payload: dict[str, Any] = {
        "title": title,
        "tags": tags,
        "doc_type": _normalize_doc_type(doc_type),
        "created": created or datetime.now().isoformat(),
        "auto_generated": auto_generated,
        "version": version,
    }
    if updated:
        payload["updated"] = updated
    if wikilinks:
        payload["wikilinks"] = wikilinks
    if extra_fields:
        payload.update(extra_fields)

    return f"---\n{yaml.safe_dump(payload, sort_keys=False, allow_unicode=False).strip()}\n---"


def build_document_markdown(
    *,
    title: str,
    tags: list[str],
    doc_type: str,
    body: str,
    created: str | None = None,
    auto_generated: bool = True,
    version: int = 1,
    updated: str | None = None,
    wikilinks: list[str] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> str:
    """Build a full markdown document from the canonical contract."""
    frontmatter = build_frontmatter(
        title=title,
        tags=tags,
        doc_type=doc_type,
        created=created,
        auto_generated=auto_generated,
        version=version,
        updated=updated,
        wikilinks=wikilinks,
        extra_fields=extra_fields,
    )
    return f"{frontmatter}\n\n{body.strip()}\n"


def contract_payload(
    doc_type: str = DEFAULT_KB_CONTRACT_TYPE,
    sample_title: str = "Document Title",
) -> dict[str, Any]:
    """Return the canonical KB contract as structured data for CLI/agents."""
    normalized = _normalize_doc_type(doc_type)
    sample_body = "\n\n".join(
        [
            f"# {sample_title}",
            "A short lede paragraph that explains why this document matters and what the operator should understand first.",
            *[
                f"{section}\nAdd concrete evidence, structure, and operationally useful detail here."
                for section in default_section_guidance(normalized)[1:]
            ],
        ]
    )
    return {
        "doc_type": normalized,
        "required_frontmatter": {
            "title": "string",
            "tags": "array[string]",
            "doc_type": "string",
            "created": "iso8601 timestamp",
            "auto_generated": "boolean",
            "version": "integer >= 1",
        },
        "optional_frontmatter": {
            "updated": "iso8601 timestamp",
            "wikilinks": "array[string]",
            "source_url": "string",
            "source_title": "string",
            "source_author": "string",
            "date_published": "ISO date string",
            "card_summary": "string",
            "detail_summary": "string",
            "doc_family": "string",
            "linked_feature": "string",
            "feature_id": "string",
            "refresh_required": "boolean",
            "documented_against_commit": "git commit sha",
            "documented_against_ref": "string",
            "owned_paths": "array[string]",
            "last_verified_at": "iso8601 timestamp",
            "verified_with": "string",
        },
        "rules": BASE_CONTRACT_RULES,
        "required_sections": default_section_guidance(normalized),
        "section_budgets": section_budget_guidance(normalized),
        "presentation_fields": presentation_field_guidance(normalized),
        "section_expectations": section_expectations(normalized),
        "sample_markdown": build_document_markdown(
            title=sample_title,
            tags=[normalized, "example"],
            doc_type=normalized,
            body=sample_body,
            extra_fields={
                "card_summary": "Short result-card summary for fast scanning.",
                "detail_summary": "Longer reading-pane summary explaining what the document covers and why it matters.",
                "doc_family": "seed" if normalized == "system-docs" else None,
            }
            if normalized in {"system-docs", "feature", "testing"}
            else None,
        ),
    }


def contract_prompt_block(doc_type: str, sample_title: str, tags: list[str]) -> str:
    """Return the canonical KB contract phrased for LLM prompts."""
    payload = contract_payload(doc_type=doc_type, sample_title=sample_title)
    rules = "\n".join(f"- {rule}" for rule in payload["rules"])
    sections = "\n".join(f"- {section}" for section in payload["required_sections"])
    return (
        "Use this exact document contract:\n\n"
        f"{rules}\n\n"
        "Required section pattern:\n"
        f"{sections}\n\n"
        "Canonical markdown template:\n"
        "```markdown\n"
        f"{build_document_markdown(title=sample_title, tags=tags, doc_type=doc_type, body=f'# {sample_title}\\n\\nWrite the article body here.')}"
        "```\n"
    )


@dataclass
class DocumentSpec:
    """Specification for knowledge base document format."""

    # Required frontmatter fields
    title: str
    tags: list[str]
    doc_type: str
    created: str  # ISO 8601 format
    auto_generated: bool

    # Optional frontmatter fields
    version: int = 1
    updated: str | None = None
    wikilinks: list[str] | None = None

    # Content requirements
    min_content_length: int = 100
    max_title_length: int = 100
    max_tags: int = 10


class DocumentLinter:
    """Lints knowledge base documents for format compliance."""

    MIN_SECTION_BODY_LENGTH = 24

    def __init__(self, strict: bool = False):
        """Initialize linter.

        Args:
            strict: If True, warnings are treated as errors
        """
        self.strict = strict
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def lint_file(self, file_path: Path) -> bool:
        """Lint a markdown file.

        Args:
            file_path: Path to markdown file

        Returns:
            True if document passes linting (no errors)
        """
        self.errors = []
        self.warnings = []

        if not file_path.exists():
            self.errors.append(f"File not found: {file_path}")
            return False

        content = file_path.read_text(encoding="utf-8")
        return self.lint_content(content, str(file_path))

    def lint_content(self, content: str, source: str = "<string>") -> bool:
        """Lint markdown content.

        Args:
            content: Markdown content with frontmatter
            source: Source identifier for error messages

        Returns:
            True if document passes linting (no errors)
        """
        self.errors = []
        self.warnings = []

        # Check frontmatter exists
        if not content.startswith("---"):
            self.errors.append(f"{source}: Missing frontmatter (must start with '---')")
            return False

        parts = content.split("---", 2)
        if len(parts) < 3:
            self.errors.append(f"{source}: Invalid frontmatter format (must have closing '---')")
            return False

        frontmatter_str = parts[1].strip()
        body = parts[2].strip()

        # Parse frontmatter
        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            self.errors.append(f"{source}: Invalid YAML in frontmatter: {e}")
            return False

        if not isinstance(frontmatter, dict):
            self.errors.append(f"{source}: Frontmatter must be a YAML dictionary")
            return False

        # Validate required fields
        self._validate_frontmatter(frontmatter, source)

        # Validate body content
        self._validate_body(body, frontmatter, source)

        # Validate markdown structure
        self._validate_markdown(body, frontmatter, source)

        return len(self.errors) == 0 and (not self.strict or len(self.warnings) == 0)

    def _validate_frontmatter(self, frontmatter: dict[str, Any], source: str) -> None:
        """Validate frontmatter fields."""
        # Required fields
        required = ["title", "tags", "doc_type", "created", "auto_generated"]
        for field in required:
            if field not in frontmatter:
                self.errors.append(f"{source}: Missing required field '{field}' in frontmatter")

        # Validate title
        if "title" in frontmatter:
            title = frontmatter["title"]
            if not isinstance(title, str):
                self.errors.append(f"{source}: 'title' must be a string")
            elif not title.strip():
                self.errors.append(f"{source}: 'title' cannot be empty")
            elif len(title) > 100:
                self.warnings.append(f"{source}: 'title' is very long ({len(title)} chars)")

        # Validate tags
        if "tags" in frontmatter:
            tags = frontmatter["tags"]
            if not isinstance(tags, list):
                self.errors.append(f"{source}: 'tags' must be a list")
            elif len(tags) == 0:
                self.warnings.append(f"{source}: 'tags' list is empty")
            elif len(tags) > 10:
                self.warnings.append(f"{source}: Too many tags ({len(tags)}), consider reducing")
            else:
                for tag in tags:
                    if not isinstance(tag, str):
                        self.errors.append(f"{source}: All tags must be strings")
                        break

        # Validate doc_type
        if "doc_type" in frontmatter:
            doc_type = frontmatter["doc_type"]
            if not isinstance(doc_type, str):
                self.errors.append(f"{source}: 'doc_type' must be a string")
            elif not doc_type.strip():
                self.errors.append(f"{source}: 'doc_type' cannot be empty")

        # Validate created timestamp
        if "created" in frontmatter:
            created = frontmatter["created"]
            if not isinstance(created, str):
                self.errors.append(f"{source}: 'created' must be a string (ISO 8601 format)")
            else:
                try:
                    datetime.fromisoformat(created.replace("Z", "+00:00"))
                except ValueError:
                    self.errors.append(
                        f"{source}: 'created' must be valid ISO 8601 timestamp, got: {created}"
                    )

        # Validate auto_generated
        if "auto_generated" in frontmatter:
            auto_gen = frontmatter["auto_generated"]
            if not isinstance(auto_gen, bool):
                self.errors.append(f"{source}: 'auto_generated' must be a boolean")

        # Validate optional version
        if "version" in frontmatter:
            version = frontmatter["version"]
            if not isinstance(version, int):
                self.errors.append(f"{source}: 'version' must be an integer")
            elif version < 1:
                self.errors.append(f"{source}: 'version' must be >= 1")

        # Validate optional wikilinks
        if "wikilinks" in frontmatter:
            wikilinks = frontmatter["wikilinks"]
            if not isinstance(wikilinks, list):
                self.errors.append(f"{source}: 'wikilinks' must be a list")
            else:
                for link in wikilinks:
                    if not isinstance(link, str):
                        self.errors.append(f"{source}: All wikilinks must be strings")
                        break

        self._validate_maintained_doc_metadata(frontmatter, source)

    def _validate_maintained_doc_metadata(
        self,
        frontmatter: dict[str, Any],
        source: str,
    ) -> None:
        doc_type = str(frontmatter.get("doc_type", "") or "").strip().lower()
        doc_family = str(frontmatter.get("doc_family", "") or "").strip().lower()
        if doc_type not in {"feature", "testing"} and doc_family not in {"feature", "testing"}:
            return

        task_id = str(frontmatter.get("task_id", "") or "").strip()
        linked_feature = str(frontmatter.get("linked_feature", "") or "").strip()
        feature_id = str(frontmatter.get("feature_id", "") or "").strip()
        if not any((task_id, linked_feature, feature_id)):
            self.errors.append(
                f"{source}: maintained feature/testing docs require task or feature linkage"
            )

        documented_against_commit = str(
            frontmatter.get("documented_against_commit", "") or ""
        ).strip()
        if not documented_against_commit:
            self.errors.append(
                f"{source}: maintained feature/testing docs require 'documented_against_commit'"
            )

        documented_against_ref = str(frontmatter.get("documented_against_ref", "") or "").strip()
        if not documented_against_ref:
            self.errors.append(
                f"{source}: maintained feature/testing docs require 'documented_against_ref'"
            )

        owned_paths = frontmatter.get("owned_paths")
        if not isinstance(owned_paths, list) or not any(str(item).strip() for item in owned_paths):
            self.errors.append(
                f"{source}: maintained feature/testing docs require non-empty 'owned_paths'"
            )

        refresh_required = frontmatter.get("refresh_required")
        if refresh_required is True and not frontmatter.get("updated"):
            self.errors.append(
                f"{source}: refresh_required maintained docs require 'updated'"
            )

        if doc_type == "testing" or doc_family == "testing":
            last_verified_at = str(frontmatter.get("last_verified_at", "") or "").strip()
            if not last_verified_at:
                self.errors.append(
                    f"{source}: testing docs require 'last_verified_at'"
                )

    def _validate_body(self, body: str, frontmatter: dict[str, Any], source: str) -> None:
        """Validate document body content."""
        if not body.strip():
            self.errors.append(f"{source}: Document body is empty")
            return

        min_length = 150 if frontmatter.get("auto_generated") else 100
        if len(body) < min_length:
            self.warnings.append(
                f"{source}: Document body is very short ({len(body)} chars)"
            )

    def _normalize_heading(self, text: str) -> str:
        """Normalize heading text for loose equality checks."""
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    def _section_text(self, lines: list[str]) -> str:
        """Collapse section lines into analyzable text."""
        meaningful = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("<!--")
        ]
        text = "\n".join(meaningful)
        return re.sub(r"[`*_>#-]+", " ", text).strip()

    def _word_count(self, text: str) -> int:
        """Return a rough natural-language word count."""
        return len(re.findall(r"\b[\w'-]+\b", text))

    def _validate_markdown(self, body: str, frontmatter: dict[str, Any], source: str) -> None:
        """Validate markdown structure."""
        if re.search(r"^#{1,6}\s*$", body, re.MULTILINE):
            self.errors.append(f"{source}: Found empty heading marker")

        # Check for at least one heading
        if not re.search(r"^#+\s+.+$", body, re.MULTILINE):
            self.warnings.append(f"{source}: No markdown headings found")
            return

        heading_matches = list(re.finditer(r"^(#+)\s+(.+)$", body, re.MULTILINE))
        headings = [(len(match.group(1)), match.group(2).strip(), match.start()) for match in heading_matches]

        if headings[0][0] != 1:
            self.errors.append(f"{source}: First heading must be an H1")

        h1_titles = [title for level, title, _ in headings if level == 1]
        if len(h1_titles) > 1:
            self.warnings.append(f"{source}: Multiple H1 headings found")

        doc_type = frontmatter.get("doc_type")
        if isinstance(doc_type, str):
            available_h2 = {
                self._normalize_heading(title)
                for level, title, _ in headings
                if level == 2
            }
            missing = [
                section.replace("## ", "")
                for section in default_section_guidance(doc_type)
                if section.startswith("## ")
                and self._normalize_heading(section.replace("## ", "")) not in available_h2
            ]
            if missing:
                self.errors.append(
                    f"{source}: Missing required sections for {doc_type}: {', '.join(missing)}"
                )

        # Check for proper heading hierarchy (no skipping levels)
        levels = [level for level, _, _ in headings]
        for i in range(1, len(levels)):
            if levels[i] > levels[i - 1] + 1:
                self.warnings.append(
                    f"{source}: Heading hierarchy skips levels (h{levels[i-1]} -> h{levels[i]})"
                )
                break

        for index, (level, heading_text, start) in enumerate(headings):
            section_start = start
            section_end = len(body)
            for next_level, _, next_start in headings[index + 1 :]:
                if next_level <= level:
                    section_end = next_start
                    break
            section_block = body[section_start:section_end]
            section_lines = section_block.splitlines()[1:]
            section_text = self._section_text(section_lines)

            if level > 1 and not section_text:
                self.errors.append(
                    f"{source}: Section '{heading_text}' has no body content"
                )
                continue

            if level <= 2 and section_text and len(section_text) < self.MIN_SECTION_BODY_LENGTH:
                self.warnings.append(
                    f"{source}: Section '{heading_text}' is too brief ({len(section_text)} chars)"
                )

            if level == 2 and isinstance(doc_type, str):
                for budget in section_budget_guidance(doc_type):
                    if self._normalize_heading(budget["heading"]) != self._normalize_heading(heading_text):
                        continue
                    words = self._word_count(section_text)
                    min_words = int(budget["min_words"])
                    max_words = int(budget["max_words"])
                    if words < min_words:
                        self.warnings.append(
                            f"{source}: Section '{heading_text}' is under target size ({words} words, expected {min_words}-{max_words})"
                        )
                    elif words > max_words:
                        self.warnings.append(
                            f"{source}: Section '{heading_text}' is over target size ({words} words, expected {min_words}-{max_words})"
                        )
                    break

    def get_report(self) -> str:
        """Get formatted linting report."""
        lines = []

        if self.errors:
            lines.append("ERRORS:")
            for error in self.errors:
                lines.append(f"  [FAIL] {error}")

        if self.warnings:
            if lines:
                lines.append("")
            lines.append("WARNINGS:")
            for warning in self.warnings:
                lines.append(f"  [WARN] {warning}")

        if not self.errors and not self.warnings:
            lines.append("[OK] Document passes all checks")

        return "\n".join(lines)


def lint_directory(
    directory: Path, strict: bool = False, verbose: bool = False
) -> tuple[int, int, int]:
    """Lint all markdown files in a directory.

    Args:
        directory: Directory containing markdown files
        strict: If True, warnings are treated as errors
        verbose: If True, print detailed reports for each file

    Returns:
        Tuple of (passed, failed, total) counts
    """
    if not directory.exists():
        print(f"[FAIL] Directory not found: {directory}")
        return (0, 0, 0)

    linter = DocumentLinter(strict=strict)
    passed = 0
    failed = 0
    total = 0

    for md_file in sorted(directory.glob("*.md")):
        total += 1
        result = linter.lint_file(md_file)

        if result:
            passed += 1
            if verbose:
                print(f"[OK] {md_file.name}")
        else:
            failed += 1
            print(f"\n[FAIL] {md_file.name}")
            print(linter.get_report())
            print()

    return (passed, failed, total)
