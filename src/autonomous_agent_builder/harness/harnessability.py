"""Harnessability scorer — evaluate project readiness for agent automation.

Score 0-8 based on checks:
- has_type_annotations (2 pts)
- has_linting_config (2 pts)
- has_test_suite (2 pts)
- has_module_boundaries (1 pt)
- has_api_contracts (1 pt)

Routing:
- score < 3 → REJECT (agents cannot safely work here)
- score 3-4 → ARCHITECT_REVIEW (review before any agent runs)
- score >= 5 → PROCEED
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from autonomous_agent_builder.db.models import HarnessAction

log = structlog.get_logger()


@dataclass
class HarnessabilityResult:
    """Result of harnessability assessment."""

    score: int
    checks: dict[str, Any]
    recommendations: list[str]
    routing_action: HarnessAction


# Check definitions: name -> (max_points, checker_function_name)
HARNESSABILITY_CHECKS = {
    "has_type_annotations": 2,
    "has_linting_config": 2,
    "has_test_suite": 2,
    "has_module_boundaries": 1,
    "has_api_contracts": 1,
}


def score_project(project_path: str, language: str = "python") -> HarnessabilityResult:
    """Score a project's harnessability (0-8)."""
    path = Path(project_path)
    checks: dict[str, Any] = {}
    recommendations: list[str] = []
    total_score = 0

    # Check 1: Type annotations (2 pts)
    type_score = _check_type_annotations(path, language)
    checks["has_type_annotations"] = {"score": type_score, "max": 2}
    total_score += type_score
    if type_score < 2:
        recommendations.append("Add type annotations to improve agent code generation accuracy")

    # Check 2: Linting config (2 pts)
    lint_score = _check_linting_config(path, language)
    checks["has_linting_config"] = {"score": lint_score, "max": 2}
    total_score += lint_score
    if lint_score < 2:
        recommendations.append(
            "Add linting configuration (ruff/eslint) for automated quality checks"
        )

    # Check 3: Test suite (2 pts)
    test_score = _check_test_suite(path, language)
    checks["has_test_suite"] = {"score": test_score, "max": 2}
    total_score += test_score
    if test_score < 2:
        recommendations.append("Add test suite with at least basic coverage for agent verification")

    # Check 4: Module boundaries (1 pt)
    module_score = _check_module_boundaries(path, language)
    checks["has_module_boundaries"] = {"score": module_score, "max": 1}
    total_score += module_score
    if module_score < 1:
        recommendations.append(
            "Organize code into clear modules (src/ layout, no circular imports)"
        )

    # Check 5: API contracts (1 pt)
    api_score = _check_api_contracts(path, language)
    checks["has_api_contracts"] = {"score": api_score, "max": 1}
    total_score += api_score
    if api_score < 1:
        recommendations.append(
            "Add API contracts (OpenAPI spec, typed interfaces, or function signatures)"
        )

    # Determine routing action
    if total_score < 3:
        action = HarnessAction.REJECT
    elif total_score < 5:
        action = HarnessAction.ARCHITECT_REVIEW
    else:
        action = HarnessAction.PROCEED

    log.info(
        "harnessability_scored",
        path=project_path,
        score=total_score,
        action=action.value,
    )

    return HarnessabilityResult(
        score=total_score,
        checks=checks,
        recommendations=recommendations,
        routing_action=action,
    )


def _check_type_annotations(path: Path, language: str) -> int:
    """Check for type annotation support."""
    score = 0

    if language == "python":
        # Check for mypy/pyright config
        if (path / "pyproject.toml").exists():
            content = (path / "pyproject.toml").read_text()
            if "mypy" in content or "pyright" in content:
                score += 1
        # Check for py.typed marker or type hints in source
        src_files = list(path.rglob("*.py"))
        typed_files = sum(1 for f in src_files[:20] if _file_has_type_hints(f))
        if typed_files > len(src_files[:20]) * 0.3:
            score += 1

    elif language in ("node", "typescript"):
        if (path / "tsconfig.json").exists():
            score += 2
        elif any(path.rglob("*.ts")):
            score += 1

    elif language == "java":
        score += 2  # Java is inherently typed

    return min(score, 2)


def _check_linting_config(path: Path, language: str) -> int:
    """Check for linting configuration."""
    score = 0

    if language == "python":
        if (path / "pyproject.toml").exists():
            content = (path / "pyproject.toml").read_text()
            if "ruff" in content or "flake8" in content or "pylint" in content:
                score += 2
            elif "tool." in content:
                score += 1
        if (path / ".flake8").exists() or (path / ".pylintrc").exists():
            score += 2

    elif language in ("node", "typescript", "javascript"):
        eslint_files = [".eslintrc", ".eslintrc.json", ".eslintrc.js", "eslint.config.mjs"]
        if any((path / f).exists() for f in eslint_files):
            score += 2

    elif language == "java":
        if (path / "checkstyle.xml").exists() or (path / "pmd.xml").exists():
            score += 2

    return min(score, 2)


def _check_test_suite(path: Path, language: str) -> int:
    """Check for test infrastructure."""
    score = 0

    if language == "python":
        test_dirs = [path / "tests", path / "test"]
        has_dir = any(d.is_dir() for d in test_dirs)
        if has_dir:
            score += 1
        test_files = list(path.rglob("test_*.py")) + list(path.rglob("*_test.py"))
        if len(test_files) >= 1:
            score += 1

    elif language in ("node", "typescript", "javascript"):
        test_dirs = [path / "__tests__", path / "tests", path / "test"]
        has_dir = any(d.is_dir() for d in test_dirs)
        test_files = (
            list(path.rglob("*.test.ts"))
            + list(path.rglob("*.test.js"))
            + list(path.rglob("*.spec.ts"))
        )
        if has_dir or test_files:
            score += 1
        if len(test_files) >= 1:
            score += 1

    elif language == "java":
        if (path / "src" / "test").is_dir():
            score += 2

    return min(score, 2)


def _check_module_boundaries(path: Path, language: str) -> int:
    """Check for clear module structure."""
    if language == "python" or language in ("node", "typescript"):
        if (path / "src").is_dir():
            return 1
    elif language == "java" and (path / "src" / "main" / "java").is_dir():
        return 1
    return 0


def _check_api_contracts(path: Path, language: str) -> int:
    """Check for API contract definitions."""
    # OpenAPI spec
    for name in ["openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"]:
        if (path / name).exists():
            return 1

    # TypeScript interfaces / Python protocols
    if language in ("node", "typescript"):
        for f in list(path.rglob("*.ts"))[:30]:
            try:
                if "interface " in f.read_text(encoding="utf-8"):
                    return 1
            except (OSError, UnicodeDecodeError):
                continue

    if language == "python":
        for f in list(path.rglob("*.py"))[:30]:
            try:
                content = f.read_text(encoding="utf-8")
                if "Protocol" in content or "@dataclass" in content or "BaseModel" in content:
                    return 1
            except (OSError, UnicodeDecodeError):
                continue

    return 0


def _file_has_type_hints(filepath: Path) -> bool:
    """Quick check if a Python file uses type hints."""
    try:
        content = filepath.read_text(encoding="utf-8")
        return any(
            marker in content
            for marker in [" -> ", ": str", ": int", ": list", ": dict", "Optional["]
        )
    except (OSError, UnicodeDecodeError):
        return False
