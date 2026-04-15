"""Application configuration — Pydantic Settings with environment variable support."""

from __future__ import annotations

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

    @property
    def url(self) -> str:
        if self.driver == "sqlite":
            return f"sqlite+aiosqlite:///./{self.name}.db"
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_url(self) -> str:
        if self.driver == "sqlite":
            return f"sqlite:///./{self.name}.db"
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
    permission_mode: str = "dontAsk"


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
    workspace_root: str = "/tmp/aab-workspaces"

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    gate: GateSettings = Field(default_factory=GateSettings)
    harness: HarnessSettings = Field(default_factory=HarnessSettings)


def get_settings() -> Settings:
    """Factory for settings singleton."""
    return Settings()
