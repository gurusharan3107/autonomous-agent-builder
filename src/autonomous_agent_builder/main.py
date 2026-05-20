"""Main entry point — run the application server."""

from __future__ import annotations

from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Load .env before anything else so the Claude Agent SDK child process can
# inherit local auth such as CLAUDE_CODE_OAUTH_TOKEN.
load_dotenv(Path.cwd() / ".env")

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
