"""Environment boundary for Codex subscription-auth runtime processes."""

from __future__ import annotations

import os

CODEX_RUNTIME_BLOCKED_API_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_ORG_ID",
    "OPENAI_ORGANIZATION",
    "OPENAI_PROJECT",
)


def codex_subscription_env() -> dict[str, str]:
    """Return a child-process env that cannot use OpenAI API-key auth.

    Codex SDK/CLI lanes are powered by the user's ChatGPT/Codex subscription
    login, not by the project `OPENAI_API_KEY` used for Realtime voice. Builder
    runtime configuration is loaded from the autonomous-builder source `.env`,
    so Codex child processes must explicitly drop OpenAI API env vars before
    launch.
    """

    env = dict(os.environ)
    for key in CODEX_RUNTIME_BLOCKED_API_ENV_KEYS:
        env.pop(key, None)
    env["AAB_CODEX_AUTH_SOURCE"] = "chatgpt_subscription"
    return env
