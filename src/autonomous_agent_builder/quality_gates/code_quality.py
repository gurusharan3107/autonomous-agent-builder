"""Code quality gate — Ruff for Python, ESLint for Node.js."""

from __future__ import annotations

import asyncio
import json
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


class CodeQualityGate(QualityGate):
    """Run code linter (Ruff/ESLint) and report findings."""

    name = "code_quality"
    gate_type = "code_quality"

    def __init__(self, language: str = "python"):
        self.language = language

    async def run(self, workspace_path: str) -> GateResult:
        language = self._effective_language(workspace_path)
        if language == "python":
            return await self._run_ruff(workspace_path)
        elif language in ("node", "javascript", "typescript"):
            return await self._run_node_quality(workspace_path)
        elif language == "java":
            return await self._run_checkstyle(workspace_path)
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

    async def _run_command(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, (stdout.decode(errors="replace") + stderr.decode(errors="replace"))

    async def _run_node_quality(self, workspace_path: str) -> GateResult:
        workspace = Path(workspace_path)
        package_dir = self._node_package_dir(workspace)
        if not package_dir:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                error_code="PACKAGE_JSON_NOT_FOUND",
                evidence={"tool": "npm", "workspace": str(workspace)},
                remediation_possible=True,
            )

        package = self._package_json(package_dir)
        scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
        checks: list[dict[str, object]] = []

        if "lint" not in scripts:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                findings_count=1,
                error_code="NO_LINT_SCRIPT",
                evidence={"tool": "npm", "package_dir": str(package_dir), "scripts": sorted(scripts)},
                remediation_possible=True,
            )

        lint_code, lint_output = await self._run_command(["npm", "run", "lint"], package_dir)
        checks.append(
            {
                "command": "npm run lint",
                "exit_code": lint_code,
                "output": lint_output[:3000],
            }
        )
        if lint_code != 0:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                findings_count=1,
                error_code="LINT_FAILED",
                evidence={"tool": "npm", "package_dir": str(package_dir), "checks": checks},
                remediation_possible=True,
            )

        if "build" in scripts:
            build_code, build_output = await self._run_command(["npm", "run", "build"], package_dir)
            checks.append(
                {
                    "command": "npm run build",
                    "exit_code": build_code,
                    "output": build_output[:3000],
                }
            )
            if build_code != 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAIL,
                    findings_count=1,
                    error_code="BUILD_FAILED",
                    evidence={"tool": "npm", "package_dir": str(package_dir), "checks": checks},
                    remediation_possible=True,
                )
        elif (package_dir / "tsconfig.json").exists():
            type_code, type_output = await self._run_command(["npx", "tsc", "--noEmit"], package_dir)
            checks.append(
                {
                    "command": "npx tsc --noEmit",
                    "exit_code": type_code,
                    "output": type_output[:3000],
                }
            )
            if type_code != 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAIL,
                    findings_count=1,
                    error_code="TYPECHECK_FAILED",
                    evidence={"tool": "npm", "package_dir": str(package_dir), "checks": checks},
                    remediation_possible=True,
                )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            evidence={"tool": "npm", "package_dir": str(package_dir), "checks": checks},
            remediation_possible=True,
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
        language = self._effective_language(workspace_path)
        if language == "python":
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
        elif language in ("node", "javascript", "typescript"):
            package_dir = self._node_package_dir(Path(workspace_path)) or Path(workspace_path)
            proc = await asyncio.create_subprocess_exec(
                "npm",
                "run",
                "lint",
                "--",
                "--fix",
                cwd=str(package_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        return False
