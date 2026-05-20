"""Run deterministic Playwright acceptance proof for a generated-app feature."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .base import Script, ScriptResult

_SCRIPT_PRIORITY = (
    "test:e2e",
    "e2e",
    "test:playwright",
    "playwright",
    "test:browser",
    "browser-proof",
)
# Fallback scripts when no Playwright/e2e command exists. Generic test
# runners (jest, mocha, jsdom-based, custom node scripts) are accepted
# as proof for HTML/CSS/JS apps that don't carry a real browser test
# harness — Playwright preferred, but a passing smoke test is better
# than blocking on missing infrastructure.
_FALLBACK_SCRIPT_PRIORITY = (
    "test:acceptance",
    "test:feature",
    "test:integration",
    "test:smoke",
    "test:run",
    "test",
)
_TEST_DIRS = ("tests", "test", "e2e", "playwright", "spec", "specs")
_TEST_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


class FeatureAcceptanceScript(Script):
    """Run feature-scoped Playwright acceptance tests when they exist."""

    @property
    def name(self) -> str:
        return "feature_acceptance"

    @property
    def description(self) -> str:
        return "Run deterministic Playwright feature acceptance tests"

    def validate_args(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "project_root" in kwargs and not isinstance(kwargs["project_root"], str):
            return False, "Argument 'project_root' must be a string"
        if "feature_title" in kwargs and not isinstance(kwargs["feature_title"], str):
            return False, "Argument 'feature_title' must be a string"
        if "feature_description" in kwargs and not isinstance(kwargs["feature_description"], str):
            return False, "Argument 'feature_description' must be a string"
        if "acceptance_criteria" in kwargs and not (
            isinstance(kwargs["acceptance_criteria"], list)
            and all(isinstance(item, str) for item in kwargs["acceptance_criteria"])
        ):
            return False, "Argument 'acceptance_criteria' must be a list of strings"
        if "timeout" in kwargs and (
            not isinstance(kwargs["timeout"], int) or kwargs["timeout"] <= 0
        ):
            return False, "Argument 'timeout' must be a positive integer"
        return True, None

    def run(self, **kwargs: Any) -> ScriptResult:
        project_root = Path(kwargs.get("project_root") or Path.cwd()).resolve()
        timeout = int(kwargs.get("timeout") or 180)
        feature_title = str(kwargs.get("feature_title") or "").strip()
        feature_description = str(kwargs.get("feature_description") or "").strip()
        acceptance_criteria = [
            str(item).strip()
            for item in (kwargs.get("acceptance_criteria") or [])
            if str(item).strip()
        ]
        if not project_root.exists() or not project_root.is_dir():
            return {
                "success": False,
                "data": {
                    "status": "blocked",
                    "reason": "project_root_missing",
                    "project_root": str(project_root),
                },
                "error": f"Project root does not exist: {project_root}",
            }

        package_json = self._load_package_json(project_root)
        command = self._select_playwright_command(project_root, package_json)
        coverage = self._coverage_signal(
            project_root,
            feature_title=feature_title,
            feature_description=feature_description,
            acceptance_criteria=acceptance_criteria,
        )
        base_data: dict[str, Any] = {
            "feature_title": feature_title,
            "acceptance_criteria": acceptance_criteria,
            "coverage": coverage,
            "expected_next_on_failure": "run feature-verifier agent to validate product behavior and create or repair Playwright tests",
        }
        if not command:
            data = {
                **base_data,
                "status": "missing_test_command",
                "reason": "no_acceptance_test_command",
                "available_scripts": sorted((package_json.get("scripts") or {}).keys()),
            }
            return {
                "success": False,
                "data": data,
                "error": (
                    "No acceptance test command found. Looked for: "
                    "Playwright (test:e2e/test:playwright/etc.), generic test "
                    "scripts (test/test:acceptance/etc.), and a top-level "
                    "run-tests.js. Add a test runner script or have the "
                    "feature-verifier agent create one."
                ),
            }

        result = self._run_command(command, project_root, timeout)
        data = {
            **base_data,
            "status": "passed" if result["status"] == "passed" else "failed",
            "command": command,
            "checks": [result],
        }
        if result["status"] == "passed" and not coverage["covered"]:
            data["status"] = "coverage_unclear"
            return {
                "success": False,
                "data": data,
                "error": "Playwright command passed, but no feature-scoped acceptance coverage was detected",
            }
        if result["status"] != "passed":
            return {
                "success": False,
                "data": data,
                "error": "Playwright feature acceptance failed",
            }
        return {"success": True, "data": data, "error": None}

    def _load_package_json(self, project_root: Path) -> dict[str, Any]:
        path = project_root / "package.json"
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _select_playwright_command(
        self,
        project_root: Path,
        package_json: dict[str, Any],
    ) -> list[str]:
        scripts = package_json.get("scripts")
        scripts = scripts if isinstance(scripts, dict) else {}
        for name in _SCRIPT_PRIORITY:
            if isinstance(scripts.get(name), str):
                return ["npm", "run", name]
        for name, command in scripts.items():
            text = f"{name} {command}".lower()
            if "playwright" in text or ("e2e" in text and "test" in text):
                return ["npm", "run", str(name)]
        local_playwright = project_root / "node_modules" / ".bin" / "playwright"
        if local_playwright.exists() and self._has_playwright_config(project_root):
            return [str(local_playwright), "test"]
        # Fallback: generic test scripts when no Playwright is configured.
        # Vanilla HTML/CSS/JS workspaces typically don't carry a Playwright
        # harness — a passing jsdom/jest/mocha or custom node test is still
        # acceptance proof for the agreed scope.
        for name in _FALLBACK_SCRIPT_PRIORITY:
            if isinstance(scripts.get(name), str):
                return ["npm", "run", name]
        # Last resort: a top-level `run-tests.js` that executes the suite.
        # The feature-verifier agent often writes one for no-build-step apps.
        run_tests = project_root / "run-tests.js"
        if run_tests.exists():
            return ["node", str(run_tests)]
        return []

    def _has_playwright_config(self, project_root: Path) -> bool:
        return any(project_root.glob("playwright.config.*"))

    def _coverage_signal(
        self,
        project_root: Path,
        *,
        feature_title: str,
        feature_description: str,
        acceptance_criteria: list[str],
    ) -> dict[str, Any]:
        terms = self._feature_terms(feature_title, feature_description, acceptance_criteria)
        files = self._test_files(project_root)
        matched_terms: set[str] = set()
        matched_files: list[str] = []
        bytes_scanned = 0
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            bytes_scanned += len(text)
            lower = text.lower()
            file_matches = {term for term in terms if term in lower}
            if file_matches:
                matched_terms.update(file_matches)
                matched_files.append(str(path.relative_to(project_root)))
            if bytes_scanned > 500_000:
                break
        required_matches = min(2, len(terms))
        return {
            "covered": not terms or len(matched_terms) >= required_matches,
            "terms": terms,
            "matched_terms": sorted(matched_terms),
            "matched_files": sorted(set(matched_files)),
            "test_files_scanned": len(files),
            "required_term_matches": required_matches,
        }

    def _feature_terms(
        self,
        feature_title: str,
        feature_description: str,
        acceptance_criteria: list[str],
    ) -> list[str]:
        text = " ".join([feature_title, feature_description, *acceptance_criteria]).lower()
        tokens = re.findall(r"[a-z0-9]+", text)
        stopwords = {
            "able",
            "after",
            "with",
            "when",
            "that",
            "this",
            "from",
            "they",
            "user",
            "users",
            "feature",
            "should",
            "create",
            "view",
            "edit",
            "test",
            "tests",
        }
        terms = [
            token
            for token in tokens
            if len(token) >= 4 and token not in stopwords and not token.isdigit()
        ]
        return sorted(set(terms))[:12]

    def _test_files(self, project_root: Path) -> list[Path]:
        files: list[Path] = []
        for dirname in _TEST_DIRS:
            root = project_root / dirname
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if (
                    path.is_file()
                    and path.suffix in _TEST_SUFFIXES
                    and "node_modules" not in path.parts
                ):
                    files.append(path)
        return sorted(set(files))

    def _run_command(
        self,
        command: list[str],
        cwd: Path,
        timeout: int,
    ) -> dict[str, Any]:
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
                "type": "playwright",
                "command": command,
                "status": "failed",
                "exit_code": None,
                "duration_timeout_seconds": timeout,
                "stdout_tail": self._tail(exc.stdout or ""),
                "stderr_tail": self._tail(exc.stderr or ""),
            }
        return {
            "type": "playwright",
            "command": command,
            "status": "passed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "stdout_tail": self._tail(result.stdout),
            "stderr_tail": self._tail(result.stderr),
        }

    def _tail(self, text: str, limit: int = 4000) -> str:
        return str(text or "")[-limit:]
