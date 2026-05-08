"""Embedded FastAPI server application factory.

This server is copied into .agent-builder/server/ during project initialization
and serves the local project's dashboard and API endpoints.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub


_DASHBOARD_CACHE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


def _is_truthy(value: str | None) -> bool:
    """Match the truthy-string convention used elsewhere in the runtime."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(db_path: Path, dashboard_path: Path, project_root: Path | None = None) -> FastAPI:
    """Create FastAPI application for embedded server.

    Args:
        db_path: Path to SQLite database file
        dashboard_path: Path to dashboard assets directory
        project_root: Path to project root directory (parent of .agent-builder/)

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Agent Builder",
        description="Project-level autonomous SDLC builder",
        version="0.1.0",
    )

    # Store project root in app state
    if project_root is None:
        # Calculate from db_path (.agent-builder/agent_builder.db)
        project_root = db_path.parent.parent
    app.state.project_root = project_root
    os.environ["AAB_PROJECT_ROOT"] = str(project_root)

    app.state.chat_hub = ChatSessionHub()

    # Initialize database connection
    _init_database(app, db_path)

    # Register API routes
    _register_routes(app)

    # Serve dashboard assets
    _mount_dashboard(app, dashboard_path)

    return app


def _init_database(app: FastAPI, db_path: Path) -> None:
    """Initialize database connection for the application.

    Args:
        app: FastAPI application
        db_path: Path to SQLite database file
    """
    from autonomous_agent_builder.db.session import close_db, get_engine

    # Set database URL for this server instance
    db_url = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DB_URL_OVERRIDE"] = db_url

    @app.on_event("startup")
    async def startup():
        """Initialize database engine and local OTLP collector on startup."""
        import os

        from autonomous_agent_builder.db.session import init_db
        from autonomous_agent_builder.observability.local_collector import (
            LocalOTLPCollector,
            parse_local_endpoint,
        )

        # Trigger engine creation
        get_engine()
        # Create tables if they don't exist
        await init_db()

        # Bake-in OTLP collector: when builder is the configured local
        # endpoint, run an in-process receiver so Day-0 readiness's
        # ``telemetry_collector_reachable`` check passes on a fresh
        # ``builder init`` without external setup. Operators with their own
        # collector get a port-in-use skip.
        app.state.local_otlp_collector = None
        if _is_truthy(os.environ.get("AAB_CLAUDE_OTEL_ENABLED")):
            endpoint = os.environ.get("AAB_CLAUDE_OTEL_ENDPOINT", "")
            local = parse_local_endpoint(endpoint)
            if local is not None:
                host, port = local
                project_root = app.state.project_root or Path.cwd()
                telemetry_root = project_root / ".agent-builder" / "telemetry"
                collector = LocalOTLPCollector(telemetry_root, host, port)
                collector.start()
                app.state.local_otlp_collector = collector

    @app.on_event("shutdown")
    async def shutdown():
        """Close database connections and local OTLP collector on shutdown."""
        await app.state.chat_hub.shutdown()
        await close_db()
        collector = getattr(app.state, "local_otlp_collector", None)
        if collector is not None:
            collector.stop()


def _register_routes(app: FastAPI) -> None:
    """Register API route handlers.

    Args:
        app: FastAPI application
    """
    from autonomous_agent_builder.api.routes import dispatch, onboarding, readiness
    from autonomous_agent_builder.embedded.server.routes import (
        agent,
        dashboard,
        features,
        gates,
        kb,
        knowledge_extraction,
        memory,
        projects,
        stream,
        tasks,
    )

    # Register routers with /api prefix
    app.include_router(agent.router, prefix="/api", tags=["agent"])
    app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
    app.include_router(features.router, prefix="/api", tags=["features"])
    app.include_router(dispatch.router, prefix="/api", tags=["dispatch"])
    app.include_router(tasks.router, prefix="/api", tags=["tasks"])
    app.include_router(gates.router, prefix="/api", tags=["gates"])
    app.include_router(stream.router, prefix="/api", tags=["stream"])
    app.include_router(projects.router, prefix="/api", tags=["projects"])
    app.include_router(kb.router, prefix="/api", tags=["kb"])
    app.include_router(knowledge_extraction.router, prefix="/api", tags=["knowledge"])
    app.include_router(memory.router, prefix="/api", tags=["memory"])
    app.include_router(onboarding.router, prefix="/api", tags=["onboarding"])
    app.include_router(readiness.router, prefix="/api", tags=["readiness"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health endpoint used by builder CLI connectivity checks."""
        return {"status": "ok", "version": app.version}


def _mount_dashboard(app: FastAPI, dashboard_path: Path) -> None:
    """Mount dashboard static files and SPA fallback.

    Args:
        app: FastAPI application
        dashboard_path: Path to dashboard assets directory
    """
    assets_path = dashboard_path / "assets"

    @app.get("/assets/{asset_path:path}")
    async def dashboard_asset(asset_path: str):
        """Serve dashboard assets without browser caching.

        Builder dashboards are rebuilt frequently during local validation, and
        stale asset caching leaves the in-app browser on an older bundle while
        the API already serves fresh data.
        """
        candidate = (assets_path / asset_path).resolve()
        if not str(candidate).startswith(str(assets_path.resolve())):
            raise HTTPException(status_code=404, detail="Asset not found")
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(candidate, headers=_DASHBOARD_CACHE_HEADERS)

    # SPA fallback - serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve index.html for all routes (SPA fallback)."""
        index_path = dashboard_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path, headers=_DASHBOARD_CACHE_HEADERS)
        else:
            return {"message": "Dashboard not yet built"}
