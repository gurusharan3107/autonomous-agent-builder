"""Tests for CLI HTTP client — error mapping, exit codes, and base URL resolution."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.cli.client import (
    EXIT_FAILURE,
    EXIT_INVALID_USAGE,
    AabApiError,
    handle_api_error,
    resolve_base_url,
)


class TestAabApiError:
    def test_error_message(self) -> None:
        err = AabApiError(404, {"detail": "not found"})
        assert "404" in str(err)
        assert err.status_code == 404

    def test_string_detail(self) -> None:
        err = AabApiError(500, "server error")
        assert err.detail == "server error"


class TestHandleApiError:
    def test_404_exits_failure(self) -> None:
        err = AabApiError(404, {"detail": "Task not found"})
        with pytest.raises(SystemExit) as exc_info:
            handle_api_error(err)
        assert exc_info.value.code == EXIT_FAILURE

    def test_422_exits_invalid_usage(self) -> None:
        err = AabApiError(422, {"detail": "Validation error"})
        with pytest.raises(SystemExit) as exc_info:
            handle_api_error(err)
        assert exc_info.value.code == EXIT_INVALID_USAGE

    def test_500_exits_failure(self) -> None:
        err = AabApiError(500, "Internal server error")
        with pytest.raises(SystemExit) as exc_info:
            handle_api_error(err)
        assert exc_info.value.code == EXIT_FAILURE


class TestResolveBaseUrl:
    def test_prefers_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.setenv("AAB_API_URL", "http://127.0.0.1:9999")
        monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))

        assert resolve_base_url() == "http://127.0.0.1:9999"

    def test_uses_repo_local_port(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("AAB_API_URL", raising=False)
        monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
        agent_builder_dir = tmp_path / ".agent-builder"
        agent_builder_dir.mkdir()
        (agent_builder_dir / "server.port").write_text("9876", encoding="utf-8")

        assert resolve_base_url() == "http://127.0.0.1:9876"

    def test_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("AAB_API_URL", raising=False)
        monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))

        assert resolve_base_url() == "http://localhost:8000"
