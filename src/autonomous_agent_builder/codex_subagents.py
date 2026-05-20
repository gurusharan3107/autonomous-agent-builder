"""Deterministic checks for project-scoped Codex custom agents."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_MODELS = {
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
    "gpt-5.2",
}

REQUIRED_AGENT_KEYS = ("name", "description", "developer_instructions")
REQUIRED_PROJECT_AGENTS = {
    "architecture_reviewer",
    "code-simplifier",
    "code_reviewer",
}
REQUIRED_RUNTIME_BOUNDARY = "not a claude agent sdk runtime agent"
REQUIRED_PRODUCT_BOUNDARY = "builder product specialist"
REQUIRED_ARCHITECTURE_REVIEWER_CONTRACT = (
    "boundary map",
    "findings",
    "recommended owner surfaces",
    "next step",
)
REQUIRED_CODE_REVIEWER_CONTRACT = (
    "findings",
    "correctness",
    "security",
    "regression",
    "owner-surface",
    "tests",
    "severity",
)
REQUIRED_RECOMMENDATION_QUALITY_CONTRACT = (
    "evidence-grounded",
    "actionable",
    "scope-boundary",
    "verification",
    "impact",
)
FORBIDDEN_CONFIG_DESCRIPTION_PHRASES = (
    "claude agent sdk runtime agent",
    "runtime specialist",
    "builder product",
    "product specialist",
    "product runs",
    "phase routing",
)


@dataclass(frozen=True)
class CodexSubagentIssue:
    """A single project Codex subagent validation issue."""

    code: str
    path: str
    message: str

    def to_payload(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True)
class CodexSubagentValidation:
    """Validation result for project-scoped Codex custom agents."""

    ok: bool
    agents: tuple[str, ...]
    issues: tuple[CodexSubagentIssue, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "status": "ok" if self.ok else "failed",
            "agents": list(self.agents),
            "issues": [issue.to_payload() for issue in self.issues],
            "schema_version": "1",
        }


def _load_toml(path: Path) -> tuple[dict[str, Any], CodexSubagentIssue | None]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, CodexSubagentIssue("invalid_toml", str(path), str(exc))
    if not isinstance(data, dict):
        return {}, CodexSubagentIssue("invalid_toml", str(path), "TOML root must be a table.")
    return data, None


def _string_value(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _validate_agent_file(path: Path) -> tuple[str | None, list[CodexSubagentIssue]]:
    data, parse_issue = _load_toml(path)
    if parse_issue is not None:
        return None, [parse_issue]

    issues: list[CodexSubagentIssue] = []
    for key in REQUIRED_AGENT_KEYS:
        if _string_value(data, key) is None:
            issues.append(
                CodexSubagentIssue(
                    "missing_required_key",
                    str(path),
                    f"Custom agent file must define non-empty '{key}'.",
                )
            )

    name = _string_value(data, "name")
    model = _string_value(data, "model")
    if model is not None and model not in SUPPORTED_MODELS:
        issues.append(
            CodexSubagentIssue(
                "unsupported_model",
                str(path),
                f"Model '{model}' is not in the supported Codex model allowlist.",
            )
        )

    instructions = _string_value(data, "developer_instructions") or ""
    if name in REQUIRED_PROJECT_AGENTS:
        _validate_repo_optimization_agent(path, name, data, instructions, issues)

    return name, issues


def _validate_repo_optimization_agent(
    path: Path,
    name: str,
    data: dict[str, Any],
    instructions: str,
    issues: list[CodexSubagentIssue],
) -> None:
    if "autonomous-agent-builder" not in instructions:
        issues.append(
            CodexSubagentIssue(
                "missing_repo_scope",
                str(path),
                "Repo optimization agents must name autonomous-agent-builder explicitly.",
            )
        )
    if "Claude Agent SDK" not in instructions:
        issues.append(
            CodexSubagentIssue(
                "missing_runtime_boundary",
                str(path),
                "Repo optimization agents must state the Claude Agent SDK/runtime boundary.",
            )
        )
    if REQUIRED_RUNTIME_BOUNDARY not in instructions.lower():
        issues.append(
            CodexSubagentIssue(
                "missing_codex_only_boundary",
                str(path),
                "Repo optimization agents must explicitly say they are not a Claude Agent SDK runtime agent.",
            )
        )
    if REQUIRED_PRODUCT_BOUNDARY not in instructions.lower():
        issues.append(
            CodexSubagentIssue(
                "missing_product_boundary",
                str(path),
                "Repo optimization agents must state the Builder product-specialist boundary.",
            )
        )

    sandbox_mode = _string_value(data, "sandbox_mode")
    if name in {"architecture_reviewer", "code_reviewer"} and sandbox_mode != "read-only":
        issues.append(
            CodexSubagentIssue(
                "reviewer_not_read_only",
                str(path),
                f"{name} must stay read-only.",
            )
        )
    if name == "architecture_reviewer":
        _append_missing_phrase_issues(
            path,
            instructions,
            REQUIRED_ARCHITECTURE_REVIEWER_CONTRACT,
            "missing_architecture_reviewer_contract",
            "architecture_reviewer instructions must include",
            issues,
        )
    _validate_recommendation_quality_contract(path, name, instructions, issues)
    if name == "code_reviewer":
        _append_missing_phrase_issues(
            path,
            instructions,
            REQUIRED_CODE_REVIEWER_CONTRACT,
            "missing_reviewer_contract",
            "code_reviewer instructions must include",
            issues,
        )
    if name == "code-simplifier":
        if sandbox_mode != "workspace-write":
            issues.append(
                CodexSubagentIssue(
                    "simplifier_wrong_sandbox",
                    str(path),
                    "code-simplifier must use workspace-write so edits remain project-scoped.",
                )
            )
        _append_missing_phrase_issues(
            path,
            instructions,
            ("Preserve functionality", "recently modified", "Verification"),
            "missing_simplifier_contract",
            "code-simplifier instructions must include",
            issues,
            case_sensitive=True,
        )


def _append_missing_phrase_issues(
    path: Path,
    instructions: str,
    required_phrases: tuple[str, ...],
    code: str,
    message_prefix: str,
    issues: list[CodexSubagentIssue],
    *,
    case_sensitive: bool = False,
) -> None:
    haystack = instructions if case_sensitive else instructions.lower()
    for phrase in required_phrases:
        needle = phrase if case_sensitive else phrase.lower()
        if needle not in haystack:
            issues.append(
                CodexSubagentIssue(
                    code,
                    str(path),
                    f"{message_prefix} '{phrase}'.",
                )
            )


def _validate_recommendation_quality_contract(
    path: Path,
    name: str,
    instructions: str,
    issues: list[CodexSubagentIssue],
) -> None:
    _append_missing_phrase_issues(
        path,
        instructions,
        REQUIRED_RECOMMENDATION_QUALITY_CONTRACT,
        "missing_recommendation_quality_contract",
        f"{name} instructions must include recommendation-quality criterion",
        issues,
    )


def _validate_config_description(
    config_path: Path,
    config_name: str,
    config_value: dict[str, Any],
    issues: list[CodexSubagentIssue],
) -> None:
    description = _string_value(config_value, "description")
    if description is None:
        return
    normalized = description.lower()
    for phrase in FORBIDDEN_CONFIG_DESCRIPTION_PHRASES:
        if phrase in normalized:
            issues.append(
                CodexSubagentIssue(
                    "config_description_boundary_drift",
                    str(config_path),
                    (
                        f"Agent config '{config_name}' description must not claim "
                        f"runtime/product ownership via '{phrase}'."
                    ),
                )
            )


def validate_project_codex_subagents(repo_root: Path) -> CodexSubagentValidation:
    """Validate project-scoped Codex custom agent config under ``.codex``."""

    codex_root = repo_root / ".codex"
    config_path = codex_root / "config.toml"
    agents_root = codex_root / "agents"
    issues: list[CodexSubagentIssue] = []

    config, parse_issue = _load_toml(config_path)
    if parse_issue is not None:
        return CodexSubagentValidation(False, (), (parse_issue,))

    agent_config = config.get("agents")
    if not isinstance(agent_config, dict):
        issues.append(
            CodexSubagentIssue(
                "missing_agents_config",
                str(config_path),
                ".codex/config.toml must define an [agents] table.",
            )
        )
        agent_config = {}

    discovered: dict[str, Path] = {}
    for path in sorted(agents_root.glob("*.toml")):
        name, agent_issues = _validate_agent_file(path)
        issues.extend(agent_issues)
        if name is None:
            continue
        if name in discovered:
            issues.append(
                CodexSubagentIssue(
                    "duplicate_agent_name",
                    str(path),
                    f"Agent name '{name}' is already defined in {discovered[name]}.",
                )
            )
        discovered[name] = path

    for required_name in sorted(REQUIRED_PROJECT_AGENTS):
        if required_name not in discovered:
            issues.append(
                CodexSubagentIssue(
                    "missing_required_project_agent",
                    str(agents_root),
                    f"Required project Codex agent '{required_name}' is missing.",
                )
            )

    resolved_agents_root = agents_root.resolve()

    for config_name, config_value in sorted(agent_config.items()):
        if not isinstance(config_value, dict):
            continue
        _validate_config_description(config_path, config_name, config_value, issues)
        config_file = _string_value(config_value, "config_file")
        if config_file is None:
            issues.append(
                CodexSubagentIssue(
                    "missing_config_file_entry",
                    str(config_path),
                    f"Agent config '{config_name}' must define config_file.",
                )
            )
            continue
        target = (codex_root / config_file).resolve()
        if not target.is_relative_to(resolved_agents_root):
            issues.append(
                CodexSubagentIssue(
                    "config_file_outside_agents",
                    str(config_path),
                    f"Agent config '{config_name}' points outside .codex/agents: {config_file}.",
                )
            )
            continue
        if not target.exists():
            issues.append(
                CodexSubagentIssue(
                    "missing_config_file",
                    str(config_path),
                    f"Agent config '{config_name}' points at missing file {config_file}.",
                )
            )
            continue
        agent_name, agent_issues = _validate_agent_file(target)
        issues.extend(agent_issues)
        if agent_name is not None and agent_name != config_name:
            issues.append(
                CodexSubagentIssue(
                    "config_name_mismatch",
                    str(config_path),
                    f"Config entry '{config_name}' points to agent named '{agent_name}'.",
                )
            )

    registered = {
        name
        for name, value in agent_config.items()
        if isinstance(value, dict) and _string_value(value, "config_file") is not None
    }
    missing_registrations = sorted(set(discovered) - registered)
    for name in missing_registrations:
        issues.append(
            CodexSubagentIssue(
                "missing_config_registration",
                str(config_path),
                f"Agent '{name}' exists under .codex/agents but is not registered.",
            )
        )

    return CodexSubagentValidation(
        ok=not issues,
        agents=tuple(sorted(discovered)),
        issues=tuple(issues),
    )
