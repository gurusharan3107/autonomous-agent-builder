"""Tests for quality gate framework — concurrent execution + AND aggregation."""

from __future__ import annotations

import asyncio

import pytest

from autonomous_agent_builder.quality_gates.base import (
    AggregateGateResult,
    GateResult,
    GateStatus,
    QualityGate,
    _run_with_timeout,
    run_quality_gates,
)


class PassingGate(QualityGate):
    name = "pass_gate"
    gate_type = "code_quality"

    async def run(self, workspace_path: str) -> GateResult:
        return GateResult(gate_name=self.name, status=GateStatus.PASS)


class FailingGate(QualityGate):
    name = "fail_gate"
    gate_type = "testing"

    async def run(self, workspace_path: str) -> GateResult:
        return GateResult(
            gate_name=self.name,
            status=GateStatus.FAIL,
            findings_count=3,
            remediation_possible=True,
        )


class WarningGate(QualityGate):
    name = "warn_gate"
    gate_type = "code_quality"

    async def run(self, workspace_path: str) -> GateResult:
        return GateResult(gate_name=self.name, status=GateStatus.WARN, findings_count=1)


class SlowGate(QualityGate):
    name = "slow_gate"
    gate_type = "testing"

    async def run(self, workspace_path: str) -> GateResult:
        await asyncio.sleep(10)
        return GateResult(gate_name=self.name, status=GateStatus.PASS)


class TestGateConcurrency:
    @pytest.mark.asyncio
    async def test_all_pass(self):
        result = await run_quality_gates("/tmp", [PassingGate(), PassingGate()])
        assert result.status == GateStatus.PASS
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_one_fail_overall_fail(self):
        result = await run_quality_gates("/tmp", [PassingGate(), FailingGate()])
        assert result.status == GateStatus.FAIL
        assert len(result.failed_gates) == 1

    @pytest.mark.asyncio
    async def test_warning_propagates(self):
        result = await run_quality_gates("/tmp", [PassingGate(), WarningGate()])
        assert result.status == GateStatus.WARN

    @pytest.mark.asyncio
    async def test_post_gates_skipped_on_pre_fail(self):
        result = await run_quality_gates(
            "/tmp",
            pre_gates=[FailingGate()],
            post_gates=[PassingGate()],
        )
        assert result.status == GateStatus.FAIL
        assert len(result.results) == 1  # Only pre-gate ran

    @pytest.mark.asyncio
    async def test_post_gates_run_on_pre_pass(self):
        result = await run_quality_gates(
            "/tmp",
            pre_gates=[PassingGate()],
            post_gates=[PassingGate()],
        )
        assert result.status == GateStatus.PASS
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_timeout_treated_as_fail(self):
        result = await _run_with_timeout(SlowGate(), "/tmp", timeout=1)
        assert result.status == GateStatus.TIMEOUT
        assert result.timeout is True
        assert result.error_code == "DEADLINE_EXCEEDED"

    @pytest.mark.asyncio
    async def test_remediable_gates(self):
        result = await run_quality_gates("/tmp", [FailingGate()])
        assert len(result.remediable_gates) == 1


class TestGateResult:
    def test_aggregate_failed_gates(self):
        results = [
            GateResult(gate_name="a", status=GateStatus.PASS),
            GateResult(gate_name="b", status=GateStatus.FAIL),
            GateResult(gate_name="c", status=GateStatus.TIMEOUT, timeout=True),
        ]
        agg = AggregateGateResult(status=GateStatus.FAIL, results=results)
        assert len(agg.failed_gates) == 2
        assert len(agg.warning_gates) == 0
