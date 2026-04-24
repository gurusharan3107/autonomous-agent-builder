"""Deterministic quality gate for repo-local system-docs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.knowledge.proof_contract import (
    BLOCKING_CLAIM_TYPES,
    CLAIM_TYPES,
    CORE_TARGET_DOCS,
    DEFAULT_BLOCKING_DOCS,
    REPO_INDEX_RELATIVE_PATH,
    compute_dependency_hash,
    load_evidence_manifest,
    repo_looks_like_builder_repo,
    verify_evidence_manifest,
)
from autonomous_agent_builder.knowledge.evidence_graph import (
    GRAPH_ARTIFACT_RELATIVE_PATH,
    load_shared_evidence_graph,
    validate_shared_evidence_graph,
)
from autonomous_agent_builder.knowledge.maintained_freshness import (
    maintained_doc_report,
)

TEMPLATE_LEAKAGE_MARKERS = (
    "dashboard-first autonomous delivery system",
    "builder cli commands",
    "src/autonomous_agent_builder/",
    "react spa operator surface",
)
_INACTIVE_DOC_LIFECYCLES = {"superseded", "quarantined"}


@dataclass
class QualityCheck:
    name: str
    passed: bool
    score: float
    message: str
    details: dict[str, Any] | None = None


@dataclass
class QualityGateResult:
    passed: bool
    score: float
    checks: list[QualityCheck]
    summary: str
    blocking_docs: list[str] = field(default_factory=list)
    non_blocking_docs: list[str] = field(default_factory=list)
    claim_failures: list[dict[str, Any]] = field(default_factory=list)
    unresolved_claims: list[dict[str, Any]] = field(default_factory=list)
    contradicted_claims: list[dict[str, Any]] = field(default_factory=list)
    workspace_profile: str = ""
    graph_artifact: str = ""
    blocking_render_status: dict[str, Any] = field(default_factory=dict)
    unresolved_item_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "summary": self.summary,
            "blocking_docs": self.blocking_docs,
            "non_blocking_docs": self.non_blocking_docs,
            "claim_failures": self.claim_failures,
            "unresolved_claims": self.unresolved_claims,
            "contradicted_claims": self.contradicted_claims,
            "workspace_profile": self.workspace_profile,
            "graph_artifact": self.graph_artifact,
            "blocking_render_status": self.blocking_render_status,
            "unresolved_item_counts": self.unresolved_item_counts,
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
    """Deterministic validation for evidence-native blocking docs."""

    EXPECTED_DOCS = set(CORE_TARGET_DOCS)

    def __init__(self, kb_path: Path, workspace_path: Path):
        self.kb_path = kb_path
        self.workspace_path = workspace_path
        self._builder_repo = repo_looks_like_builder_repo(workspace_path)

    def validate(self) -> QualityGateResult:
        completeness = self._check_completeness()
        graph_validity = self._check_graph_validity()
        claim_validation = self._check_claim_validation()
        citation_validity = self._check_citation_validity()
        freshness = self._check_freshness()
        searchability = self._check_searchability()
        checks = [
            completeness,
            graph_validity,
            claim_validation,
            citation_validity,
            freshness,
            searchability,
        ]

        passed = all(check.passed for check in checks[:5])
        score = sum(check.score for check in checks) / len(checks) if checks else 0.0
        blocking_docs = self._blocking_docs()
        non_blocking_docs = self._non_blocking_docs()
        claim_failures = list((claim_validation.details or {}).get("claim_failures", []))
        unresolved_claims = list((claim_validation.details or {}).get("unresolved_claims", []))
        contradicted_claims = list((claim_validation.details or {}).get("contradicted_claims", []))
        graph_payload = self._graph_payload()
        unresolved_item_counts = {
            doc: sum(
                1
                for item in graph_payload.get("unresolved_items", [])
                if item.get("doc_slug") == doc
            )
            for doc in blocking_docs
        }
        blocking_render_status = self._blocking_render_status()

        if passed:
            summary = (
                "Deterministic KB validation passed for blocking docs: "
                + ", ".join(blocking_docs)
            )
        else:
            summary = (
                "Deterministic KB validation failed for blocking docs: "
                + ", ".join(blocking_docs)
            )
            if claim_failures:
                summary += f" ({len(claim_failures)} claim failure(s))"

        return QualityGateResult(
            passed=passed,
            score=score,
            checks=checks,
            summary=summary,
            blocking_docs=blocking_docs,
            non_blocking_docs=non_blocking_docs,
            claim_failures=claim_failures,
            unresolved_claims=unresolved_claims,
            contradicted_claims=contradicted_claims,
            workspace_profile=str(graph_payload.get("workspace_profile", "")),
            graph_artifact=str(self.kb_path / GRAPH_ARTIFACT_RELATIVE_PATH),
            blocking_render_status=blocking_render_status,
            unresolved_item_counts=unresolved_item_counts,
        )

    def _check_completeness(self) -> QualityCheck:
        blocking_docs = self._blocking_docs()
        missing_docs = [slug for slug in blocking_docs if not (self.kb_path / f"{slug}.md").exists()]
        repo_index_exists = (self.kb_path / REPO_INDEX_RELATIVE_PATH).exists()
        passed = not missing_docs and repo_index_exists
        details = {
            "blocking_docs": blocking_docs,
            "missing": missing_docs,
            "repo_index": str(self.kb_path / REPO_INDEX_RELATIVE_PATH),
            "repo_index_exists": repo_index_exists,
        }
        score = 1.0
        if blocking_docs:
            score -= len(missing_docs) / len(blocking_docs)
        if not repo_index_exists:
            score = min(score, 0.5)
        return QualityCheck(
            name="completeness",
            passed=passed,
            score=max(0.0, score),
            message=(
                "All blocking docs and repo index are present"
                if passed
                else "Missing blocking docs or repo index"
            ),
            details=details,
        )

    def _check_graph_validity(self) -> QualityCheck:
        graph_path = self.kb_path / GRAPH_ARTIFACT_RELATIVE_PATH
        if not graph_path.exists():
            return QualityCheck(
                name="graph_validity",
                passed=False,
                score=0.0,
                message="Shared evidence graph is missing",
                details={"issues": [f"missing {graph_path}"]},
            )
        graph = self._graph_payload()
        issues = validate_shared_evidence_graph(graph)
        render_status = self._blocking_render_status()
        for doc_slug, status in render_status.items():
            if not status.get("rendered_from_graph"):
                issues.append(f"{doc_slug}: blocking doc was not rendered from the shared graph")
        return QualityCheck(
            name="graph_validity",
            passed=not issues,
            score=1.0 if not issues else max(0.0, 1.0 - (len(issues) / 6)),
            message="Shared evidence graph is present and schema-valid"
            if not issues
            else f"{len(issues)} graph issue(s) detected",
            details={
                "issues": issues,
                "workspace_profile": graph.get("workspace_profile", ""),
                "graph_artifact": str(graph_path),
                "blocking_render_status": render_status,
            },
        )

    def _check_claim_validation(self) -> QualityCheck:
        claim_failures: list[dict[str, Any]] = []
        unresolved_claims: list[dict[str, Any]] = []
        contradicted_claims: list[dict[str, Any]] = []

        for doc_slug in self._blocking_docs():
            doc_result = self._validate_blocking_doc(doc_slug)
            claim_failures.extend(doc_result["claim_failures"])
            unresolved_claims.extend(doc_result["unresolved_claims"])
            contradicted_claims.extend(doc_result["contradicted_claims"])

        issues = len(claim_failures) + len(unresolved_claims) + len(contradicted_claims)
        return QualityCheck(
            name="claim_validation",
            passed=issues == 0,
            score=1.0 if issues == 0 else max(0.0, 1.0 - (issues / max(1, len(self._blocking_docs()) * 4))),
            message=(
                "All blocking claims are typed, cited, and contradiction-free"
                if issues == 0
                else f"{issues} blocking-claim issue(s) detected"
            ),
            details={
                "claim_failures": claim_failures,
                "unresolved_claims": unresolved_claims,
                "contradicted_claims": contradicted_claims,
            },
        )

    def _check_citation_validity(self) -> QualityCheck:
        issues: list[str] = []
        documents: list[str] = []
        for doc_slug in self._blocking_docs():
            doc_path = self.kb_path / f"{doc_slug}.md"
            if not doc_path.exists():
                continue
            frontmatter = self._extract_frontmatter(doc_path.read_text(encoding="utf-8"))
            manifest_ref = frontmatter.get("evidence_manifest")
            if not isinstance(manifest_ref, str) or not manifest_ref.strip():
                issues.append(f"{doc_slug}: missing evidence manifest reference")
                continue
            manifest_path = self._resolve_manifest_path(manifest_ref)
            if not manifest_path.exists():
                issues.append(f"{doc_slug}: missing evidence manifest {manifest_ref}")
                continue
            documents.append(doc_slug)
            verification = verify_evidence_manifest(self.workspace_path, manifest_path)
            if not verification["valid"]:
                issues.extend(f"{doc_slug}: {issue}" for issue in verification["issues"][:10])

        return QualityCheck(
            name="citation_validity",
            passed=not issues,
            score=1.0 if not issues else max(0.0, 1.0 - (len(issues) / max(1, len(documents) * 4))),
            message=(
                "All blocking manifests resolve to live citations"
                if not issues
                else f"{len(issues)} citation issue(s) detected"
            ),
            details={"issues": issues, "documents": documents},
        )

    def _check_freshness(self) -> QualityCheck:
        issues: list[str] = []
        documents: list[str] = []
        warnings: list[str] = []
        maintained_docs: list[dict[str, Any]] = []
        for doc_slug in self._blocking_docs():
            doc_path = self.kb_path / f"{doc_slug}.md"
            if not doc_path.exists():
                continue
            frontmatter = self._extract_frontmatter(doc_path.read_text(encoding="utf-8"))
            manifest_ref = frontmatter.get("evidence_manifest")
            if not isinstance(manifest_ref, str) or not manifest_ref.strip():
                continue
            manifest_path = self._resolve_manifest_path(manifest_ref)
            if not manifest_path.exists():
                continue
            documents.append(doc_slug)
            manifest = load_evidence_manifest(manifest_path)
            dependencies = manifest.get("dependencies") or []
            if not isinstance(dependencies, list):
                issues.append(f"{doc_slug}: dependencies must be a list")
                continue
            dependency_hash = compute_dependency_hash(self.workspace_path, [str(path) for path in dependencies])
            if manifest.get("dependency_hash") != dependency_hash:
                issues.append(f"{doc_slug}: dependency hash mismatch")
                continue
            if frontmatter.get("dependency_hash") != dependency_hash:
                issues.append(f"{doc_slug}: document frontmatter dependency hash mismatch")

        for doc_path in sorted(self.kb_path.glob("*.md")):
            if doc_path.stem == "extraction-metadata":
                continue
            content = doc_path.read_text(encoding="utf-8")
            frontmatter = self._extract_frontmatter(content)
            doc_type = str(frontmatter.get("doc_type", "") or "")
            family = str(frontmatter.get("doc_family", "") or "")
            lifecycle_status = str(frontmatter.get("lifecycle_status", "") or "").strip().lower()
            if doc_type not in {"feature", "testing"} and family not in {"feature", "testing"}:
                continue
            if lifecycle_status in _INACTIVE_DOC_LIFECYCLES:
                continue
            documents.append(doc_path.stem)
            if frontmatter.get("refresh_required") is True and not frontmatter.get("updated"):
                issues.append(f"{doc_path.stem}: refresh_required system doc is missing updated timestamp")
            if (doc_type == "testing" or family == "testing") and not frontmatter.get("last_verified_at"):
                issues.append(f"{doc_path.stem}: testing doc is missing last_verified_at")
            if not frontmatter.get("linked_feature") and not frontmatter.get("feature_id") and not frontmatter.get("task_id"):
                issues.append(f"{doc_path.stem}: maintained system doc is missing feature or task linkage")
            report = maintained_doc_report(
                workspace_path=self.workspace_path,
                doc_id=doc_path.stem,
                doc_type=doc_type or family,
                lifecycle_status=lifecycle_status or "active",
                metadata=frontmatter,
                created=str(frontmatter.get("created", "") or ""),
                updated=str(frontmatter.get("updated", "") or ""),
            )
            maintained_docs.append(report.to_dict())
            if report.blocking:
                issues.append(f"{doc_path.stem}: {report.stale_reason}")
            elif report.status != "current":
                warnings.append(f"{doc_path.stem}: {report.stale_reason}")

        return QualityCheck(
            name="freshness",
            passed=not issues,
            score=1.0 if not issues else max(0.0, 1.0 - (len(issues) / max(1, len(documents) * 2))),
            message=(
                "All blocking docs are fresh against cited dependencies"
                if not issues and not warnings
                else (
                    f"Blocking freshness checks passed; {len(warnings)} migration warning(s) remain"
                    if not issues and warnings
                    else f"{len(issues)} freshness issue(s) detected"
                )
            ),
            details={
                "issues": issues,
                "warnings": warnings,
                "documents": documents,
                "maintained_docs": maintained_docs,
            },
        )

    def _check_searchability(self) -> QualityCheck:
        doc_files = [path for path in self.kb_path.glob("*.md") if path.stem != "extraction-metadata"]
        if not doc_files:
            return QualityCheck(
                name="searchability",
                passed=False,
                score=0.0,
                message="No documents found for tag validation",
                details={"avg_tags": 0.0},
            )
        tag_counts: list[int] = []
        for doc_file in doc_files:
            frontmatter = self._extract_frontmatter(doc_file.read_text(encoding="utf-8"))
            tags = frontmatter.get("tags") or []
            if isinstance(tags, list):
                tag_counts.append(len(tags))
        avg_tags = sum(tag_counts) / len(tag_counts) if tag_counts else 0.0
        return QualityCheck(
            name="searchability",
            passed=avg_tags >= 2.0,
            score=1.0 if avg_tags >= 2.0 else avg_tags / 2.0,
            message="Documents have usable tag coverage" if avg_tags >= 2.0 else "Documents need better tag coverage",
            details={"avg_tags": avg_tags},
        )

    def _validate_blocking_doc(self, doc_slug: str) -> dict[str, list[dict[str, Any]]]:
        claim_failures: list[dict[str, Any]] = []
        unresolved_claims: list[dict[str, Any]] = []
        contradicted_claims: list[dict[str, Any]] = []
        doc_path = self.kb_path / f"{doc_slug}.md"
        if not doc_path.exists():
            claim_failures.append(
                {
                    "doc": doc_slug,
                    "section": "Document",
                    "claim": "Blocking document must exist.",
                    "reason": "missing_document",
                    "citations": [],
                }
            )
            return {
                "claim_failures": claim_failures,
                "unresolved_claims": unresolved_claims,
                "contradicted_claims": contradicted_claims,
            }

        content = doc_path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)
        manifest_ref = frontmatter.get("evidence_manifest")
        if frontmatter.get("authoritative") is not True:
            claim_failures.append(
                {
                    "doc": doc_slug,
                    "section": "Frontmatter",
                    "claim": "Blocking documents must declare authoritative: true.",
                    "reason": "non_authoritative_blocking_doc",
                    "citations": [],
                }
            )
        if frontmatter.get("verified") is not True:
            claim_failures.append(
                {
                    "doc": doc_slug,
                    "section": "Frontmatter",
                    "claim": "Blocking documents must declare verified: true.",
                    "reason": "unverified_blocking_doc",
                    "citations": [],
                }
            )
        if not isinstance(manifest_ref, str) or not manifest_ref.strip():
            claim_failures.append(
                {
                    "doc": doc_slug,
                    "section": "Frontmatter",
                    "claim": "Blocking documents must reference an evidence manifest.",
                    "reason": "missing_evidence_manifest",
                    "citations": [],
                }
            )
            return {
                "claim_failures": claim_failures,
                "unresolved_claims": unresolved_claims,
                "contradicted_claims": contradicted_claims,
            }

        manifest_path = self._resolve_manifest_path(manifest_ref)
        if not manifest_path.exists():
            claim_failures.append(
                {
                    "doc": doc_slug,
                    "section": "Frontmatter",
                    "claim": f"Evidence manifest `{manifest_ref}` must exist.",
                    "reason": "missing_manifest_file",
                    "citations": [],
                }
            )
            return {
                "claim_failures": claim_failures,
                "unresolved_claims": unresolved_claims,
                "contradicted_claims": contradicted_claims,
            }

        manifest = load_evidence_manifest(manifest_path)
        self._validate_manifest_contract(doc_slug, manifest, claim_failures)
        doc_body = self._extract_body(content).lower()
        if not self._builder_repo:
            for marker in TEMPLATE_LEAKAGE_MARKERS:
                if marker in doc_body:
                    claim_failures.append(
                        {
                            "doc": doc_slug,
                            "section": "Document",
                            "claim": f"Blocking doc leaked builder-template marker `{marker}`.",
                            "reason": "template_leakage",
                            "citations": [],
                        }
                    )

        for unresolved in manifest.get("unresolved_claims") or []:
            unresolved_claims.append(self._normalize_manifest_issue(doc_slug, unresolved, reason="unresolved_claim"))
        for contradicted in manifest.get("contradicted_claims") or []:
            contradicted_claims.append(self._normalize_manifest_issue(doc_slug, contradicted, reason="contradicted_claim"))

        for claim in manifest.get("claims") or []:
            citations = claim.get("citations") or []
            claim_type = claim.get("claim_type")
            if claim_type not in CLAIM_TYPES:
                claim_failures.append(
                    {
                        "doc": doc_slug,
                        "section": claim.get("section", "Unknown"),
                        "claim": claim.get("text", ""),
                        "reason": "invalid_claim_type",
                        "citations": citations,
                    }
                )
            elif claim_type not in BLOCKING_CLAIM_TYPES:
                claim_failures.append(
                    {
                        "doc": doc_slug,
                        "section": claim.get("section", "Unknown"),
                        "claim": claim.get("text", ""),
                        "reason": "disallowed_blocking_claim_type",
                        "citations": citations,
                    }
                )
            if not citations:
                claim_failures.append(
                    {
                        "doc": doc_slug,
                        "section": claim.get("section", "Unknown"),
                        "claim": claim.get("text", ""),
                        "reason": "missing_citations",
                        "citations": [],
                    }
                )
            if not str(claim.get("text", "")).strip():
                claim_failures.append(
                    {
                        "doc": doc_slug,
                        "section": claim.get("section", "Unknown"),
                        "claim": claim.get("text", ""),
                        "reason": "empty_claim_text",
                        "citations": citations,
                    }
                )
            claim_text = str(claim.get("text", ""))
            if any(
                marker.lower() in claim_text.lower()
                for marker in ("placeholder", "add concrete evidence", "no deterministic evidence was available")
            ):
                claim_failures.append(
                    {
                        "doc": doc_slug,
                        "section": claim.get("section", "Unknown"),
                        "claim": claim_text,
                        "reason": "placeholder_claim_text",
                        "citations": citations,
                    }
                )

        return {
            "claim_failures": claim_failures,
            "unresolved_claims": unresolved_claims,
            "contradicted_claims": contradicted_claims,
        }

    def _validate_manifest_contract(
        self,
        doc_slug: str,
        manifest: dict[str, Any],
        claim_failures: list[dict[str, Any]],
    ) -> None:
        required_fields = (
            "doc",
            "claims",
            "dependencies",
            "dependency_hash",
            "unresolved_claims",
            "contradicted_claims",
            "claim_types",
            "graph_artifact",
            "workspace_profile",
            "render_status",
        )
        for field in required_fields:
            if field not in manifest:
                claim_failures.append(
                    {
                        "doc": doc_slug,
                        "section": "Manifest",
                        "claim": f"Manifest must include `{field}`.",
                        "reason": "missing_manifest_field",
                        "citations": [],
                    }
                )
        if manifest.get("doc") != doc_slug:
            claim_failures.append(
                {
                    "doc": doc_slug,
                    "section": "Manifest",
                    "claim": "Manifest doc slug must match the document.",
                    "reason": "manifest_doc_mismatch",
                    "citations": [],
                }
            )
        claim_types = manifest.get("claim_types") or []
        if not isinstance(claim_types, list) or not claim_types:
            claim_failures.append(
                {
                    "doc": doc_slug,
                    "section": "Manifest",
                    "claim": "Manifest must include claim_types.",
                    "reason": "missing_claim_types",
                    "citations": [],
                }
            )
        render_status = manifest.get("render_status") or {}
        if not isinstance(render_status, dict) or not render_status.get("rendered_from_graph"):
            claim_failures.append(
                {
                    "doc": doc_slug,
                    "section": "Manifest",
                    "claim": "Blocking docs must be rendered from the shared evidence graph.",
                    "reason": "blocking_doc_not_graph_backed",
                    "citations": [],
                }
            )

    def _normalize_manifest_issue(
        self,
        doc_slug: str,
        issue: dict[str, Any] | str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        if isinstance(issue, dict):
            normalized = dict(issue)
        else:
            normalized = {"claim": str(issue)}
        normalized.setdefault("doc", doc_slug)
        normalized.setdefault("section", normalized.get("section", "Manifest"))
        normalized.setdefault("reason", reason)
        normalized.setdefault("citations", normalized.get("citations", []))
        return normalized

    def _extract_body(self, content: str) -> str:
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content

    def _extract_frontmatter(self, content: str) -> dict[str, Any]:
        if not content.startswith("---"):
            return {}
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}
        try:
            parsed = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _expected_docs(self) -> set[str]:
        metadata = self._metadata_frontmatter()
        expected = metadata.get("expected_documents")
        if isinstance(expected, list):
            return {str(item).strip() for item in expected if str(item).strip()}
        return set(CORE_TARGET_DOCS)

    def _blocking_docs(self) -> list[str]:
        metadata = self._metadata_frontmatter()
        configured = metadata.get("blocking_documents")
        if isinstance(configured, list) and configured:
            return [str(item).strip() for item in configured if str(item).strip()]
        settings_docs = get_settings().kb_blocking_docs or list(DEFAULT_BLOCKING_DOCS)
        generated = self._generated_docs()
        return [doc for doc in settings_docs if doc in generated or doc in self._expected_docs()]

    def _non_blocking_docs(self) -> list[str]:
        metadata = self._metadata_frontmatter()
        configured = metadata.get("non_blocking_documents")
        if isinstance(configured, list):
            return [str(item).strip() for item in configured if str(item).strip()]
        expected = self._expected_docs()
        blocking = set(self._blocking_docs())
        return [doc for doc in CORE_TARGET_DOCS if doc in expected and doc not in blocking]

    def _generated_docs(self) -> set[str]:
        return {path.stem for path in self.kb_path.glob("*.md") if path.stem != "extraction-metadata"}

    def _metadata_frontmatter(self) -> dict[str, Any]:
        metadata_file = self.kb_path / "extraction-metadata.md"
        if not metadata_file.exists():
            return {}
        return self._extract_frontmatter(metadata_file.read_text(encoding="utf-8"))

    def _resolve_manifest_path(self, manifest_ref: str) -> Path:
        return (self.kb_path / manifest_ref).resolve()

    def _graph_payload(self) -> dict[str, Any]:
        graph_path = self.kb_path / GRAPH_ARTIFACT_RELATIVE_PATH
        if not graph_path.exists():
            return {}
        try:
            return load_shared_evidence_graph(self.kb_path)
        except Exception:
            return {}

    def _blocking_render_status(self) -> dict[str, Any]:
        statuses: dict[str, Any] = {}
        for doc_slug in self._blocking_docs():
            doc_path = self.kb_path / f"{doc_slug}.md"
            if not doc_path.exists():
                statuses[doc_slug] = {"rendered_from_graph": False}
                continue
            frontmatter = self._extract_frontmatter(doc_path.read_text(encoding="utf-8"))
            manifest_ref = frontmatter.get("evidence_manifest")
            if not isinstance(manifest_ref, str) or not manifest_ref.strip():
                statuses[doc_slug] = {"rendered_from_graph": False}
                continue
            manifest_path = self._resolve_manifest_path(manifest_ref)
            if not manifest_path.exists():
                statuses[doc_slug] = {"rendered_from_graph": False}
                continue
            manifest = load_evidence_manifest(manifest_path)
            status = manifest.get("render_status") or {}
            statuses[doc_slug] = status if isinstance(status, dict) else {"rendered_from_graph": False}
        return statuses
