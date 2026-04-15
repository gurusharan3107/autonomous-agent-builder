"""Tests for CLI output module — formatting, truncation, TTY detection."""

from __future__ import annotations

from autonomous_agent_builder.cli.output import format_status, table, truncate


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
