"""Builder logs observability coverage CLI surface regressions."""

from __future__ import annotations

from autonomous_agent_builder.cli.commands import logs as logs_module


def test_observability_coverage_flags_placeholder_otlp_endpoint():
    coverage = logs_module._observability_coverage(
        [
            {
                "tools": [],
                "observability": {
                    "source": "runtime_env",
                    "enabled": True,
                    "metrics_exporter": "otlp",
                    "logs_exporter": "otlp",
                    "traces_exporter": "otlp",
                    "endpoint_configured": False,
                    "endpoint_placeholder": True,
                    "signal_state": {"metrics": True, "logs": True, "traces": True},
                },
            }
        ]
    )

    assert coverage["otel"]["endpoint_configured"] is False
    assert coverage["otel"]["endpoint_placeholder"] is True
    assert "otel_otlp_endpoint" in coverage["missing_signals"]
    assert coverage["next"] == (
        "Configure a real OTLP collector endpoint before treating exported telemetry as usable."
    )


def test_observability_coverage_flags_unreachable_local_otel_collector():
    coverage = logs_module._observability_coverage(
        [
            {
                "tools": [],
                "observability": {
                    "source": "runtime_env",
                    "enabled": True,
                    "metrics_exporter": "otlp",
                    "logs_exporter": "otlp",
                    "traces_exporter": "otlp",
                    "endpoint_configured": True,
                    "endpoint_placeholder": False,
                    "collector": {
                        "configured": True,
                        "local": True,
                        "checked": True,
                        "reachable": False,
                        "status": "configured_unreachable",
                        "endpoint": "http://localhost:4318",
                        "error": "ConnectionRefusedError",
                    },
                    "signal_state": {"metrics": True, "logs": True, "traces": True},
                },
            }
        ]
    )

    assert coverage["otel"]["endpoint_configured"] is True
    assert coverage["otel"]["collector_reachable"] is False
    assert "otel_collector_unreachable" in coverage["missing_signals"]
    assert coverage["next"] == (
        "Start the local OTEL collector or change AAB_CLAUDE_OTEL_ENDPOINT; "
        "telemetry is configured but exports are not reachable."
    )


def test_observability_coverage_uses_codex_runtime_guidance(monkeypatch):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    monkeypatch.setenv("RUNTIME_MODEL", "gpt-5.5")

    coverage = logs_module._observability_coverage([{"tools": []}])

    assert coverage["source"] == "codex_app_server"
    assert coverage["runtime_sdk"] == "codex_sdk"
    assert coverage["missing_signals"] == ["codex_runtime_usage"]
    assert coverage["next"] == (
        "Run a Codex-backed chat or task dispatch; builder will normalize "
        "Codex runtime usage events into tokens, turns, and duration."
    )
