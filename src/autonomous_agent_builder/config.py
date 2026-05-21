"""Application configuration — Pydantic Settings with environment variable support."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings. Supports PostgreSQL (prod) and SQLite (local dev)."""

    model_config = {"env_prefix": "DB_"}

    host: str = "localhost"
    port: int = 5432
    name: str = "agent_builder"
    user: str = "agent_builder"
    password: str = "agent_builder"
    driver: str = "sqlite"  # "postgresql" for prod, "sqlite" for local dev
    url_override: str | None = None  # Direct URL override (set via AAB_DB_URL)

    def _sqlite_target(self) -> str:
        """Return a stable SQLite file target for relative names or absolute paths."""
        name = self.name
        if name.endswith(".db"):
            name = name[:-3]
        path = Path(name)
        if path.is_absolute():
            return str(path.with_suffix(".db"))
        return f"./{name}.db"

    @property
    def url(self) -> str:
        # Check for direct URL override first (used by embedded server)
        if self.url_override:
            return self.url_override

        if self.driver == "sqlite":
            return f"sqlite+aiosqlite:///{self._sqlite_target()}"
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_url(self) -> str:
        # Check for direct URL override first
        if self.url_override:
            # Convert async URL to sync URL
            return self.url_override.replace("+aiosqlite", "").replace("+asyncpg", "")

        if self.driver == "sqlite":
            return f"sqlite:///{self._sqlite_target()}"
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class AgentSettings(BaseSettings):
    """Agent runtime settings."""

    model_config = {"env_prefix": "AGENT_"}

    max_turns: int = 30
    max_budget_usd: float = 5.00
    planning_model: str = "opus"
    design_model: str = "opus"
    implementation_model: str = "sonnet"
    pr_model: str = "sonnet"
    kb_extraction_model: str = "claude-haiku-4-5-20251001"
    kb_validation_model: str = "claude-haiku-4-5-20251001"
    kb_retry_model: str = "claude-haiku-4-5-20251001"
    kb_manual_repair_model: str = "sonnet"
    kb_design_review_model: str = "claude-opus-4-7"
    query_timeout_seconds: int = 300
    # Claude CLI startup on Windows (especially in corporate environments) can
    # take 25-30s before the first token is emitted. The probe only needs a
    # one-token response but must wait for that cold start.
    availability_probe_timeout_seconds: int = 60
    permission_mode: str = "dontAsk"
    auth_backend: str = "auto"


class RuntimeSettings(BaseSettings):
    """Runtime selection settings - modular runtime support.

    User-facing lifecycle SDKs:
    - "claude": Claude Agent SDK with local Claude OAuth token auth.
    - "codex_sdk": Codex app-server/SDK path through Codex CLI login auth.

    Compatibility adapters may exist in lower-level runtime code, but sprint
    validation and dashboard runtime switching should use only "claude" and
    "codex_sdk".

    Legacy aliases may be normalized by lower-level runtime code, but they are
    not valid user-facing runtime selections.
    """

    model_config = SettingsConfigDict(env_prefix="RUNTIME_", env_file=".env", extra="ignore")

    # Which harness powers the agent runtime.
    sdk: str = "claude"  # User-facing: "claude" | "codex_sdk"

    # Provider inside the selected SDK. Defaults are resolved by runtime factory.
    provider: str | None = None

    # Backward-compatible legacy name. New code should use provider.
    subscription: str | None = None

    # Model identifier in the selected harness.
    # Claude Agent SDK default: local Claude Code model alias.
    # Codex SDK examples: "gpt-5.5", "gpt-5.4"
    model: str = "sonnet"

    # API-backed provider settings. Not used by claude or Codex subscription modes.
    api_base_url: str | None = None
    api_key_env: str | None = None

    # Codex CLI profile name. Optional; omitted when unset.
    codex_profile: str | None = None

    # Codex CLI process controls.
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "never"

    # Runtime tracing policy: "off" | "builder" | provider-specific values.
    tracing: str = "builder"

    # Connection mode: "online" or "offline" (local only)
    mode: str = "online"

    # Cost/speed preference
    preference: str = "balanced"  # "speed" | "balanced" | "quality"


class GateSettings(BaseSettings):
    """Quality gate settings."""

    model_config = {"env_prefix": "GATE_"}

    max_retries: int = 2
    retry_backoff: list[int] = Field(default=[30, 90])
    code_quality_timeout: int = 30
    testing_timeout: int = 120
    security_timeout: int = 60
    dependency_timeout: int = 45


class HarnessSettings(BaseSettings):
    """Harnessability scoring settings."""

    model_config = {"env_prefix": "HARNESS_"}

    reject_threshold: int = 3
    review_threshold: int = 5


class Settings(BaseSettings):
    """Root settings — aggregates all sub-settings."""

    model_config = SettingsConfigDict(env_prefix="AAB_", env_file=".env", extra="ignore")

    app_name: str = "Autonomous Agent Builder"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    workspace_root: str = Field(
        default_factory=lambda: str(Path(tempfile.gettempdir()) / "aab-workspaces")
    )
    kb_blocking_docs: list[str] = Field(
        default_factory=lambda: [
            "system-architecture",
            "dependencies",
            "technology-stack",
        ]
    )

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    gate: GateSettings = Field(default_factory=GateSettings)
    harness: HarnessSettings = Field(default_factory=HarnessSettings)


def get_settings() -> Settings:
    """Factory for settings singleton."""
    return Settings()
