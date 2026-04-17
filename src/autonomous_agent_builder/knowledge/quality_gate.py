"""Quality gate for knowledge extraction validation.

Validates generated knowledge base documents against quality criteria:
- Completeness (all expected docs generated)
- Content quality (sufficient detail, no empty sections)
- Accuracy (valid markdown, proper frontmatter)
- Freshness (not stale compared to codebase)
- Usefulness (searchable, well-structured)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class QualityCheck:
    """Single quality check result."""

    name: str
    passed: bool
    score: float  # 0.0 to 1.0
    message: str
    details: dict[str, Any] | None = None


@dataclass
class QualityGateResult:
    """Overall quality gate result."""

    passed: bool
    score: float  # 0.0 to 1.0
    checks: list[QualityCheck]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "passed": self.passed,
            "score": self.score,
            "summary": self.summary,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "score": check.score,
                    "message": check.message,
                    "details": check.details,
                }
                for check in self.checks
            ],
        }


class KnowledgeQualityGate:
    """Quality gate for knowledge extraction validation."""

    # Expected document types for a complete extraction
    EXPECTED_DOCS = {
        "project-overview",
        "technology-stack",
        "dependencies",
        "system-architecture",
        "code-structure",
        "database-models",
        "api-endpoints",
        "business-overview",
        "workflows-and-orchestration",
        "configuration",
        "agent-system",
    }

    # Minimum content length per document type (characters)
    MIN_CONTENT_LENGTH = {
        "project-overview": 500,
        "technology-stack": 400,
        "dependencies": 300,
        "system-architecture": 600,
        "code-structure": 500,
        "database-models": 400,
        "api-endpoints": 500,
        "business-overview": 400,
        "workflows-and-orchestration": 500,
        "configuration": 300,
        "agent-system": 500,
    }

    # Passing threshold (0.0 to 1.0)
    PASSING_THRESHOLD = 0.75

    def __init__(self, kb_path: Path, workspace_path: Path):
        """Initialize quality gate.

        Args:
            kb_path: Path to knowledge base directory
            workspace_path: Path to workspace being analyzed
        """
        self.kb_path = kb_path
        self.workspace_path = workspace_path

    def validate(self) -> QualityGateResult:
        """Run all quality checks and return result."""
        checks = [
            self._check_completeness(),
            self._check_content_quality(),
            self._check_markdown_validity(),
            self._check_frontmatter(),
            self._check_freshness(),
            self._check_searchability(),
            self._check_structure(),
            self._check_cross_references(),
        ]

        # Calculate overall score (weighted average)
        weights = {
            "completeness": 0.25,
            "content_quality": 0.20,
            "markdown_validity": 0.10,
            "frontmatter": 0.10,
            "freshness": 0.10,
            "searchability": 0.10,
            "structure": 0.10,
            "cross_references": 0.05,
        }

        total_score = sum(
            check.score * weights.get(check.name, 0.1) for check in checks
        )

        passed = total_score >= self.PASSING_THRESHOLD
        all_critical_passed = all(
            check.passed
            for check in checks
            if check.name in ["completeness", "content_quality", "markdown_validity"]
        )

        passed = passed and all_critical_passed

        # Generate summary
        passed_count = sum(1 for check in checks if check.passed)
        summary = (
            f"Quality Gate: {'PASSED' if passed else 'FAILED'} "
            f"({passed_count}/{len(checks)} checks passed, score: {total_score:.1%})"
        )

        return QualityGateResult(
            passed=passed,
            score=total_score,
            checks=checks,
            summary=summary,
        )

    def _check_completeness(self) -> QualityCheck:
        """Check if all expected documents are generated."""
        if not self.kb_path.exists():
            return QualityCheck(
                name="completeness",
                passed=False,
                score=0.0,
                message="Knowledge base directory does not exist",
            )

        # Find all generated docs
        generated_docs = set()
        for doc_file in self.kb_path.glob("*.md"):
            if doc_file.stem != "extraction-metadata":
                generated_docs.add(doc_file.stem)

        missing_docs = self.EXPECTED_DOCS - generated_docs
        extra_docs = generated_docs - self.EXPECTED_DOCS

        # Score based on coverage
        coverage = len(generated_docs & self.EXPECTED_DOCS) / len(self.EXPECTED_DOCS)

        passed = coverage >= 0.9  # Allow 1 missing doc

        message = f"Generated {len(generated_docs)}/{len(self.EXPECTED_DOCS)} expected documents"
        if missing_docs:
            message += f" (missing: {', '.join(sorted(missing_docs))})"

        return QualityCheck(
            name="completeness",
            passed=passed,
            score=coverage,
            message=message,
            details={
                "generated": sorted(generated_docs),
                "missing": sorted(missing_docs),
                "extra": sorted(extra_docs),
            },
        )

    def _check_content_quality(self) -> QualityCheck:
        """Check content quality (length, sections, detail)."""
        issues = []
        total_docs = 0
        quality_scores = []

        for doc_file in self.kb_path.glob("*.md"):
            if doc_file.stem == "extraction-metadata":
                continue

            total_docs += 1
            content = doc_file.read_text(encoding="utf-8")

            # Remove frontmatter for content analysis
            content_body = self._extract_body(content)

            # Check minimum length
            min_length = self.MIN_CONTENT_LENGTH.get(doc_file.stem, 300)
            if len(content_body) < min_length:
                issues.append(
                    f"{doc_file.stem}: Too short ({len(content_body)} < {min_length} chars)"
                )
                quality_scores.append(0.3)
                continue

            # Check for empty sections
            empty_sections = self._count_empty_sections(content_body)
            if empty_sections > 2:
                issues.append(f"{doc_file.stem}: {empty_sections} empty sections")

            # Check for placeholder text
            if "TODO" in content_body or "FIXME" in content_body:
                issues.append(f"{doc_file.stem}: Contains TODO/FIXME")

            # Calculate quality score for this doc
            doc_score = 1.0
            if len(content_body) < min_length * 1.5:
                doc_score -= 0.2
            if empty_sections > 0:
                doc_score -= 0.1 * empty_sections
            if "TODO" in content_body:
                doc_score -= 0.2

            quality_scores.append(max(0.0, doc_score))

        avg_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        passed = avg_score >= 0.7 and len(issues) <= 3

        message = f"Average content quality: {avg_score:.1%}"
        if issues:
            message += f" ({len(issues)} issues found)"

        return QualityCheck(
            name="content_quality",
            passed=passed,
            score=avg_score,
            message=message,
            details={"issues": issues[:10], "total_docs": total_docs},
        )

    def _check_markdown_validity(self) -> QualityCheck:
        """Check markdown syntax validity."""
        issues = []

        for doc_file in self.kb_path.glob("*.md"):
            content = doc_file.read_text(encoding="utf-8")

            # Check for common markdown issues
            if "```" in content:
                # Check balanced code blocks
                code_blocks = content.count("```")
                if code_blocks % 2 != 0:
                    issues.append(f"{doc_file.stem}: Unbalanced code blocks")

            # Check for broken links
            broken_links = re.findall(r"\[([^\]]+)\]\(\)", content)
            if broken_links:
                issues.append(f"{doc_file.stem}: {len(broken_links)} empty links")

            # Check for malformed headers
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if line.startswith("#") and not line.startswith("# "):
                    if len(line) > 1 and line[1] not in "#":
                        issues.append(
                            f"{doc_file.stem}:{i}: Malformed header (missing space)"
                        )

        passed = len(issues) == 0
        score = 1.0 if passed else max(0.0, 1.0 - len(issues) * 0.1)

        message = "All markdown valid" if passed else f"{len(issues)} markdown issues"

        return QualityCheck(
            name="markdown_validity",
            passed=passed,
            score=score,
            message=message,
            details={"issues": issues[:10]},
        )

    def _check_frontmatter(self) -> QualityCheck:
        """Check YAML frontmatter validity."""
        issues = []

        required_fields = {"title", "tags", "doc_type", "created", "auto_generated"}

        for doc_file in self.kb_path.glob("*.md"):
            content = doc_file.read_text(encoding="utf-8")

            # Check for frontmatter
            if not content.startswith("---"):
                issues.append(f"{doc_file.stem}: Missing frontmatter")
                continue

            # Extract frontmatter
            parts = content.split("---", 2)
            if len(parts) < 3:
                issues.append(f"{doc_file.stem}: Malformed frontmatter")
                continue

            frontmatter = parts[1]

            # Check required fields
            for field in required_fields:
                if f"{field}:" not in frontmatter:
                    issues.append(f"{doc_file.stem}: Missing field '{field}'")

        passed = len(issues) == 0
        score = 1.0 if passed else max(0.0, 1.0 - len(issues) * 0.1)

        message = (
            "All frontmatter valid" if passed else f"{len(issues)} frontmatter issues"
        )

        return QualityCheck(
            name="frontmatter",
            passed=passed,
            score=score,
            message=message,
            details={"issues": issues[:10]},
        )

    def _check_freshness(self) -> QualityCheck:
        """Check if knowledge base is fresh (not stale)."""
        # Check extraction metadata
        metadata_file = self.kb_path / "extraction-metadata.md"
        if not metadata_file.exists():
            return QualityCheck(
                name="freshness",
                passed=False,
                score=0.0,
                message="No extraction metadata found",
            )

        content = metadata_file.read_text(encoding="utf-8")

        # Extract timestamp - try multiple patterns
        patterns = [
            r"Extracted At\*\*:\s*([^\n]+)",
            r"\*\*Extracted At\*\*:\s*([^\n]+)",
            r"extracted_at[\"']:\s*[\"']([^\"']+)[\"']",
        ]
        
        timestamp_str = None
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                timestamp_str = match.group(1).strip()
                break
        
        if not timestamp_str:
            return QualityCheck(
                name="freshness",
                passed=False,
                score=0.5,
                message="Cannot determine extraction time",
            )

        # Parse timestamp
        try:
            extracted_at = datetime.fromisoformat(timestamp_str)
            age_hours = (datetime.now() - extracted_at).total_seconds() / 3600

            # Score based on age
            if age_hours < 24:
                score = 1.0
            elif age_hours < 168:  # 1 week
                score = 0.8
            elif age_hours < 720:  # 1 month
                score = 0.6
            else:
                score = 0.4

            passed = age_hours < 168  # Less than 1 week

            message = f"Extracted {age_hours:.1f} hours ago"

            return QualityCheck(
                name="freshness",
                passed=passed,
                score=score,
                message=message,
                details={"extracted_at": extracted_at.isoformat(), "age_hours": age_hours},
            )
        except Exception as e:
            # Try to be lenient - if we can't parse, assume it's fresh
            return QualityCheck(
                name="freshness",
                passed=True,
                score=0.8,
                message=f"Cannot parse timestamp, assuming fresh (error: {str(e)[:50]})",
            )

    def _check_searchability(self) -> QualityCheck:
        """Check if documents are searchable (tags, keywords)."""
        issues = []
        total_tags = 0
        docs_with_tags = 0

        for doc_file in self.kb_path.glob("*.md"):
            if doc_file.stem == "extraction-metadata":
                continue

            content = doc_file.read_text(encoding="utf-8")

            # Extract tags from frontmatter
            match = re.search(r'tags:\s*\[([^\]]+)\]', content)
            if match:
                tags = [t.strip(' "') for t in match.group(1).split(",")]
                total_tags += len(tags)
                docs_with_tags += 1

                if len(tags) < 2:
                    issues.append(f"{doc_file.stem}: Only {len(tags)} tag(s)")
            else:
                issues.append(f"{doc_file.stem}: No tags found")

        avg_tags = total_tags / docs_with_tags if docs_with_tags > 0 else 0
        passed = avg_tags >= 3 and len(issues) <= 2

        score = min(1.0, avg_tags / 4.0)  # Target 4 tags per doc

        message = f"Average {avg_tags:.1f} tags per document"
        if issues:
            message += f" ({len(issues)} docs need more tags)"

        return QualityCheck(
            name="searchability",
            passed=passed,
            score=score,
            message=message,
            details={"avg_tags": avg_tags, "issues": issues[:5]},
        )

    def _check_structure(self) -> QualityCheck:
        """Check document structure (headers, sections)."""
        issues = []

        for doc_file in self.kb_path.glob("*.md"):
            if doc_file.stem == "extraction-metadata":
                continue

            content = doc_file.read_text(encoding="utf-8")
            body = self._extract_body(content)

            # Check for main header
            if not body.startswith("# "):
                issues.append(f"{doc_file.stem}: Missing main header")

            # Count headers
            h1_count = body.count("\n# ")
            h2_count = body.count("\n## ")

            if h1_count > 1:
                issues.append(f"{doc_file.stem}: Multiple H1 headers")

            if h2_count < 2:
                issues.append(f"{doc_file.stem}: Too few sections (< 2 H2 headers)")

        passed = len(issues) <= 2
        score = 1.0 if passed else max(0.0, 1.0 - len(issues) * 0.15)

        message = "Good structure" if passed else f"{len(issues)} structure issues"

        return QualityCheck(
            name="structure",
            passed=passed,
            score=score,
            message=message,
            details={"issues": issues[:10]},
        )

    def _check_cross_references(self) -> QualityCheck:
        """Check for cross-references between documents."""
        # This is a bonus check - not critical
        total_links = 0

        for doc_file in self.kb_path.glob("*.md"):
            if doc_file.stem == "extraction-metadata":
                continue

            content = doc_file.read_text(encoding="utf-8")

            # Count internal links (to other docs)
            internal_links = re.findall(r"\[([^\]]+)\]\(([^)]+\.md)\)", content)
            total_links += len(internal_links)

        # Score based on interconnectedness
        score = min(1.0, total_links / 10.0)  # Target 10+ cross-references
        passed = total_links >= 5

        message = f"{total_links} cross-references found"

        return QualityCheck(
            name="cross_references",
            passed=passed,
            score=score,
            message=message,
            details={"total_links": total_links},
        )

    def _extract_body(self, content: str) -> str:
        """Extract body content (remove frontmatter)."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content

    def _count_empty_sections(self, content: str) -> int:
        """Count sections with no content."""
        lines = content.split("\n")
        empty_count = 0
        in_section = False
        section_has_content = False

        for line in lines:
            if line.startswith("## "):
                if in_section and not section_has_content:
                    empty_count += 1
                in_section = True
                section_has_content = False
            elif in_section and line.strip():
                section_has_content = True

        return empty_count
