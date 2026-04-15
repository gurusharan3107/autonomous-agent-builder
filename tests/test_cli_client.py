"""Tests for CLI HTTP client — error mapping, exit codes."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.cli.client import (
    EXIT_FAILURE,
    EXIT_INVALID_USAGE,
    AabApiError,
    handle_api_error,
)


class TestAabApiError:
    def test_error_message(self):
        err = AabApiError(404, {"detail": "not found"})
        assert "404" in str(err)
        assert err.status_code == 404

    def test_string_detail(self):
        err = AabApiError(500, "server error")
        assert err.detail == "server error"


class TestHandleApiError:
    def test_404_exits_failure(self):
        err = AabApiError(404, {"detail": "Task not found"})
        with pytest.raises(SystemExit) as exc_info:
            handle_api_error(err)
        assert exc_info.value.code == EXIT_FAILURE

    def test_422_exits_invalid_usage(self):
        err = AabApiError(422, {"detail": "Validation error"})
        with pytest.raises(SystemExit) as exc_info:
            handle_api_error(err)
        assert exc_info.value.code == EXIT_INVALID_USAGE

    def test_500_exits_failure(self):
        err = AabApiError(500, "Internal server error")
        with pytest.raises(SystemExit) as exc_info:
            handle_api_error(err)
        assert exc_info.value.code == EXIT_FAILURE
