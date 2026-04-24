"""Ownership checks for reserved documentation surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class DocOwnershipDecision:
    decision: str
    doc_class: str
    target: str
    surface: str
    reason: str
    owner_path: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload = {
            "decision": self.decision,
            "doc_class": self.doc_class,
            "target": self.target,
            "surface": self.surface,
            "reason": self.reason,
        }
        if self.owner_path:
            payload["owner_path"] = self.owner_path
        return payload


@dataclass(frozen=True)
class ReservedDocRule:
    doc_class: str
    canonical_dir: str
    label: str
    suffix: str | None = None

    def canonical_root(self, repo_root: Path) -> Path:
        return repo_root / "docs" / self.canonical_dir

    def infer_surface(self, target: Path, repo_root: Path) -> str | None:
        canonical_root = self.canonical_root(repo_root)
        stem = target.stem

        if self.suffix and stem.endswith(self.suffix):
            surface = stem[: -len(self.suffix)]
            return surface or None
        if target.parent == canonical_root:
            return stem

        owner_path = canonical_root / f"{stem}.md"
        if owner_path.exists():
            return stem
        return None

    def check(self, target: Path, repo_root: Path) -> DocOwnershipDecision:
        docs_root = repo_root / "docs"
        canonical_root = self.canonical_root(repo_root)
        surface = self.infer_surface(target, repo_root)
        fallback_surface = target.stem

        if target.suffix != ".md":
            return DocOwnershipDecision(
                decision="NOT_APPLICABLE",
                doc_class=self.doc_class,
                target=str(target),
                surface=fallback_surface,
                reason="Target is not a markdown document.",
            )

        try:
            relative = target.relative_to(docs_root)
        except ValueError:
            return DocOwnershipDecision(
                decision="NOT_APPLICABLE",
                doc_class=self.doc_class,
                target=str(target),
                surface=fallback_surface,
                reason="Target is outside docs/.",
            )

        if surface is None:
            return DocOwnershipDecision(
                decision="NOT_APPLICABLE",
                doc_class=self.doc_class,
                target=str(target),
                surface=fallback_surface,
                reason=f"Target does not look like a {self.label} doc.",
            )

        owner_path = canonical_root / f"{surface}.md"

        if relative.parent == Path(self.canonical_dir):
            if target.exists():
                return DocOwnershipDecision(
                    decision="UPDATE_EXISTING",
                    doc_class=self.doc_class,
                    target=str(target),
                    surface=surface,
                    reason=(
                        f"{self.label.capitalize()} docs must be updated in place "
                        f"under docs/{self.canonical_dir}/."
                    ),
                    owner_path=str(target),
                )
            if owner_path.exists() and owner_path != target:
                return DocOwnershipDecision(
                    decision="UPDATE_EXISTING",
                    doc_class=self.doc_class,
                    target=str(target),
                    surface=surface,
                    reason=(
                        f"A {self.label} doc for this surface already exists; "
                        "update the existing doc instead of creating a second one."
                    ),
                    owner_path=str(owner_path),
                )
            return DocOwnershipDecision(
                decision="CREATE_NEW_ALLOWED",
                doc_class=self.doc_class,
                target=str(target),
                surface=surface,
                reason=f"New {self.label} docs are allowed only under docs/{self.canonical_dir}/.",
                owner_path=str(owner_path),
            )

        if owner_path.exists():
            reason = (
                f"{self.label.capitalize()} docs must live under docs/{self.canonical_dir}/; "
                "update the canonical doc there instead of creating another copy."
            )
        else:
            reason = (
                f"{self.label.capitalize()} docs must live under docs/{self.canonical_dir}/ "
                "rather than root docs/."
            )
        return DocOwnershipDecision(
            decision="WRONG_SURFACE",
            doc_class=self.doc_class,
            target=str(target),
            surface=surface,
            reason=reason,
            owner_path=str(owner_path),
        )


RESERVED_DOC_RULES = (
    ReservedDocRule(
        doc_class="quality-gate",
        canonical_dir="quality-gate",
        label="quality-gate",
        suffix="-quality-gate",
    ),
    ReservedDocRule(
        doc_class="workflow",
        canonical_dir="workflows",
        label="workflow",
        suffix="-workflow",
    ),
)


def check_doc_ownership(
    target: Path,
    repo_root: Path | None = None,
    doc_class: str | None = None,
) -> DocOwnershipDecision:
    repo = (repo_root or REPO_ROOT).resolve()
    resolved_target = target.resolve()
    rules = [rule for rule in RESERVED_DOC_RULES if doc_class in {None, rule.doc_class}]
    for rule in rules:
        decision = rule.check(resolved_target, repo)
        if decision.decision != "NOT_APPLICABLE":
            return decision

    return DocOwnershipDecision(
        decision="NOT_APPLICABLE",
        doc_class=doc_class or "unknown",
        target=str(resolved_target),
        surface=resolved_target.stem,
        reason="Target does not match a reserved doc surface.",
    )


def looks_like_reserved_doc_path(target: Path, repo_root: Path | None = None) -> bool:
    return check_doc_ownership(target, repo_root=repo_root).decision != "NOT_APPLICABLE"
