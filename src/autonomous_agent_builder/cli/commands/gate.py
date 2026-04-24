"""Local quality-gate surface for builder CLI contracts."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import EXIT_FAILURE, EXIT_SUCCESS
from autonomous_agent_builder.cli.output import emit_error, render
from autonomous_agent_builder.cli.quality_gates import QualityGateError, get_quality_gate_contract, list_quality_gate_contracts


def _gate_contract_payload(surface: str) -> dict[str, object]:
    return get_quality_gate_contract(surface).to_payload()


def _render_contract(data: dict[str, object], *, use_json: bool) -> None:
    def fmt(contract_data: dict[str, object]) -> str:
        lines = [
            str(contract_data["title"]),
            "",
            str(contract_data["summary"]),
            "",
            "Commands:",
            *[f"- {cmd}" for cmd in contract_data["commands"]],
            "",
            "Expectations:",
            *[f"- {item}" for item in contract_data["expectations"]],
        ]
        return "\n".join(lines)

    render(data, fmt, use_json=use_json)


def quality_gate_command(
    surface: str | None = typer.Argument(
        None,
        help="Optional quality-gate surface. Omit to list available surfaces.",
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List local quality-gate surfaces or show one contract."""
    if not surface:
        try:
            contracts = list_quality_gate_contracts()
        except QualityGateError as exc:
            emit_error(
                "quality-gate docs are malformed",
                code="invalid_quality_gate_doc",
                hint="Fix the malformed file under docs/quality-gate/ before using builder quality-gate.",
                detail=str(exc),
                use_json=json,
            )
            sys.exit(EXIT_FAILURE)
        surfaces = [
            {
                "surface": contract.surface,
                "title": contract.title,
                "summary": contract.summary,
            }
            for contract in contracts
        ]
        payload = {
            "status": "ok",
            "count": len(surfaces),
            "surfaces": surfaces,
            "next_step": "builder quality-gate <surface> --json",
            "schema_version": "1",
        }

        def fmt(data: dict[str, object]) -> str:
            lines = ["Available quality gates:", ""]
            for item in data["surfaces"]:
                lines.append(f"- {item['surface']}: {item['summary']}")
            lines.extend(["", f"next: {data['next_step']}"])
            return "\n".join(lines)

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)

    try:
        data = _gate_contract_payload(surface)
    except QualityGateError as exc:
        emit_error(
            "quality-gate lookup failed",
            code="invalid_quality_gate_surface",
            hint="Run `builder quality-gate --json` to list valid surfaces or fix malformed docs under docs/quality-gate/.",
            detail=str(exc),
            use_json=json,
        )
        sys.exit(EXIT_FAILURE)
    _render_contract(data, use_json=json)
    sys.exit(EXIT_SUCCESS)
