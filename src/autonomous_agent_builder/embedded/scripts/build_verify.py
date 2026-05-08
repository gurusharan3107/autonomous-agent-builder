"""Run deterministic build, test, lint, and app-smoke proof for a workspace."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import urlopen

from .base import Script, ScriptResult


class BuildVerifyScript(Script):
    """Run deterministic verification commands inferred from the workspace."""

    @property
    def name(self) -> str:
        return "build_verify"

    @property
    def description(self) -> str:
        return "Run deterministic lint, build, test, and optional app smoke checks"

    def validate_args(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "project_root" in kwargs and not isinstance(kwargs["project_root"], str):
            return False, "Argument 'project_root' must be a string"
        if "app_url" in kwargs and not isinstance(kwargs["app_url"], str):
            return False, "Argument 'app_url' must be a string"
        if "timeout" in kwargs and (
            not isinstance(kwargs["timeout"], int) or kwargs["timeout"] <= 0
        ):
            return False, "Argument 'timeout' must be a positive integer"
        if "paths" in kwargs and not (
            isinstance(kwargs["paths"], list)
            and all(isinstance(item, str) for item in kwargs["paths"])
        ):
            return False, "Argument 'paths' must be a list of strings"
        return True, None

    def run(self, **kwargs: Any) -> ScriptResult:
        project_root = Path(kwargs.get("project_root") or Path.cwd()).resolve()
        timeout = int(kwargs.get("timeout") or 120)
        if not project_root.exists() or not project_root.is_dir():
            return {
                "success": False,
                "data": None,
                "error": f"Project root does not exist: {project_root}",
            }

        checks = self._planned_checks(project_root)
        results = [self._run_command(check, cwd=project_root, timeout=timeout) for check in checks]
        app_url = str(kwargs.get("app_url") or "").strip()
        if app_url:
            paths = kwargs.get("paths") or ["/"]
            results.extend(self._smoke_url(app_url, path, timeout=timeout) for path in paths)

        failed = [item for item in results if item["status"] != "passed"]
        return {
            "success": not failed,
            "data": {
                "schema_version": "1",
                "project_root": str(project_root),
                "checks": results,
                "summary": {
                    "total": len(results),
                    "passed": len(results) - len(failed),
                    "failed": len(failed),
                    "skipped": 0,
                },
                "next": "fix failing deterministic proof" if failed else "ready_for_browser_proof",
            },
            "error": None if not failed else "One or more deterministic verification checks failed",
        }

    def _planned_checks(self, project_root: Path) -> list[dict[str, Any]]:
        package_json = project_root / "package.json"
        checks: list[dict[str, Any]] = []
        if package_json.exists():
            scripts = self._package_scripts(package_json)
            if "lint" in scripts:
                checks.append({"code": "npm_lint", "command": ["npm", "run", "lint"]})
            if "build" in scripts:
                checks.append({"code": "npm_build", "command": ["npm", "run", "build"]})
            if "test" in scripts:
                checks.append({"code": "npm_test", "command": ["npm", "test"]})
            return checks

        has_python_project = any(
            (project_root / name).exists()
            for name in ("pyproject.toml", "setup.py", "setup.cfg")
        )
        if has_python_project and (project_root / "tests").exists():
            checks.append({"code": "pytest", "command": [sys.executable, "-m", "pytest", "-q"]})
        return checks

    def _package_scripts(self, package_json: Path) -> dict[str, Any]:
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        scripts = payload.get("scripts")
        return scripts if isinstance(scripts, dict) else {}

    def _run_command(
        self,
        check: dict[str, Any],
        *,
        cwd: Path,
        timeout: int,
    ) -> dict[str, Any]:
        command = [str(part) for part in check["command"]]
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "code": check["code"],
                "type": "command",
                "command": command,
                "status": "failed",
                "exit_code": None,
                "duration_timeout_seconds": timeout,
                "stdout_tail": self._tail(exc.stdout or ""),
                "stderr_tail": self._tail(exc.stderr or ""),
            }
        return {
            "code": check["code"],
            "type": "command",
            "command": command,
            "status": "passed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "stdout_tail": self._tail(result.stdout),
            "stderr_tail": self._tail(result.stderr),
        }

    def _smoke_url(self, app_url: str, path: str, *, timeout: int) -> dict[str, Any]:
        target = urljoin(app_url.rstrip("/") + "/", path.lstrip("/"))
        try:
            with urlopen(target, timeout=timeout) as response:
                status_code = int(response.status)
                content = response.read(2048)
        except URLError as exc:
            return {
                "code": "app_smoke",
                "type": "http_smoke",
                "url": target,
                "status": "failed",
                "error": str(exc),
            }
        return {
            "code": "app_smoke",
            "type": "http_smoke",
            "url": target,
            "status": "passed" if 200 <= status_code < 500 and bool(content) else "failed",
            "status_code": status_code,
            "bytes_read": len(content),
        }

    def _tail(self, text: str, limit: int = 4000) -> str:
        return text[-limit:]
