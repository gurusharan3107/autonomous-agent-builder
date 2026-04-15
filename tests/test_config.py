"""Tests for configuration."""

from __future__ import annotations

from autonomous_agent_builder.config import Settings


class TestConfig:
    def test_default_settings(self):
        settings = Settings()
        assert settings.app_name == "Autonomous Agent Builder"
        assert settings.port == 8000

    def test_agent_defaults(self):
        settings = Settings()
        assert settings.agent.max_turns == 30
        assert settings.agent.max_budget_usd == 5.00
        assert settings.agent.planning_model == "opus"
        assert settings.agent.implementation_model == "sonnet"

    def test_gate_defaults(self):
        settings = Settings()
        assert settings.gate.max_retries == 2
        assert settings.gate.retry_backoff == [30, 90]
        assert settings.gate.code_quality_timeout == 30
        assert settings.gate.testing_timeout == 120

    def test_harness_thresholds(self):
        settings = Settings()
        assert settings.harness.reject_threshold == 3
        assert settings.harness.review_threshold == 5

    def test_db_url_sqlite_default(self):
        settings = Settings()
        assert "sqlite+aiosqlite" in settings.db.url
        assert "agent_builder" in settings.db.url

    def test_db_url_postgresql(self):
        from autonomous_agent_builder.config import DatabaseSettings

        db = DatabaseSettings(driver="postgresql")
        assert "postgresql+asyncpg" in db.url
        assert "agent_builder" in db.url
