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
        self._validate_body(body, source)

        # Validate markdown structure
        self._validate_markdown(body, source)

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

    def _validate_body(self, body: str, source: str) -> None:
        """Validate document body content."""
        if not body.strip():
            self.errors.append(f"{source}: Document body is empty")
            return

        if len(body) < 100:
            self.warnings.append(
                f"{source}: Document body is very short ({len(body)} chars)"
            )

    def _validate_markdown(self, body: str, source: str) -> None:
        """Validate markdown structure."""
        # Check for at least one heading
        if not re.search(r"^#+\s+.+$", body, re.MULTILINE):
            self.warnings.append(f"{source}: No markdown headings found")

        # Check for proper heading hierarchy (no skipping levels)
        headings = re.findall(r"^(#+)\s+.+$", body, re.MULTILINE)
        if headings:
            levels = [len(h) for h in headings]
            for i in range(1, len(levels)):
                if levels[i] > levels[i - 1] + 1:
                    self.warnings.append(
                        f"{source}: Heading hierarchy skips levels (h{levels[i-1]} -> h{levels[i]})"
                    )
                    break

    def get_report(self) -> str:
        """Get formatted linting report."""
        lines = []

        if self.errors:
            lines.append("ERRORS:")
            for error in self.errors:
                lines.append(f"  ❌ {error}")

        if self.warnings:
            if lines:
                lines.append("")
            lines.append("WARNINGS:")
            for warning in self.warnings:
                lines.append(f"  ⚠️  {warning}")

        if not self.errors and not self.warnings:
            lines.append("✅ Document passes all checks")

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
        print(f"❌ Directory not found: {directory}")
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
                print(f"✅ {md_file.name}")
        else:
            failed += 1
            print(f"\n❌ {md_file.name}")
            print(linter.get_report())
            print()

    return (passed, failed, total)
