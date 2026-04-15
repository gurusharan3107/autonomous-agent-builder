"""Main entry point — run the application server."""

from __future__ import annotations

import uvicorn
from dotenv import load_dotenv

# Load .env before anything else — CLAUDE_CODE_OAUTH_TOKEN must be in os.environ
# so the Claude Agent SDK subprocess (claude CLI) inherits it for auth.
load_dotenv()

from autonomous_agent_builder.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "autonomous_agent_builder.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
