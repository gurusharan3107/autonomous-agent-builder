"""Testing gate — pytest for Python, Jest for Node.js, JUnit for Java."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from autonomous_agent_builder.quality_gates.base import GateResult, GateStatus, QualityGate

_PYTHON_LANGUAGE_ALIASES = {
    "python",
    "py",
}
_PYTHON_FRAMEWORK_ALIASES = {
    "flask",
    "fastapi",
    "django",
}
_NODE_LANGUAGE_ALIASES = {
    "node",
    "nodejs",
    "javascript",
    "typescript",
    "react",
    "vite",
    "next",
    "nextjs",
}


class TestingGate(QualityGate):
    """Run project test suite and report results."""

    name = "testing"
    gate_type = "testing"

    def __init__(
        self,
        language: str = "python",
        coverage_threshold: int = 80,
        testing_doc_id: str | None = None,
    ):
        self.language = language
        self.coverage_threshold = coverage_threshold
        self.testing_doc_id = testing_doc_id

    async def run(self, workspace_path: str) -> GateResult:
        language = self._effective_language(workspace_path)
        if language == "python":
            return await self._run_pytest(workspace_path)
        elif language in ("node", "javascript", "typescript"):
            return await self._run_node_tests(workspace_path)
        elif language == "java":
            return await self._run_maven_test(workspace_path)
        else:
            return GateResult(
                gate_name=self.name, status=GateStatus.WARN, error_code="UNSUPPORTED_LANGUAGE"
            )

    def _effective_language(self, workspace_path: str) -> str:
        configured = self._normalize_language(self.language)
        if configured in _NODE_LANGUAGE_ALIASES:
            return "node"
        if configured in _PYTHON_FRAMEWORK_ALIASES:
            return "python"
        if configured == "java":
            return "java"

        workspace = Path(workspace_path)
        if self._node_package_dir(workspace) and not any(
            (workspace / marker).exists()
            for marker in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
        ):
            return "node"
        if configured in _PYTHON_LANGUAGE_ALIASES:
            return "python"
        if self._has_python_files(workspace):
            return "python"
        return configured

    def _normalize_language(self, language: str) -> str:
        return language.strip().lower().replace("-", "").replace("_", "")

    def _has_python_files(self, workspace: Path) -> bool:
        python_markers = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
        if any((workspace / marker).exists() for marker in python_markers):
            return True
        return any(path.suffix == ".py" for path in workspace.glob("*.py"))

    def _node_package_dir(self, workspace: Path) -> Path | None:
        for candidate in (workspace, workspace / "frontend"):
            if (candidate / "package.json").exists():
                return candidate
        return None

    def _package_json(self, package_dir: Path) -> dict[str, object]:
        try:
            data = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    async def _run_pytest(self, workspace_path: str) -> GateResult:
        src_path = Path(workspace_path) / "src"
        pythonpath_parts = []
        if src_path.exists():
            pythonpath_parts.append(str(src_path))
        if os.environ.get("PYTHONPATH"):
            pythonpath_parts.append(os.environ["PYTHONPATH"])

        proc = await asyncio.create_subprocess_exec(
            "pytest",
            "--tb=short",
            "-q",
            "--no-header",
            cwd=workspace_path,
            env={
                **os.environ,
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONPATH": os.pathsep.join(pythonpath_parts),
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode() + stderr.decode()

        # Parse coverage if available
        coverage_pct = None
        try:
            import pathlib

            cov_file = pathlib.Path(workspace_path) / "coverage.json"
            if cov_file.exists():
                cov_data = json.loads(cov_file.read_text())
                coverage_pct = cov_data.get("totals", {}).get("percent_covered", 0)
        except (json.JSONDecodeError, OSError):
            pass

        passed = proc.returncode == 0
        status = GateStatus.PASS if passed else GateStatus.FAIL

        # Warn if coverage below threshold
        if passed and coverage_pct is not None and coverage_pct < self.coverage_threshold:
            status = GateStatus.WARN

        return GateResult(
            gate_name=self.name,
            status=status,
            evidence={
                "output": output[:3000],
                "coverage_pct": coverage_pct,
                "tool": "pytest",
                "testing_doc_id": self.testing_doc_id,
            },
        )

    async def _run_jest(self, workspace_path: str) -> GateResult:
        proc = await asyncio.create_subprocess_exec(
            "npx",
            "jest",
            "--forceExit",
            "--json",
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        try:
            results = json.loads(stdout.decode()) if stdout else {}
            passed = results.get("success", False)
            num_tests = results.get("numTotalTests", 0)
            num_failed = results.get("numFailedTests", 0)
        except json.JSONDecodeError:
            passed = proc.returncode == 0
            num_tests = 0
            num_failed = 0

        status = GateStatus.PASS if passed else GateStatus.FAIL
        return GateResult(
            gate_name=self.name,
            status=status,
            findings_count=num_failed,
            evidence={
                "num_tests": num_tests,
                "num_failed": num_failed,
                "tool": "jest",
                "testing_doc_id": self.testing_doc_id,
            },
        )

    async def _run_node_tests(self, workspace_path: str) -> GateResult:
        workspace = Path(workspace_path)
        package_dir = self._node_package_dir(workspace)
        if not package_dir:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                error_code="PACKAGE_JSON_NOT_FOUND",
                evidence={"tool": "npm", "workspace": str(workspace)},
            )

        package = self._package_json(package_dir)
        scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
        if "test" not in scripts:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                findings_count=1,
                error_code="NO_TEST_SCRIPT",
                evidence={
                    "tool": "npm",
                    "package_dir": str(package_dir),
                    "scripts": sorted(scripts),
                    "testing_doc_id": self.testing_doc_id,
                },
            )

        if not (package_dir / "node_modules").exists():
            install = await asyncio.create_subprocess_exec(
                "npm",
                "install",
                cwd=str(package_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await install.communicate()

        proc = await asyncio.create_subprocess_exec(
            "npm",
            "test",
            cwd=str(package_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
        status = GateStatus.PASS if proc.returncode == 0 else GateStatus.FAIL
        return GateResult(
            gate_name=self.name,
            status=status,
            findings_count=0 if proc.returncode == 0 else 1,
            error_code=None if proc.returncode == 0 else "TESTS_FAILED",
            evidence={
                "output": output[:3000],
                "tool": "npm",
                "command": "npm test",
                "package_dir": str(package_dir),
                "testing_doc_id": self.testing_doc_id,
            },
        )

    async def _run_maven_test(self, workspace_path: str) -> GateResult:
        proc = await asyncio.create_subprocess_exec(
            "mvn",
            "test",
            "-q",
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode() + stderr.decode()

        status = GateStatus.PASS if proc.returncode == 0 else GateStatus.FAIL
        return GateResult(
            gate_name=self.name,
            status=status,
            evidence={
                "output": output[:3000],
                "tool": "maven-surefire",
                "testing_doc_id": self.testing_doc_id,
            },
        )
