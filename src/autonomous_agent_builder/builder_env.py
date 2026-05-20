"""Builder-owned environment helpers.

Generated application workspaces must not own Autonomous Agent Builder secrets
or runtime configuration. Those values live in the builder source checkout.
"""

from __future__ import annotations

import os
from pathlib import Path


def builder_source_root() -> Path:
    """Return the autonomous-agent-builder source checkout root."""

    return Path(__file__).resolve().parents[2]


def builder_source_env_path() -> Path:
    """Return the Builder source `.env` path.

    Tests may override this with `AAB_BUILDER_SOURCE_ENV`; product code should
    otherwise use the source checkout `.env`.
    """

    override = os.environ.get("AAB_BUILDER_SOURCE_ENV")
    return Path(override).expanduser().resolve() if override else builder_source_root() / ".env"


def parse_simple_env(path: Path) -> dict[str, str]:
    """Parse a dotenv-style file without expansion or interpolation."""

    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def builder_source_env() -> dict[str, str]:
    """Read Builder-owned secrets/configuration from the source `.env`."""

    return parse_simple_env(builder_source_env_path())
