"""Tests for configuration."""

from __future__ import annotations

from autonomous_agent_builder.config import Settings


class TestConfig:
    def test_default_settings(self):
        settings = Settings()
        assert settings.app_name == "Autonomous Agent Builder"
        assert settings.port == 8000
        assert settings.kb_blocking_docs == [
            "system-architecture",
            "dependencies",
            "technology-stack",
        ]

    def test_agent_defaults(self):
        settings = Settings()
        assert settings.agent.max_turns == 30
        assert settings.agent.max_budget_usd == 5.00
        assert settings.agent.planning_model == "opus"
        assert settings.agent.implementation_model == "sonnet"
        assert settings.agent.kb_extraction_model == "claude-haiku-4-5-20251001"
        assert settings.agent.kb_validation_model == "claude-haiku-4-5-20251001"
        assert settings.agent.kb_retry_model == "claude-haiku-4-5-20251001"
        assert settings.agent.kb_manual_repair_model == "sonnet"
        assert settings.agent.kb_design_review_model == "claude-opus-4-7"
        assert settings.agent.query_timeout_seconds == 300
        assert settings.agent.auth_backend == "auto"

    def test_background_agent_permission_mode_default_is_accept_edits(self):
        # Background (non-interactive) agents fall through to the global default.
        # "acceptEdits" auto-accepts file edits while keeping AskUserQuestion
        # enabled (unlike "dontAsk" which bypasses can_use_tool entirely and
        # silently disabled Edit/Write/Bash tool grants in background agents).
        settings = Settings()
        assert settings.agent.permission_mode == "acceptEdits"

    def test_interactive_chat_lane_overrides_permission_mode_to_default(self):
        # Interactive lanes must remain under "default" so the can_use_tool
        # callback fires for AskUserQuestion cards — they must not regress to
        # the global background setting.
        from autonomous_agent_builder.agents.definitions import get_agent_definition

        assert get_agent_definition("chat").permission_mode == "default"

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
