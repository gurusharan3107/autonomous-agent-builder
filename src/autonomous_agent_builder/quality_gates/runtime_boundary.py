"""Deterministic runtime boundary gate for builder-vs-runtime ownership."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTECTED_PATHS = (
    Path("src/autonomous_agent_builder/claude_runtime.py"),
    Path("src/autonomous_agent_builder/onboarding.py"),
    Path("src/autonomous_agent_builder/agents"),
)
ALLOWED_PATHS = {
    Path("src/autonomous_agent_builder/agents/tools/cli_tools.py"),
    Path("src/autonomous_agent_builder/services/builder_tool_service.py"),
}
FORBIDDEN_IMPORT_SUFFIXES = (
    "autonomous_agent_builder.agents.tools.cli_tools",
    "agents.tools.cli_tools",
)
SUBPROCESS_NAMES = {
    "create_subprocess_exec",
    "create_subprocess_shell",
    "run",
    "Popen",
    "call",
    "check_call",
    "check_output",
    "system",
}


@dataclass(frozen=True)
class RuntimeBoundaryViolation:
    rule: str
    path: Path
    line: int
    message: str
    remediation: str


def _iter_protected_files(repo_root: Path) -> list[Path]:
    protected: list[Path] = []
    for relative in PROTECTED_PATHS:
        absolute = repo_root / relative
        if absolute.is_dir():
            protected.extend(sorted(path for path in absolute.rglob("*.py") if path.is_file()))
        elif absolute.exists():
            protected.append(absolute)
    return [path for path in protected if path.relative_to(repo_root) not in ALLOWED_PATHS]


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _string_literal(node: ast.AST, string_scope: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return string_scope.get(node.id)
    return None


def _starts_with_builder(
    node: ast.AST,
    string_scope: dict[str, str],
    command_scope: dict[str, bool],
) -> bool:
    text = _string_literal(node, string_scope)
    if text is not None:
        stripped = text.strip()
        return stripped == "builder" or stripped.startswith("builder ")
    if isinstance(node, ast.Name):
        return command_scope.get(node.id, False)
    if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Starred):
            return False
        return _string_literal(first, string_scope) == "builder"
    return False


def _record_assignment(
    node: ast.Assign,
    string_scope: dict[str, str],
    command_scope: dict[str, bool],
) -> None:
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return
    text = _string_literal(node.value, string_scope)
    if text is not None:
        string_scope[node.targets[0].id] = text
    command_scope[node.targets[0].id] = _starts_with_builder(
        node.value,
        string_scope,
        command_scope,
    )


def _check_import(node: ast.AST, relative_path: Path) -> list[RuntimeBoundaryViolation]:
    violations: list[RuntimeBoundaryViolation] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.endswith(FORBIDDEN_IMPORT_SUFFIXES):
                violations.append(
                    RuntimeBoundaryViolation(
                        rule="runtime_cli_bridge_import",
                        path=relative_path,
                        line=node.lineno,
                        message="Runtime code imports the CLI bridge directly.",
                        remediation=(
                            "Import `autonomous_agent_builder.services.builder_tool_service` "
                            "instead so SDK/runtime code crosses the boundary through "
                            "the owning service layer."
                        ),
                    )
                )
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module.endswith(FORBIDDEN_IMPORT_SUFFIXES):
            violations.append(
                RuntimeBoundaryViolation(
                    rule="runtime_cli_bridge_import",
                    path=relative_path,
                    line=node.lineno,
                    message="Runtime code imports the CLI bridge directly.",
                    remediation=(
                        "Import `autonomous_agent_builder.services.builder_tool_service` "
                        "instead so SDK/runtime code crosses the boundary through "
                        "the owning service layer."
                    ),
                )
            )
        elif module.endswith("agents.tools"):
            for alias in node.names:
                if alias.name == "cli_tools":
                    violations.append(
                        RuntimeBoundaryViolation(
                            rule="runtime_cli_bridge_import",
                            path=relative_path,
                            line=node.lineno,
                            message="Runtime code imports the CLI bridge directly.",
                            remediation=(
                                "Import `autonomous_agent_builder.services.builder_tool_service` "
                                "instead so SDK/runtime code crosses the boundary through "
                                "the owning service layer."
                            ),
                        )
                    )
    return violations


def _check_builder_shellout(
    node: ast.Call,
    relative_path: Path,
    string_scope: dict[str, str],
    command_scope: dict[str, bool],
) -> list[RuntimeBoundaryViolation]:
    if _call_name(node) not in SUBPROCESS_NAMES or not node.args:
        return []
    shellout_arg = node.args[0]
    if isinstance(shellout_arg, ast.Starred):
        shellout_arg = shellout_arg.value
    if not _starts_with_builder(shellout_arg, string_scope, command_scope):
        return []
    return [
        RuntimeBoundaryViolation(
            rule="runtime_builder_shellout",
            path=relative_path,
            line=node.lineno,
            message="Runtime code shells out to `builder` directly.",
            remediation=(
                "Move this boundary crossing into "
                "`autonomous_agent_builder.services.builder_tool_service` or replace it "
                "with a direct service/API call."
            ),
        )
    ]


def scan_runtime_boundary(repo_root: Path | None = None) -> list[RuntimeBoundaryViolation]:
    root = (repo_root or REPO_ROOT).resolve()
    violations: list[RuntimeBoundaryViolation] = []
    for path in _iter_protected_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        string_scope: dict[str, str] = {}
        command_scope: dict[str, bool] = {}
        relative_path = path.relative_to(root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                _record_assignment(node, string_scope, command_scope)
            violations.extend(_check_import(node, relative_path))
            if isinstance(node, ast.Call):
                violations.extend(
                    _check_builder_shellout(
                        node,
                        relative_path,
                        string_scope,
                        command_scope,
                    )
                )
    return sorted(violations, key=lambda item: (str(item.path), item.line, item.rule))


def format_runtime_boundary_violations(violations: list[RuntimeBoundaryViolation]) -> str:
    lines = ["Runtime boundary violations detected:"]
    for violation in violations:
        lines.append(
            f"- {violation.path}:{violation.line} [{violation.rule}] {violation.message} "
            f"Fix: {violation.remediation}"
        )
    return "\n".join(lines)


def assert_runtime_boundary_clean(repo_root: Path | None = None) -> None:
    violations = scan_runtime_boundary(repo_root=repo_root)
    if violations:
        raise AssertionError(format_runtime_boundary_violations(violations))
