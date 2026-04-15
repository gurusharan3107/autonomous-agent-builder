"""Testing gate — pytest for Python, Jest for Node.js, JUnit for Java."""

from __future__ import annotations

import asyncio
import json

from autonomous_agent_builder.quality_gates.base import GateResult, GateStatus, QualityGate


class TestingGate(QualityGate):
    """Run project test suite and report results."""

    name = "testing"
    gate_type = "testing"

    def __init__(self, language: str = "python", coverage_threshold: int = 80):
        self.language = language
        self.coverage_threshold = coverage_threshold

    async def run(self, workspace_path: str) -> GateResult:
        if self.language == "python":
            return await self._run_pytest(workspace_path)
        elif self.language in ("node", "javascript", "typescript"):
            return await self._run_jest(workspace_path)
        elif self.language == "java":
            return await self._run_maven_test(workspace_path)
        else:
            return GateResult(
                gate_name=self.name, status=GateStatus.WARN, error_code="UNSUPPORTED_LANGUAGE"
            )

    async def _run_pytest(self, workspace_path: str) -> GateResult:
        proc = await asyncio.create_subprocess_exec(
            "pytest",
            "--tb=short",
            "-q",
            "--no-header",
            f"--cov={workspace_path}",
            "--cov-report=json",
            cwd=workspace_path,
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
            evidence={"num_tests": num_tests, "num_failed": num_failed, "tool": "jest"},
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
            evidence={"output": output[:3000], "tool": "maven-surefire"},
        )
