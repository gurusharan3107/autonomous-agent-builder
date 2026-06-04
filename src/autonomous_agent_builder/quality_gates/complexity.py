"""Baseline-aware Python complexity and god-file guardrail."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASELINE_PATH = REPO_ROOT / "docs" / "quality-gate" / "complexity-baseline.json"

_IGNORED_DIRS = {
    ".agent-builder",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
_BRANCH_NODES = (
    ast.AsyncFor,
    ast.AsyncWith,
    ast.BoolOp,
    ast.ExceptHandler,
    ast.For,
    ast.If,
    ast.IfExp,
    ast.Match,
    ast.Try,
    ast.While,
    ast.With,
    ast.comprehension,
)
_FUNCTION_NODES = (ast.AsyncFunctionDef, ast.FunctionDef)


@dataclass(frozen=True)
class ComplexityThresholds:
    """Thresholds for the ratcheting complexity guard."""

    max_file_lines: int = 500
    max_function_lines: int = 250
    max_function_branches: int = 50

    def to_payload(self) -> dict[str, int]:
        return {
            "max_file_lines": self.max_file_lines,
            "max_function_lines": self.max_function_lines,
            "max_function_branches": self.max_function_branches,
        }


@dataclass(frozen=True)
class FunctionComplexity:
    path: str
    qualname: str
    line_start: int
    line_end: int
    lines: int
    branches: int

    @property
    def baseline_key(self) -> str:
        return f"{self.path}::{self.qualname}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "qualname": self.qualname,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "lines": self.lines,
            "branches": self.branches,
            "baseline_key": self.baseline_key,
        }


@dataclass(frozen=True)
class FileComplexity:
    path: str
    lines: int
    functions: tuple[FunctionComplexity, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "lines": self.lines,
            "function_count": len(self.functions),
        }


class _FunctionCollector(ast.NodeVisitor):
    def __init__(self, path: str):
        self.path = path
        self.stack: list[str] = []
        self.functions: list[FunctionComplexity] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast visitor API.
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast visitor API.
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def _visit_function(self, node: ast.AsyncFunctionDef | ast.FunctionDef) -> None:
        qualname = ".".join([*self.stack, node.name])
        line_end = int(getattr(node, "end_lineno", node.lineno))
        self.functions.append(
            FunctionComplexity(
                path=self.path,
                qualname=qualname,
                line_start=node.lineno,
                line_end=line_end,
                lines=line_end - node.lineno + 1,
                branches=_count_function_branches(node),
            )
        )
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def _iter_non_nested_nodes(node: ast.AST) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (*_FUNCTION_NODES, ast.ClassDef, ast.Lambda)):
            continue
        nodes.append(child)
        nodes.extend(_iter_non_nested_nodes(child))
    return nodes


def _count_function_branches(node: ast.AsyncFunctionDef | ast.FunctionDef) -> int:
    return sum(1 for child in _iter_non_nested_nodes(node) if isinstance(child, _BRANCH_NODES))


def _is_ignored(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in _IGNORED_DIRS for part in relative.parts)


def iter_python_files(root: Path) -> list[Path]:
    resolved_root = root.resolve()
    return sorted(
        path
        for path in resolved_root.rglob("*.py")
        if path.is_file() and not _is_ignored(path, resolved_root)
    )


def analyze_python_file(path: Path, root: Path) -> FileComplexity:
    resolved_root = root.resolve()
    relative_path = path.resolve().relative_to(resolved_root).as_posix()
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=relative_path)
    collector = _FunctionCollector(relative_path)
    collector.visit(tree)
    return FileComplexity(
        path=relative_path,
        lines=len(text.splitlines()),
        functions=tuple(sorted(collector.functions, key=lambda item: item.baseline_key)),
    )


def load_complexity_baseline(path: Path | None = None) -> dict[str, Any]:
    baseline_path = path or DEFAULT_BASELINE_PATH
    if not baseline_path.exists():
        return {"schema_version": 1, "files": {}, "functions": {}}
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Complexity baseline must be a JSON object: {baseline_path}")
    payload.setdefault("files", {})
    payload.setdefault("functions", {})
    return payload


def scan_python_complexity(root: Path) -> list[FileComplexity]:
    resolved_root = root.resolve()
    files: list[FileComplexity] = []
    for path in iter_python_files(resolved_root):
        files.append(analyze_python_file(path, resolved_root))
    return files


def build_complexity_report(
    root: Path,
    *,
    baseline_path: Path | None = None,
    thresholds: ComplexityThresholds | None = None,
) -> dict[str, Any]:
    resolved_root = root.resolve()
    active_thresholds = thresholds or ComplexityThresholds()
    baseline_file = baseline_path or DEFAULT_BASELINE_PATH
    baseline = load_complexity_baseline(baseline_file)
    files = scan_python_complexity(resolved_root)
    functions = [function for file in files for function in file.functions]
    violations = [
        *_file_violations(files, baseline, active_thresholds),
        *_function_violations(functions, baseline, active_thresholds),
    ]
    violations.sort(
        key=lambda item: (str(item["path"]), str(item.get("qualname", "")), item["metric"])
    )
    files_over_threshold = [
        file.to_payload() for file in files if file.lines > active_thresholds.max_file_lines
    ]
    functions_over_threshold = [
        function.to_payload()
        for function in functions
        if function.lines > active_thresholds.max_function_lines
        or function.branches > active_thresholds.max_function_branches
    ]
    functions_over_threshold.sort(
        key=lambda item: (int(item["lines"]), int(item["branches"]), str(item["baseline_key"])),
        reverse=True,
    )
    files_over_threshold.sort(
        key=lambda item: (int(item["lines"]), str(item["path"])), reverse=True
    )
    passed = not violations
    return {
        "passed": passed,
        "status": "passed" if passed else "failed",
        "root": str(resolved_root),
        "baseline_path": str(baseline_file),
        "thresholds": active_thresholds.to_payload(),
        "files_scanned": len(files),
        "functions_scanned": len(functions),
        "summary": {
            "files_over_threshold": len(files_over_threshold),
            "functions_over_threshold": len(functions_over_threshold),
            "violations": len(violations),
            "baseline_files": len(baseline.get("files", {})),
            "baseline_functions": len(baseline.get("functions", {})),
        },
        "violations": violations,
        "hotspots": {
            "files": files_over_threshold[:20],
            "functions": functions_over_threshold[:20],
        },
    }


def _baseline_metadata_violation(
    entry: Any,
    *,
    kind: str,
    path: str,
    metric: str,
    observed: int,
    threshold: int,
    qualname: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return _violation(
            kind=kind,
            path=path,
            metric=metric,
            observed=observed,
            threshold=threshold,
            reason="missing_baseline",
            qualname=qualname,
        )
    missing = [
        key
        for key in ("owner", "extraction_plan")
        if not isinstance(entry.get(key), str) or not entry[key].strip()
    ]
    if missing:
        return _violation(
            kind=kind,
            path=path,
            metric=metric,
            observed=observed,
            threshold=threshold,
            reason="baseline_missing_metadata",
            qualname=qualname,
            baseline=entry,
            missing=missing,
        )
    return None


def _file_violations(
    files: list[FileComplexity],
    baseline: dict[str, Any],
    thresholds: ComplexityThresholds,
) -> list[dict[str, Any]]:
    baseline_files = baseline.get("files", {})
    violations: list[dict[str, Any]] = []
    for file in files:
        if file.lines <= thresholds.max_file_lines:
            continue
        entry = baseline_files.get(file.path) if isinstance(baseline_files, dict) else None
        metadata_violation = _baseline_metadata_violation(
            entry,
            kind="file",
            path=file.path,
            metric="lines",
            observed=file.lines,
            threshold=thresholds.max_file_lines,
        )
        if metadata_violation:
            violations.append(metadata_violation)
            continue
        allowed = _int_entry(entry, "lines")
        if allowed is None or file.lines > allowed:
            violations.append(
                _violation(
                    kind="file",
                    path=file.path,
                    metric="lines",
                    observed=file.lines,
                    threshold=thresholds.max_file_lines,
                    reason="baseline_growth",
                    baseline=entry,
                    allowed=allowed,
                )
            )
        elif file.lines < allowed:
            violations.append(
                _violation(
                    kind="file",
                    path=file.path,
                    metric="lines",
                    observed=file.lines,
                    threshold=thresholds.max_file_lines,
                    reason="baseline_not_ratcheted_down",
                    baseline=entry,
                    allowed=allowed,
                )
            )
    return violations


def _function_violations(
    functions: list[FunctionComplexity],
    baseline: dict[str, Any],
    thresholds: ComplexityThresholds,
) -> list[dict[str, Any]]:
    baseline_functions = baseline.get("functions", {})
    violations: list[dict[str, Any]] = []
    for function in functions:
        metrics = {
            "lines": (function.lines, thresholds.max_function_lines),
            "branches": (function.branches, thresholds.max_function_branches),
        }
        for metric, (observed, threshold) in metrics.items():
            if observed <= threshold:
                continue
            entry = (
                baseline_functions.get(function.baseline_key)
                if isinstance(baseline_functions, dict)
                else None
            )
            metadata_violation = _baseline_metadata_violation(
                entry,
                kind="function",
                path=function.path,
                qualname=function.qualname,
                metric=metric,
                observed=observed,
                threshold=threshold,
            )
            if metadata_violation:
                violations.append(metadata_violation)
                continue
            allowed = _int_entry(entry, metric)
            if allowed is None or observed > allowed:
                violations.append(
                    _violation(
                        kind="function",
                        path=function.path,
                        qualname=function.qualname,
                        metric=metric,
                        observed=observed,
                        threshold=threshold,
                        reason="baseline_growth",
                        baseline=entry,
                        allowed=allowed,
                    )
                )
            elif observed < allowed:
                violations.append(
                    _violation(
                        kind="function",
                        path=function.path,
                        qualname=function.qualname,
                        metric=metric,
                        observed=observed,
                        threshold=threshold,
                        reason="baseline_not_ratcheted_down",
                        baseline=entry,
                        allowed=allowed,
                    )
                )
    return violations


def _int_entry(entry: Any, key: str) -> int | None:
    if not isinstance(entry, dict):
        return None
    value = entry.get(key)
    return value if isinstance(value, int) else None


def _violation(
    *,
    kind: str,
    path: str,
    metric: str,
    observed: int,
    threshold: int,
    reason: str,
    qualname: str | None = None,
    baseline: Any = None,
    allowed: int | None = None,
    missing: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": kind,
        "path": path,
        "metric": metric,
        "observed": observed,
        "threshold": threshold,
        "reason": reason,
    }
    if qualname:
        payload["qualname"] = qualname
        payload["baseline_key"] = f"{path}::{qualname}"
    if allowed is not None:
        payload["allowed"] = allowed
    if missing:
        payload["missing"] = missing
    if isinstance(baseline, dict):
        payload["baseline_owner"] = baseline.get("owner", "")
        payload["baseline_extraction_plan"] = baseline.get("extraction_plan", "")
    return payload
