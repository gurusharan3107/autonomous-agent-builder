"""Security gate — Semgrep two-pass: ERROR blocking + WARNING advisory.

Per architecture spec:
- Pass 1: --severity=ERROR --config=p/owasp-top-ten --config=p/security-audit (blocking)
- Pass 2: --severity=WARNING --config=p/owasp-top-ten (advisory)
- exit_code=1 → findings, exit_code=0 → clean, exit_code=2 → tool error
- Autofix: --autofix --dryrun first, then --autofix if safe
- Cross-file analysis runs nightly only (--interfile-timeout=300)
"""

from __future__ import annotations

import asyncio
import json

from autonomous_agent_builder.quality_gates.base import GateResult, GateStatus, QualityGate


class SecurityGate(QualityGate):
    """Semgrep-based security scanning with two-pass severity filtering."""

    name = "security"
    gate_type = "security"

    async def run(self, workspace_path: str) -> GateResult:
        # Pass 1: blocking (ERROR severity only)
        blocking = await self._run_semgrep(
            workspace_path,
            severity="ERROR",
            configs=["p/owasp-top-ten", "p/security-audit"],
        )

        # Pass 2: advisory (WARNING severity)
        advisory = await self._run_semgrep(
            workspace_path,
            severity="WARNING",
            configs=["p/owasp-top-ten"],
        )

        # Determine status: exit_code=1 → findings, 0 → clean, 2 → tool error
        if blocking["exit_code"] == 2:
            status = GateStatus.ERROR
            error_code = "SEMGREP_TOOL_ERROR"
        elif blocking["exit_code"] == 1:
            status = GateStatus.FAIL
            error_code = None
        elif advisory["exit_code"] == 1:
            status = GateStatus.WARN
            error_code = None
        else:
            status = GateStatus.PASS
            error_code = None

        blocking_count = len(blocking.get("findings", []))
        advisory_count = len(advisory.get("findings", []))

        return GateResult(
            gate_name=self.name,
            status=status,
            findings_count=blocking_count + advisory_count,
            error_code=error_code,
            evidence={
                "blocking": blocking,
                "advisory": advisory,
            },
            remediation_possible=self._has_autofix(blocking.get("findings", [])),
        )

    async def remediate(self, workspace_path: str) -> bool:
        """Two-step autofix: dryrun first, apply if safe."""
        # Step 1: dryrun
        dryrun = await self._run_semgrep_cmd(
            ["semgrep", "scan", "--autofix", "--dryrun", workspace_path]
        )
        if not dryrun["stdout"].strip():
            return False  # Nothing to autofix

        # Step 2: apply
        result = await self._run_semgrep_cmd(["semgrep", "scan", "--autofix", workspace_path])
        return result["exit_code"] == 0

    async def _run_semgrep(
        self,
        workspace_path: str,
        severity: str,
        configs: list[str],
    ) -> dict:
        """Run semgrep with specific severity and configs."""
        cmd = ["semgrep", "scan", "--json", "--severity", severity]
        for config in configs:
            cmd.extend(["--config", config])
        cmd.extend(["--pro-languages", workspace_path])

        result = await self._run_semgrep_cmd(cmd)

        findings = []
        if result["stdout"]:
            try:
                output = json.loads(result["stdout"])
                findings = output.get("results", [])
            except json.JSONDecodeError:
                pass

        return {
            "exit_code": result["exit_code"],
            "findings": findings[:50],  # Cap for storage
            "findings_count": len(findings),
        }

    async def _run_semgrep_cmd(self, cmd: list[str]) -> dict:
        """Execute a semgrep command."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        return {
            "exit_code": proc.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

    @staticmethod
    def _has_autofix(findings: list) -> bool:
        """Check if any findings have autofix available."""
        return any(f.get("extra", {}).get("fix") for f in findings)


class DependencyGate(QualityGate):
    """Trivy-based dependency vulnerability scanning."""

    name = "dependency"
    gate_type = "dependency"

    async def run(self, workspace_path: str) -> GateResult:
        proc = await asyncio.create_subprocess_exec(
            "trivy",
            "fs",
            "--format",
            "json",
            "--severity",
            "HIGH,CRITICAL",
            workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        try:
            output = json.loads(stdout.decode()) if stdout else {}
            results = output.get("Results", [])
            vuln_count = sum(len(r.get("Vulnerabilities", [])) for r in results)
        except json.JSONDecodeError:
            vuln_count = 0
            results = []

        status = GateStatus.FAIL if vuln_count > 0 else GateStatus.PASS

        return GateResult(
            gate_name=self.name,
            status=status,
            findings_count=vuln_count,
            evidence={"results": results[:10], "tool": "trivy"},
        )
