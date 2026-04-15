"""Code quality gate — Ruff for Python, ESLint for Node.js."""

from __future__ import annotations

import asyncio
import json

from autonomous_agent_builder.quality_gates.base import GateResult, GateStatus, QualityGate


class CodeQualityGate(QualityGate):
    """Run code linter (Ruff/ESLint) and report findings."""

    name = "code_quality"
    gate_type = "code_quality"

    def __init__(self, language: str = "python"):
        self.language = language

    async def run(self, workspace_path: str) -> GateResult:
        if self.language == "python":
            return await self._run_ruff(workspace_path)
        elif self.language in ("node", "javascript", "typescript"):
            return await self._run_eslint(workspace_path)
        elif self.language == "java":
            return await self._run_checkstyle(workspace_path)
        else:
            return GateResult(
                gate_name=self.name, status=GateStatus.WARN, error_code="UNSUPPORTED_LANGUAGE"
            )

    async def _run_ruff(self, workspace_path: str) -> GateResult:
        proc = await asyncio.create_subprocess_exec(
            "ruff",
            "check",
            "--output-format=json",
            workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        try:
            findings = json.loads(stdout.decode()) if stdout else []
        except json.JSONDecodeError:
            findings = []

        count = len(findings) if isinstance(findings, list) else 0
        status = GateStatus.FAIL if proc.returncode == 1 else GateStatus.PASS

        return GateResult(
            gate_name=self.name,
            status=status,
            findings_count=count,
            evidence={"findings": findings[:20], "tool": "ruff"},
            remediation_possible=True,
        )

    async def _run_eslint(self, workspace_path: str) -> GateResult:
        proc = await asyncio.create_subprocess_exec(
            "npx",
            "eslint",
            "--format=json",
            workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        try:
            results = json.loads(stdout.decode()) if stdout else []
            count = sum(r.get("errorCount", 0) for r in results)
        except json.JSONDecodeError:
            count = 0
            results = []

        status = GateStatus.FAIL if count > 0 else GateStatus.PASS
        return GateResult(
            gate_name=self.name,
            status=status,
            findings_count=count,
            evidence={"findings": results[:10], "tool": "eslint"},
            remediation_possible=True,
        )

    async def _run_checkstyle(self, workspace_path: str) -> GateResult:
        # Java: Checkstyle via Maven
        proc = await asyncio.create_subprocess_exec(
            "mvn",
            "checkstyle:check",
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
            evidence={"output": output[:2000], "tool": "checkstyle"},
        )

    async def remediate(self, workspace_path: str) -> bool:
        """Auto-fix linting issues."""
        if self.language == "python":
            proc = await asyncio.create_subprocess_exec(
                "ruff",
                "check",
                "--fix",
                workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        elif self.language in ("node", "javascript", "typescript"):
            proc = await asyncio.create_subprocess_exec(
                "npx",
                "eslint",
                "--fix",
                workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        return False
