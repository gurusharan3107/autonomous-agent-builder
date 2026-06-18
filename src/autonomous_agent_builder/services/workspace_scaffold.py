"""Workspace scaffold helpers used by the orchestrator and the
`mcp__builder__workspace_scaffold` tool.

Scaffold is the runtime-decided bootstrap step that runs before the first
`code-gen` dispatch for a task. It writes the minimum lint/test config a
workspace needs so quality gates can resolve their binaries instead of
failing with FileNotFoundError. See `docs/rubric/autonomous-builder-agents.md`
section "scaffold" for the agent contract and quality bar.

This module only owns the pure helpers (pre-check, JSON parsing, language
persistence). The orchestrator and the route handler compose these with
`_run_agent("scaffold", ...)` and the task lifecycle.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.models import Project
from autonomous_agent_builder.onboarding import _detect_language

_SCAFFOLD_RESULT_PREFIX = "SCAFFOLD_RESULT_JSON:"


@dataclass(frozen=True)
class ScaffoldResult:
    """Outcome of a scaffold attempt.

    `action="skipped"` means the workspace already had a detectable language;
    `"scaffolded"` means the agent ran and the result JSON was parsed
    successfully; `"blocked"` means a deterministic failure occurred and the
    task should be blocked with an actionable reason.
    """

    action: str
    language: str = ""
    stack: str = ""
    files_written: tuple[str, ...] = ()
    gate_set: tuple[str, ...] = ()
    reason: str = ""
    raw_output: str = field(default="", repr=False)


def should_scaffold(workspace_path: str) -> tuple[bool, str]:
    """Return (needs_scaffold, detected_language).

    Returns False with the detected language ONLY when the workspace has both
    (a) a detectable language AND (b) the per-language gate config that quality
    gates need to run. Otherwise returns True with the best-effort detected
    language so the orchestrator runs the scaffold agent.

    The gate-config check (e.g. pyproject.toml for python) was added after
    live testing surfaced a workspace where `requirements.txt` existed (→
    language=python) but `pyproject.toml` was missing — code_quality gate
    then errored with FileNotFoundError trying to run ruff. See FINDING-20
    in docs/IMPROVEMENTS.md.
    """
    path = Path(workspace_path)
    if not path.exists():
        return True, "unknown"
    detected = _detect_language(path)
    if detected == "unknown":
        return True, "unknown"
    if not _language_has_gate_config(path, detected):
        return True, detected
    return False, detected


def _language_has_gate_config(workspace: Path, language: str) -> bool:
    """Heuristic: do the per-language gate config files exist?"""
    if language == "python":
        return (workspace / "pyproject.toml").exists()
    if language == "node":
        return (workspace / "package.json").exists() and (
            (workspace / "eslint.config.js").exists()
            or (workspace / ".eslintrc.json").exists()
            or (workspace / ".eslintrc.js").exists()
            or (workspace / ".eslintrc").exists()
        )
    if language == "go":
        return (workspace / "go.mod").exists()
    if language == "rust":
        return (workspace / "Cargo.toml").exists()
    if language == "java":
        return (workspace / "pom.xml").exists() or (workspace / "build.gradle").exists()
    return True


def parse_scaffold_result(output_text: str) -> ScaffoldResult:
    """Parse the trailing `SCAFFOLD_RESULT_JSON:` line from agent output.

    Tolerates trailing whitespace and surrounding code-fence markers. Raises
    no exceptions — returns a `ScaffoldResult(action="blocked", reason=...)`
    when the marker or JSON is missing or malformed. The orchestrator turns
    that into an actionable blocked_reason.
    """
    if not output_text:
        return ScaffoldResult(
            action="blocked",
            reason="scaffold_failed: agent returned empty output",
            raw_output="",
        )
    match = re.search(
        rf"{re.escape(_SCAFFOLD_RESULT_PREFIX)}\s*(\{{.*?\}})\s*$",
        output_text,
        flags=re.DOTALL,
    )
    if not match:
        return ScaffoldResult(
            action="blocked",
            reason=(
                "scaffold_failed: agent output is missing the "
                f"`{_SCAFFOLD_RESULT_PREFIX}` line"
            ),
            raw_output=output_text,
        )
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return ScaffoldResult(
            action="blocked",
            reason=f"scaffold_failed: malformed SCAFFOLD_RESULT_JSON ({exc})",
            raw_output=output_text,
        )
    if not isinstance(data, dict):
        return ScaffoldResult(
            action="blocked",
            reason="scaffold_failed: SCAFFOLD_RESULT_JSON must be an object",
            raw_output=output_text,
        )
    language = str(data.get("language", "") or "").strip().lower()
    if not language:
        return ScaffoldResult(
            action="blocked",
            reason="scaffold_failed: SCAFFOLD_RESULT_JSON missing `language`",
            raw_output=output_text,
        )
    return ScaffoldResult(
        action="scaffolded",
        language=language,
        stack=str(data.get("stack", "") or "").strip(),
        files_written=tuple(str(p) for p in (data.get("files_written") or [])),
        gate_set=tuple(str(g) for g in (data.get("gate_set") or [])),
        raw_output=output_text,
    )


async def persist_scaffold_language(
    project: Project,
    language: str,
    db: AsyncSession,
) -> None:
    """Update `Project.language` in the DB so subsequent gates pick up the right binaries."""
    project.language = language
    await db.flush()


_MINIMAL_PYPROJECT_TEMPLATE = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{project_name}"
version = "0.0.1"
description = "Generated app scaffold"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.5"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
"""

_MINIMAL_PACKAGE_JSON_TEMPLATE = """\
{{
  "name": "{project_name}",
  "version": "0.0.1",
  "private": true,
  "scripts": {{
    "lint": "eslint .",
    "test": "node --test"
  }},
  "devDependencies": {{
    "eslint": "^9.0.0",
    "globals": "^15.0.0"
  }}
}}
"""

_MINIMAL_ESLINT_CONFIG = """\
import js from "@eslint/js";
import globals from "globals";
export default [
  js.configs.recommended,
  {{
    files: ["**/*.js"],
    languageOptions: {{
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {{
        ...globals.browser,
        ...globals.node,
      }},
    }},
    rules: {{
      "no-unused-vars": "warn",
      "no-undef": "error",
      "no-console": "off",
    }},
  }},
];
"""


def write_minimal_gate_config(
    workspace_path: str, language: str, project_name: str = "app"
) -> tuple[bool, list[str]]:
    """Deterministic emergency safety net for when the model-backed scaffold
    agent claims success but doesn't actually produce the per-language gate
    config the workspace needs. Returns (wrote_anything, [paths_written]).

    Gates are project-type-specific — this fallback only covers the most
    common live failure modes (python, node). The primary path is the
    model-backed scaffold agent, which is responsible for any language
    (java/go/rust/elixir/swift/etc.). When this fallback can't help, the
    orchestrator surfaces a scaffold_failed: blocked_reason that the
    operator can recover through the dashboard.
    """
    path = Path(workspace_path)
    safe_name = (project_name or "app").strip().replace(" ", "-").lower() or "app"
    written: list[str] = []

    if language == "python":
        pyproject = path / "pyproject.toml"
        if not (pyproject.exists() and pyproject.read_text().strip()):
            pyproject.write_text(_MINIMAL_PYPROJECT_TEMPLATE.format(project_name=safe_name))
            written.append(str(pyproject))
        # Best-effort: ensure src and tests __init__.py exist so imports resolve.
        src_dir = path / "src"
        if src_dir.exists() and src_dir.is_dir():
            for child in src_dir.iterdir():
                if child.is_dir() and not (child / "__init__.py").exists():
                    (child / "__init__.py").write_text("")
                    written.append(str(child / "__init__.py"))
        tests_dir = path / "tests"
        if tests_dir.exists() and tests_dir.is_dir():
            init_file = tests_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("")
                written.append(str(init_file))
        return bool(written), written

    if language == "node":
        package_json = path / "package.json"
        if not (package_json.exists() and package_json.read_text().strip()):
            package_json.write_text(_MINIMAL_PACKAGE_JSON_TEMPLATE.format(project_name=safe_name))
            written.append(str(package_json))
        eslint_config = path / "eslint.config.js"
        # Honor any pre-existing legacy config file.
        legacy = any(
            (path / name).exists()
            for name in (".eslintrc.json", ".eslintrc.js", ".eslintrc")
        )
        if not eslint_config.exists() and not legacy:
            eslint_config.write_text(_MINIMAL_ESLINT_CONFIG)
            written.append(str(eslint_config))
        return bool(written), written

    # Other languages (go/rust/java/etc.) fall through. The orchestrator will
    # surface a scaffold_failed: reason naming the missing config.
    return False, []


def build_scaffold_template_vars(
    *,
    feature_description: str,
    project_name: str,
    workspace_path: str,
    operator_answers: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build the template_vars dict for `_run_agent("scaffold", ...)`."""
    if operator_answers:
        answers_text = json.dumps(operator_answers, sort_keys=True)
    else:
        answers_text = "(none yet)"
    return {
        "feature_description": feature_description or "(no description)",
        "project_name": project_name or "(unnamed project)",
        "workspace_path": workspace_path,
        "operator_answers": answers_text,
    }
