"""Collect deterministic changed-file evidence for the current workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.runner import capture_workspace_diff

from .base import Script, ScriptResult


class ChangeEvidenceScript(Script):
    """Collect deterministic changed-file and diff evidence."""

    @property
    def name(self) -> str:
        return "change_evidence"

    @property
    def description(self) -> str:
        return "Collect deterministic changed-file and diff evidence"

    def validate_args(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "project_root" in kwargs and not isinstance(kwargs["project_root"], str):
            return False, "Argument 'project_root' must be a string"
        return True, None

    def run(self, **kwargs: Any) -> ScriptResult:
        project_root = Path(kwargs.get("project_root") or Path.cwd()).resolve()
        if not project_root.exists() or not project_root.is_dir():
            return {
                "success": False,
                "data": None,
                "error": f"Project root does not exist: {project_root}",
            }
        diff_summary = capture_workspace_diff(str(project_root))
        files = diff_summary.get("files", []) if isinstance(diff_summary, dict) else []
        return {
            "success": True,
            "data": {
                "schema_version": "1",
                "project_root": str(project_root),
                "has_changes": bool(diff_summary),
                "files_changed": int(diff_summary.get("files_changed", 0)) if diff_summary else 0,
                "insertions": int(diff_summary.get("insertions", 0)) if diff_summary else 0,
                "deletions": int(diff_summary.get("deletions", 0)) if diff_summary else 0,
                "files": files,
                "hunks": diff_summary.get("hunks", []) if diff_summary else [],
                "next": "ready_for_review_summary"
                if diff_summary
                else "no_workspace_diff_detected",
            },
            "error": None,
        }
