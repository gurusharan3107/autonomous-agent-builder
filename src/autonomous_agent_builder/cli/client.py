"""HTTP client for the builder CLI — sync httpx wrapper around the FastAPI backend.

The CLI talks to the running server via HTTP. This keeps business logic in one place
(the server) and avoids duplicating validation, DB access, or orchestration logic.

The server must be running for CLI commands to work. Use `builder doctor`
to verify connectivity, or `builder start` to launch the local dashboard and API.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import httpx

from autonomous_agent_builder.cli.output import emit_error
from autonomous_agent_builder.cli.port_manager import get_server_url, read_port_file
from autonomous_agent_builder.cli.project_discovery import ProjectNotFoundError, find_agent_builder_dir

# Exit codes per CLI contract
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INVALID_USAGE = 2
EXIT_CONNECTIVITY = 3


class AabApiError(Exception):
    """API returned a non-2xx response."""

    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


class BuilderConnectivityError(Exception):
    """Builder API is unreachable but local fallback may still be possible."""

    def __init__(self, base_url: str, reason: str = "connectivity_error"):
        self.base_url = base_url
        self.reason = reason
        super().__init__(f"{reason}: {base_url}")


class BuilderClient:
    """Synchronous HTTP client for the autonomous-agent-builder API.

    Resolves base URL from:
    1. Constructor argument
    2. AAB_API_URL environment variable
    3. Repo-local .agent-builder/server.port
    4. Default: http://localhost:8000
    """

    def __init__(self, base_url: str | None = None, *, use_json: bool = False):
        self.base_url = base_url or resolve_base_url()
        self.use_json = use_json
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
            _exit_connectivity(self.base_url, use_json=self.use_json)
        except httpx.TimeoutException:
            emit_error(
                "request timed out",
                code="connectivity_timeout",
                hint="Retry the command or verify the builder server is reachable.",
                use_json=self.use_json,
            )
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
            if resp.status_code >= 400:
                _exit_invalid_health(
                    self.base_url,
                    use_json=self.use_json,
                    detail={"status_code": resp.status_code, "body": _safe_json_or_text(resp)},
                )
            return _parse_json_response(resp, self.base_url, use_json=self.use_json)
        except httpx.ConnectError:
            _exit_connectivity(self.base_url, use_json=self.use_json)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()


def resolve_base_url() -> str:
    """Resolve the builder API base URL with repo-local port fallback."""
    return resolve_base_url_with_source()[0]


def resolve_base_url_with_source() -> tuple[str, str]:
    """Resolve the builder API base URL and return the winning source."""
    env_url = os.environ.get("AAB_API_URL")
    if env_url:
        return env_url, "env"

    port = None
    configured_root = os.environ.get("AAB_PROJECT_ROOT")
    if configured_root:
        port = read_port_file(Path(configured_root) / ".agent-builder")
    else:
        try:
            port = read_port_file(find_agent_builder_dir())
        except ProjectNotFoundError:
            port = None

    if port:
        return get_server_url(port), "repo-port"

    return "http://localhost:8000", "default"


def _safe_json_or_text(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


def _valid_health_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("status"), str)
        and bool(payload.get("status"))
    )


def _parse_json_response(resp: httpx.Response, base_url: str, *, use_json: bool = False) -> dict[str, Any]:
    try:
        payload = resp.json()
    except ValueError:
        content_type = resp.headers.get("content-type", "unknown")
        emit_error(
            f"server at {base_url} returned non-JSON response from /health",
            code="invalid_health_response",
            hint=(
                "Point AAB_API_URL to the builder API, or use a repo-local "
                "'builder start' session that writes .agent-builder/server.port."
            ),
            detail={"content_type": content_type},
            use_json=use_json,
        )
        sys.exit(EXIT_CONNECTIVITY)

    if not _valid_health_payload(payload):
        emit_error(
            f"server at {base_url} returned invalid health payload",
            code="invalid_health_payload",
            hint="Run 'builder start' or verify AAB_API_URL points to a builder API.",
            detail=payload,
            use_json=use_json,
        )
        sys.exit(EXIT_CONNECTIVITY)

    return payload


def _exit_invalid_health(base_url: str, *, use_json: bool = False, detail: Any = None) -> None:
    emit_error(
        f"server at {base_url} did not return the builder health contract",
        code="invalid_health_endpoint",
        hint=(
            "Run 'builder start' or point AAB_API_URL to the builder API. "
            "Another service may be listening on this port."
        ),
        detail=detail,
        use_json=use_json,
    )
    sys.exit(EXIT_CONNECTIVITY)


def _exit_connectivity(base_url: str, *, use_json: bool = False) -> None:
    emit_error(
        f"cannot connect to server at {base_url}",
        code="connectivity_error",
        hint="Run 'builder start' to start the local dashboard and API.",
        use_json=use_json,
    )
    sys.exit(EXIT_CONNECTIVITY)


def get_client(*, use_json: bool = False) -> BuilderClient:
    """Get a BuilderClient instance. Convenience factory."""
    return BuilderClient(use_json=use_json)


def request_json(client: BuilderClient, method: str, path: str, **kwargs: Any) -> Any:
    """Execute a request without emitting CLI output on connectivity failures."""
    api_path = f"/api{path}" if not path.startswith("/api") else path
    try:
        resp = client._client.request(method, api_path, **kwargs)
    except httpx.ConnectError as exc:
        raise BuilderConnectivityError(client.base_url, "connectivity_error") from exc
    except httpx.TimeoutException as exc:
        raise BuilderConnectivityError(client.base_url, "connectivity_timeout") from exc
    except httpx.HTTPError as exc:
        raise BuilderConnectivityError(client.base_url, "connectivity_error") from exc

    if resp.status_code >= 400:
        raise AabApiError(resp.status_code, _safe_json_or_text(resp))

    try:
        return resp.json()
    except ValueError:
        return _safe_json_or_text(resp)


def handle_api_error(err: AabApiError, *, use_json: bool = False) -> None:
    """Map API errors to CLI exit codes and print user-friendly messages."""
    detail = err.detail
    if isinstance(detail, dict):
        detail = detail.get("detail", detail)
    if err.status_code == 404:
        emit_error(
            "resource not found",
            code="not_found",
            hint="List or resolve the resource first, then retry with the exact ID.",
            detail=detail,
            use_json=use_json,
        )
        sys.exit(EXIT_FAILURE)
    elif err.status_code == 422:
        emit_error(
            "invalid input",
            code="invalid_input",
            hint="Check the required flags or ID shape and retry.",
            detail=detail,
            use_json=use_json,
        )
        sys.exit(EXIT_INVALID_USAGE)
    else:
        emit_error(
            f"server returned {err.status_code}",
            code="server_error",
            hint="Check builder server logs or rerun with a narrower command.",
            detail=detail,
            use_json=use_json,
        )
        sys.exit(EXIT_FAILURE)
