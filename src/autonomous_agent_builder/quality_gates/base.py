"""Quality gate framework — ABC + concurrent execution + AND aggregation.

Gates run with asyncio.gather() and per-gate timeouts. One FAIL = overall FAIL.
Tiered scheduling: pre-integration (every commit), post-integration (after pre passes),
nightly (architecture deep scan).
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

from autonomous_agent_builder.config import get_settings

log = structlog.get_logger()


class GateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class GateResult:
    """Result from a single quality gate execution."""

    gate_name: str
    status: GateStatus
    findings_count: int = 0
    elapsed_ms: int = 0
    error_code: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    remediation_possible: bool = False
    timeout: bool = False


@dataclass
class AggregateGateResult:
    """Aggregated result from multiple concurrent gates."""

    status: GateStatus
    results: list[GateResult]

    @property
    def failed_gates(self) -> list[GateResult]:
        return [r for r in self.results if r.status in (GateStatus.FAIL, GateStatus.TIMEOUT)]

    @property
    def warning_gates(self) -> list[GateResult]:
        return [r for r in self.results if r.status == GateStatus.WARN]

    @property
    def remediable_gates(self) -> list[GateResult]:
        return [r for r in self.failed_gates if r.remediation_possible]


class QualityGate(ABC):
    """Abstract base class for all quality gates."""

    name: str
    gate_type: str  # code_quality, security, testing, dependency

    @abstractmethod
    async def run(self, workspace_path: str) -> GateResult:
        """Execute the gate check against the workspace."""

    async def remediate(self, workspace_path: str) -> bool:
        """Attempt auto-remediation. Returns True if fixed."""
        return False


async def _run_with_timeout(gate: QualityGate, workspace_path: str, timeout: int) -> GateResult:
    """Run a single gate with timeout protection."""
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(gate.run(workspace_path), timeout=timeout)
        result.elapsed_ms = int((time.monotonic() - start) * 1000)
        return result
    except TimeoutError:
        elapsed = int((time.monotonic() - start) * 1000)
        log.warning("gate_timeout", gate=gate.name, timeout=timeout, elapsed_ms=elapsed)
        return GateResult(
            gate_name=gate.name,
            status=GateStatus.TIMEOUT,
            elapsed_ms=elapsed,
            error_code="DEADLINE_EXCEEDED",
            timeout=True,
        )
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        log.error("gate_error", gate=gate.name, error=str(e))
        return GateResult(
            gate_name=gate.name,
            status=GateStatus.ERROR,
            elapsed_ms=elapsed,
            error_code=type(e).__name__,
        )


async def run_quality_gates(
    workspace_path: str,
    pre_gates: list[QualityGate],
    post_gates: list[QualityGate] | None = None,
) -> AggregateGateResult:
    """Run quality gates concurrently with AND aggregation.

    Pre-integration gates run first. Post-integration gates only run
    if all pre-integration gates pass.
    """
    settings = get_settings()

    # Gate timeout mapping
    timeouts = {
        "code_quality": settings.gate.code_quality_timeout,
        "testing": settings.gate.testing_timeout,
        "security": settings.gate.security_timeout,
        "dependency": settings.gate.dependency_timeout,
    }

    # Run pre-integration gates concurrently
    log.info("gates_pre_integration_start", gates=[g.name for g in pre_gates])
    pre_results = await asyncio.gather(
        *[
            _run_with_timeout(gate, workspace_path, timeouts.get(gate.gate_type, 60))
            for gate in pre_gates
        ]
    )

    # Log per-gate results (structured — gate-level trace spec)
    for r in pre_results:
        log.info(
            "gate_result",
            gate=r.gate_name,
            status=r.status.value,
            elapsed_ms=r.elapsed_ms,
            error_code=r.error_code,
            findings_count=r.findings_count,
        )

    # AND aggregation: any FAIL or TIMEOUT in pre = overall FAIL, skip post
    if any(r.status in (GateStatus.FAIL, GateStatus.TIMEOUT) for r in pre_results):
        return AggregateGateResult(status=GateStatus.FAIL, results=list(pre_results))

    # Run post-integration gates if pre passed
    all_results = list(pre_results)
    if post_gates:
        log.info("gates_post_integration_start", gates=[g.name for g in post_gates])
        post_results = await asyncio.gather(
            *[
                _run_with_timeout(gate, workspace_path, timeouts.get(gate.gate_type, 60))
                for gate in post_gates
            ]
        )
        for r in post_results:
            log.info(
                "gate_result",
                gate=r.gate_name,
                status=r.status.value,
                elapsed_ms=r.elapsed_ms,
                error_code=r.error_code,
                findings_count=r.findings_count,
            )
        all_results.extend(post_results)

    # Final aggregation
    if any(r.status in (GateStatus.FAIL, GateStatus.TIMEOUT) for r in all_results):
        return AggregateGateResult(status=GateStatus.FAIL, results=all_results)
    if any(r.status == GateStatus.WARN for r in all_results):
        return AggregateGateResult(status=GateStatus.WARN, results=all_results)
    return AggregateGateResult(status=GateStatus.PASS, results=all_results)
