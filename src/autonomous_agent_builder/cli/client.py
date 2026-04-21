"""HTTP client for the builder CLI — sync httpx wrapper around the FastAPI backend.

The CLI talks to the running server via HTTP. This keeps business logic in one place
(the server) and avoids duplicating validation, DB access, or orchestration logic.

The server must be running for CLI commands to work. Use `builder server health`
to verify connectivity.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

# Exit codes per CLI contract (clig.dev / POSIX convention)
EXIT_SUCCESS = 0       # success
EXIT_FAILURE = 1       # general / unclassified error
EXIT_INVALID_USAGE = 2  # bad flags, missing args, validation error
EXIT_CONNECTIVITY = 3  # server not reachable, auth failure
EXIT_NOT_FOUND = 4     # resource does not exist


class AabApiError(Exception):
    """API returned a non-2xx response."""

    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


class BuilderClient:
    """Synchronous HTTP client for the autonomous-agent-builder API.

    Resolves base URL from:
    1. Constructor argument
    2. AAB_API_URL environment variable
    3. Default: http://localhost:8000
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.environ.get(
            "AAB_API_URL", "http://localhost:8000"
        )
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def get(self, path: str, **params: Any) -> Any:
        """GET request to /api{path}. Returns parsed JSON."""
        return self._request("GET", path, params=params)

    def post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        """POST request to /api{path}. Returns parsed JSON."""
        return self._request("POST", path, json=data)

    def put(self, path: str, data: dict[str, Any] | None = None) -> Any:
        """PUT request to /api{path}. Returns parsed JSON."""
        return self._request("PUT", path, json=data)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Execute HTTP request with error handling and exit code mapping."""
        api_path = f"/api{path}" if not path.startswith("/api") else path
        try:
            resp = self._client.request(method, api_path, **kwargs)
        except httpx.ConnectError:
            from autonomous_agent_builder.cli.output import error
            error(
                f"Error: cannot connect to server at {self.base_url}\n"
                "Hint: run 'builder server start' to start the server"
            )
            sys.exit(EXIT_CONNECTIVITY)
        except httpx.TimeoutException:
            from autonomous_agent_builder.cli.output import error
            error("Error: request timed out")
            sys.exit(EXIT_CONNECTIVITY)

        if resp.status_code >= 400:
            detail = resp.text
            import contextlib

            with contextlib.suppress(Exception):
                detail = resp.json()
            raise AabApiError(resp.status_code, detail)

        if resp.status_code == 204:
            return {}

        return resp.json()

    def health(self) -> dict[str, Any]:
        """Check server health via GET /health (not /api prefixed)."""
        try:
            resp = self._client.get("/health")
            return resp.json()
        except httpx.ConnectError:
            from autonomous_agent_builder.cli.output import error
            error(
                f"Error: cannot connect to server at {self.base_url}\n"
                "Hint: run 'builder server start' to start the server"
            )
            sys.exit(EXIT_CONNECTIVITY)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()


def get_client() -> BuilderClient:
    """Get a BuilderClient instance. Convenience factory."""
    return BuilderClient()


def handle_api_error(err: AabApiError) -> None:
    """Map API errors to CLI exit codes and print user-friendly messages."""
    from autonomous_agent_builder.cli.output import error

    if err.status_code == 404:
        detail = err.detail
        if isinstance(detail, dict):
            detail = detail.get("detail", str(detail))
        error(f"Error: not found — {detail}")
        sys.exit(EXIT_FAILURE)
    elif err.status_code == 422:
        detail = err.detail
        if isinstance(detail, dict):
            detail = detail.get("detail", str(detail))
        error(f"Error: invalid input — {detail}")
        sys.exit(EXIT_INVALID_USAGE)
    else:
        error(f"Error: server returned {err.status_code} — {err.detail}")
        sys.exit(EXIT_FAILURE)
