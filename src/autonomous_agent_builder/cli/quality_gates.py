"""Quality-gate contract loading and ownership checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from autonomous_agent_builder.cli.doc_ownership import DocOwnershipDecision, check_doc_ownership

REPO_ROOT = Path(__file__).resolve().parents[3]
QUALITY_GATE_DIR = REPO_ROOT / "docs" / "quality-gate"
REQUIRED_KEYS = ("title", "surface", "summary", "commands", "expectations")


class QualityGateError(ValueError):
    """Raised when quality-gate docs are missing or malformed."""


@dataclass(frozen=True)
class QualityGateContract:
    surface: str
    title: str
    summary: str
    commands: tuple[str, ...]
    expectations: tuple[str, ...]
    related_docs: tuple[str, ...] = ()
    path: Path | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "surface": self.surface,
            "title": self.title,
            "summary": self.summary,
            "commands": list(self.commands),
            "expectations": list(self.expectations),
        }
        if self.related_docs:
            payload["related_docs"] = list(self.related_docs)
        if self.path is not None:
            payload["path"] = str(self.path)
        return payload


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_QUALITY_GATE_SUFFIX = "-quality-gate"


def _load_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise QualityGateError(f"{path} is missing frontmatter.")
    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise QualityGateError(f"{path} frontmatter must be a mapping.")
    return parsed


def _normalize_string_list(path: Path, value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise QualityGateError(f"{path} frontmatter '{key}' must be a list of strings.")
    return tuple(item.strip() for item in value)


def _contract_from_path(path: Path) -> QualityGateContract:
    frontmatter = _load_frontmatter(path)
    for key in REQUIRED_KEYS:
        if key not in frontmatter:
            raise QualityGateError(f"{path} frontmatter is missing required key '{key}'.")
    title = frontmatter["title"]
    surface = frontmatter["surface"]
    summary = frontmatter["summary"]
    if not isinstance(title, str) or not title.strip():
        raise QualityGateError(f"{path} frontmatter 'title' must be a non-empty string.")
    if not isinstance(surface, str) or not surface.strip():
        raise QualityGateError(f"{path} frontmatter 'surface' must be a non-empty string.")
    if not isinstance(summary, str) or not summary.strip():
        raise QualityGateError(f"{path} frontmatter 'summary' must be a non-empty string.")
    commands = _normalize_string_list(path, frontmatter["commands"], "commands")
    expectations = _normalize_string_list(path, frontmatter["expectations"], "expectations")
    related_docs = ()
    if "related_docs" in frontmatter:
        related_docs = _normalize_string_list(
            path,
            frontmatter.get("related_docs", []),
            "related_docs",
        )
    return QualityGateContract(
        surface=surface.strip(),
        title=title.strip(),
        summary=summary.strip(),
        commands=commands,
        expectations=expectations,
        related_docs=related_docs,
        path=path,
    )


def list_quality_gate_contracts(root: Path | None = None) -> list[QualityGateContract]:
    gate_root = (root or QUALITY_GATE_DIR).resolve()
    if not gate_root.exists():
        raise QualityGateError(f"Quality-gate directory not found: {gate_root}")
    contracts: list[QualityGateContract] = []
    seen_surfaces: dict[str, Path] = {}
    for path in sorted(gate_root.glob("*.md")):
        contract = _contract_from_path(path)
        if contract.surface in seen_surfaces:
            raise QualityGateError(
                f"Duplicate quality-gate surface '{contract.surface}' "
                f"in {seen_surfaces[contract.surface]} and {path}"
            )
        seen_surfaces[contract.surface] = path
        contracts.append(contract)
    return contracts


def get_quality_gate_contract(surface: str, root: Path | None = None) -> QualityGateContract:
    contracts = list_quality_gate_contracts(root=root)
    for contract in contracts:
        if contract.surface == surface:
            return contract
    choices = ", ".join(sorted(contract.surface for contract in contracts))
    raise QualityGateError(f"Unknown quality gate '{surface}'. Choose from: {choices}")


def infer_quality_gate_surface(target: Path, *, quality_gate_root: Path | None = None) -> str:
    gate_root = (quality_gate_root or QUALITY_GATE_DIR).resolve()
    target = target.resolve()
    stem = target.stem
    if stem.endswith(_QUALITY_GATE_SUFFIX):
        stem = stem[: -len(_QUALITY_GATE_SUFFIX)]
    if target.parent == gate_root:
        return stem
    return stem


def looks_like_quality_gate_path(target: Path, *, repo_root: Path | None = None) -> bool:
    repo = (repo_root or REPO_ROOT).resolve()
    docs_root = repo / "docs"
    try:
        relative = target.resolve().relative_to(docs_root)
    except ValueError:
        return False
    if target.suffix != ".md":
        return False
    return relative.parent == Path("quality-gate") or _QUALITY_GATE_SUFFIX in target.stem


def check_quality_gate_ownership(
    target: Path,
    *,
    repo_root: Path | None = None,
) -> DocOwnershipDecision:
    return check_doc_ownership(target, repo_root=repo_root, doc_class="quality-gate")
