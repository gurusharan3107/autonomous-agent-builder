"""Tests for CLI output module — formatting, truncation, TTY detection."""

from __future__ import annotations

import json

from autonomous_agent_builder.cli.output import emit_error, extract_next_command, format_status, normalize_json_payload, table, truncate


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", 100) == "hello"

    def test_exact_limit_unchanged(self):
        text = "a" * 50
        assert truncate(text, 50) == text

    def test_over_limit_truncated(self):
        text = "a" * 100
        result = truncate(text, 50)
        assert len(result) > 50  # includes marker
        assert "truncated" in result
        assert "--full" in result

    def test_default_limit_2000(self):
        text = "a" * 3000
        result = truncate(text)
        assert result.startswith("a" * 2000)
        assert "truncated" in result


class TestTable:
    def test_empty_rows(self):
        assert table(["A", "B"], []) == "(no results)"

    def test_basic_table(self):
        result = table(["NAME", "AGE"], [["Alice", "30"], ["Bob", "25"]])
        lines = result.split("\n")
        assert len(lines) == 4  # header + separator + 2 rows
        assert "NAME" in lines[0]
        assert "Alice" in lines[2]

    def test_max_col_width(self):
        long_text = "a" * 100
        result = table(["COL"], [[long_text]], max_col_width=20)
        # Long text should be truncated with ...
        assert "..." in result


class TestFormatStatus:
    def test_basic(self):
        assert format_status("pending") == "PENDING"

    def test_underscore_replaced(self):
        assert format_status("quality_gates") == "QUALITY GATES"

    def test_capability_limit(self):
        assert format_status("capability_limit") == "CAPABILITY LIMIT"


class TestCompactMachineFields:
    def test_extract_next_command(self):
        assert extract_next_command("Run 'builder start' to start the local dashboard and API.") == "builder start"

    def test_emit_error_json_uses_compact_fields(self, capsys):
        emit_error(
            "cannot connect to server at http://127.0.0.1:9876",
            code="connectivity_error",
            hint="Run 'builder start' to start the local dashboard and API.",
            use_json=True,
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert payload["exit_code"] == 3
        assert payload["next"] == "builder start"
        assert payload["error"]["hint"] == "builder start"

    def test_normalize_json_payload_adds_agent_contract_fields(self):
        payload = normalize_json_payload({"status": "ok", "items": [{"id": "one"}], "next_step": "builder map --json"})

        assert payload["ok"] is True
        assert payload["exit_code"] == 0
        assert payload["schema_version"] == "1"
        assert payload["next"] == "builder map --json"
        assert payload["token_estimate"] > 0
        assert payload["truncated"] is False

    def test_emit_error_json_redacts_raw_internals(self, capsys):
        emit_error(
            "Traceback (most recent call last): secret",
            code="internal_error",
            hint="Run 'builder doctor --json'",
            detail={"response": "<html>server error</html>", "token": "api_key=abc123"},
            use_json=True,
        )

        payload = json.loads(capsys.readouterr().out)
        serialized = json.dumps(payload)
        assert "Traceback" not in serialized
        assert "<html>" not in serialized
        assert "abc123" not in serialized
        assert payload["code"] == "internal_error"
