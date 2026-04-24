"""Shared proof contract helpers for deterministic KB validation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORE_TARGET_DOCS: tuple[str, ...] = (
    "system-architecture",
    "dependencies",
    "technology-stack",
    "project-overview",
    "code-structure",
)
DEFAULT_BLOCKING_DOCS: tuple[str, ...] = (
    "system-architecture",
    "dependencies",
    "technology-stack",
)
CLAIM_TYPE_EXTRACTED = "extracted_fact"
CLAIM_TYPE_DERIVED = "derived_fact"
CLAIM_TYPE_NARRATIVE = "narrative_inference"
CLAIM_TYPE_UNSUPPORTED = "unsupported"
CLAIM_TYPES: frozenset[str] = frozenset(
    {
        CLAIM_TYPE_EXTRACTED,
        CLAIM_TYPE_DERIVED,
        CLAIM_TYPE_NARRATIVE,
        CLAIM_TYPE_UNSUPPORTED,
    }
)
BLOCKING_CLAIM_TYPES: frozenset[str] = frozenset(
    {CLAIM_TYPE_EXTRACTED, CLAIM_TYPE_DERIVED}
)
REPO_INDEX_RELATIVE_PATH = ".evidence/repo-index.json"


@dataclass(frozen=True)
class Citation:
    path: str
    line_start: int
    line_end: int
    kind: str = "evidence"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "kind": self.kind,
        }

    def inline_ref(self) -> str:
        return f"`{self.path}:{self.line_start}-{self.line_end}`"


@dataclass(frozen=True)
class Claim:
    section: str
    text: str
    citations: tuple[Citation, ...]
    claim_type: str = CLAIM_TYPE_EXTRACTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "text": self.text,
            "claim_type": self.claim_type,
            "citations": [citation.to_dict() for citation in self.citations],
        }


def manifest_relative_path(doc_slug: str) -> str:
    return f".evidence/{doc_slug}.json"


def normalize_doc_slug(slug: str) -> str:
    return slug.strip().lower()


def repo_looks_like_builder_repo(workspace_path: Path) -> bool:
    return (workspace_path / "src" / "autonomous_agent_builder").exists()


def load_evidence_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def compute_dependency_hash(workspace_path: Path, dependencies: list[str]) -> str:
    digest = hashlib.sha256()
    for dependency in sorted(set(dependencies)):
        abs_path = workspace_path / dependency
        digest.update(dependency.encode("utf-8"))
        digest.update(b"\0")
        if abs_path.exists():
            digest.update(_content_hash(abs_path).encode("utf-8"))
        else:
            digest.update(b"missing")
        digest.update(b"\0")
    return digest.hexdigest()


def verify_evidence_manifest(workspace_path: Path, manifest_path: Path) -> dict[str, Any]:
    workspace = workspace_path.resolve()
    manifest = load_evidence_manifest(manifest_path)
    issues: list[str] = []

    claims = manifest.get("claims")
    if not isinstance(claims, list) or not claims:
        issues.append("Manifest must include at least one claim.")
        return {"valid": False, "issues": issues, "dependency_hash": manifest.get("dependency_hash")}

    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        issues.append("Manifest must include dependency paths.")
        return {"valid": False, "issues": issues, "dependency_hash": manifest.get("dependency_hash")}

    for claim in claims:
        text = claim.get("text", "")
        citations = claim.get("citations")
        if not text or not isinstance(citations, list) or not citations:
            issues.append("Every claim must include text and at least one citation.")
            continue
        for citation in citations:
            path = citation.get("path")
            line_start = citation.get("line_start")
            line_end = citation.get("line_end")
            if not isinstance(path, str) or not path.strip():
                issues.append("Citation path must be a non-empty string.")
                continue
            abs_path = workspace / path
            if not abs_path.exists():
                issues.append(f"Missing cited file: {path}")
                continue
            lines = abs_path.read_text(encoding="utf-8").splitlines()
            if not isinstance(line_start, int) or not isinstance(line_end, int):
                issues.append(f"Invalid line numbers for {path}")
                continue
            if line_start < 1 or line_end < line_start or line_end > len(lines):
                issues.append(f"Out-of-range citation {path}:{line_start}-{line_end}")
                continue
            excerpt = "\n".join(lines[line_start - 1 : line_end]).strip()
            if not excerpt:
                issues.append(f"Empty cited span for {path}:{line_start}-{line_end}")

    computed_hash = compute_dependency_hash(workspace, [str(path) for path in dependencies])
    if manifest.get("dependency_hash") != computed_hash:
        issues.append("Dependency hash does not match current dependency contents.")

    return {
        "valid": not issues,
        "issues": issues,
        "dependency_hash": computed_hash,
    }


def write_evidence_manifest(
    *,
    workspace_path: Path,
    collection_path: Path,
    doc_slug: str,
    claims: list[Claim],
    dependencies: list[str],
    unresolved_claims: list[dict[str, Any]] | None = None,
    contradicted_claims: list[dict[str, Any]] | None = None,
    extractor_version: str,
    source_commit: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    manifest_rel_path = manifest_relative_path(doc_slug)
    manifest_path = collection_path / manifest_rel_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    dependency_hash = compute_dependency_hash(workspace_path, dependencies)
    manifest: dict[str, Any] = {
        "doc": doc_slug,
        "source_commit": source_commit,
        "extractor_version": extractor_version,
        "dependency_hash": dependency_hash,
        "dependencies": sorted(set(dependencies)),
        "claims": [claim.to_dict() for claim in claims],
        "unresolved_claims": unresolved_claims or [],
        "contradicted_claims": contradicted_claims or [],
        "claim_types": sorted({claim.claim_type for claim in claims}),
    }
    if extra:
        manifest.update(extra)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_rel_path, dependency_hash, manifest


def build_repo_index(workspace_path: Path, collection_path: Path) -> dict[str, Any]:
    evidence_root = collection_path / ".evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    repo_index_path = collection_path / REPO_INDEX_RELATIVE_PATH

    top_level_entries = sorted(
        path.name
        for path in workspace_path.iterdir()
        if not path.name.startswith(".") and path.name != ".agent-builder"
    )[:50]
    top_level_dirs = sorted(
        path.name
        for path in workspace_path.iterdir()
        if path.is_dir() and not path.name.startswith(".") and path.name != ".agent-builder"
    )[:25]
    manifests = [
        name
        for name in (
            "README.md",
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "tsconfig.json",
            "go.mod",
            "Cargo.toml",
            "pom.xml",
            "build.gradle",
            "Dockerfile",
        )
        if (workspace_path / name).exists()
    ]
    entrypoints = sorted(
        {
            str(path.relative_to(workspace_path)).replace("\\", "/")
            for pattern in (
                "main.py",
                "app.py",
                "server.py",
                "manage.py",
                "index.js",
                "index.ts",
                "src/**/main.py",
                "src/**/app.py",
                "src/**/server.py",
                "src/**/index.js",
                "src/**/index.ts",
            )
            for path in workspace_path.glob(pattern)
            if path.is_file()
        }
    )[:25]
    languages = sorted(_detect_languages(workspace_path))
    package_roots = sorted(
        {
            path.parent.name
            for path in workspace_path.glob("src/*/__init__.py")
            if path.is_file()
        }
    )

    payload = {
        "workspace": str(workspace_path.resolve()),
        "builder_repo": repo_looks_like_builder_repo(workspace_path),
        "core_target_docs": list(CORE_TARGET_DOCS),
        "top_level_entries": top_level_entries,
        "top_level_dirs": top_level_dirs,
        "manifests": manifests,
        "entrypoints": entrypoints,
        "languages": languages,
        "package_roots": package_roots,
    }
    repo_index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def repo_index_path(collection_path: Path) -> Path:
    return collection_path / REPO_INDEX_RELATIVE_PATH


def citation_for_file(workspace_path: Path, relative_path: str, *, kind: str = "evidence") -> Citation:
    abs_path = workspace_path / relative_path
    lines = abs_path.read_text(encoding="utf-8").splitlines()
    line_end = max(1, min(len(lines), 200))
    return Citation(path=relative_path, line_start=1, line_end=line_end, kind=kind)


def citation_for_pattern(
    workspace_path: Path,
    relative_path: str,
    *,
    pattern: str,
    kind: str = "evidence",
) -> Citation:
    abs_path = workspace_path / relative_path
    content = abs_path.read_text(encoding="utf-8")
    match = re.search(pattern, content, flags=re.MULTILINE)
    if not match:
        return citation_for_file(workspace_path, relative_path, kind=kind)
    line_start, line_end = line_range_for_match(content, match.start(), match.end())
    return Citation(path=relative_path, line_start=line_start, line_end=line_end, kind=kind)


def line_range_for_match(content: str, start: int, end: int) -> tuple[int, int]:
    line_start = content.count("\n", 0, start) + 1
    line_end = content.count("\n", 0, end) + 1
    return line_start, max(line_start, line_end)


def git_head(workspace_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def _content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _detect_languages(workspace_path: Path) -> set[str]:
    languages: set[str] = set()
    if (workspace_path / "pyproject.toml").exists() or (workspace_path / "requirements.txt").exists():
        languages.add("python")
    if (workspace_path / "package.json").exists():
        languages.add("node")
    if (workspace_path / "tsconfig.json").exists() or list(workspace_path.glob("**/*.ts")):
        languages.add("typescript")
    if (workspace_path / "go.mod").exists():
        languages.add("go")
    if (workspace_path / "Cargo.toml").exists():
        languages.add("rust")
    return languages
