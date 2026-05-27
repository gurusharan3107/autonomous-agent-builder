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
from autonomous_agent_builder.observability.codex_otel import codex_otel_status
from autonomous_agent_builder.services.path_containment import resolve_contained_path

_DASHBOARD_CACHE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


def _is_truthy(value: str | None) -> bool:
    """Match the truthy-string convention used elsewhere in the runtime."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _local_otlp_endpoint(project_root: Path) -> str:
    """Return the project-local OTLP endpoint that builder should receive."""
    if _is_truthy(os.environ.get("AAB_CLAUDE_OTEL_ENABLED")):
        endpoint = (os.environ.get("AAB_CLAUDE_OTEL_ENDPOINT") or "").strip()
        if endpoint:
            return endpoint

    codex_status = codex_otel_status(project_root)
    if codex_status.get("enabled"):
        return str(codex_status.get("endpoint") or "")

    return ""


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
    import autonomous_agent_builder.db.session as _session_mod
    from autonomous_agent_builder.db.session import close_db, get_engine

    # Set database URL for this server instance
    db_url = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DB_URL_OVERRIDE"] = db_url
    # Ensure the database directory exists before the engine tries to connect.
    db_path.parent.mkdir(parents=True, exist_ok=True)

    @app.on_event("startup")
    async def startup():
        """Initialize database engine and local OTLP collector on startup."""

        from autonomous_agent_builder.db.session import init_db
        from autonomous_agent_builder.observability.local_collector import (
            LocalOTLPCollector,
            parse_local_endpoint,
        )

        # Reset the cached engine so the new DB_URL_OVERRIDE is used.
        # Without this, a stale engine from a previous app instance would be
        # reused when TestClient triggers lifespan for test_embedded_server_app.
        _session_mod._engine = None
        _session_mod._session_factory = None
        # Trigger engine creation
        get_engine()
        # Create tables if they don't exist
        await init_db()
        from autonomous_agent_builder.db.session import get_session_factory
        from autonomous_agent_builder.services.run_reconciliation import (
            reconcile_blocked_sprints_with_materialized_main,
            reconcile_completed_tasks_with_unintegrated_workspace_changes,
            reconcile_orphaned_running_agent_runs,
            reconcile_shipped_sprints_with_failed_materialized_checkout,
        )

        session_factory = get_session_factory()
        async with session_factory() as db:
            reconciled = await reconcile_orphaned_running_agent_runs(db)
            reconciled += await reconcile_completed_tasks_with_unintegrated_workspace_changes(db)
            reconciled += await reconcile_blocked_sprints_with_materialized_main(db)
            reconciled += await reconcile_shipped_sprints_with_failed_materialized_checkout(db)
            if reconciled:
                await db.commit()

        # Bake-in OTLP collector: when builder is the configured local
        # endpoint, run an in-process receiver so Day-0 readiness's
        # ``telemetry_collector_reachable`` check passes on a fresh
        # ``builder init`` without external setup. Operators with their own
        # collector get a port-in-use skip.
        app.state.local_otlp_collector = None
        project_root = app.state.project_root or Path.cwd()
        local = parse_local_endpoint(_local_otlp_endpoint(project_root))
        if local is not None:
            host, port = local
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
        realtime,
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
    app.include_router(realtime.router, prefix="/api", tags=["realtime"])
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
    assets_path = (dashboard_path / "assets").resolve()

    @app.get("/assets/{asset_path:path}")
    async def dashboard_asset(asset_path: str):
        """Serve dashboard assets without browser caching.

        Builder dashboards are rebuilt frequently during local validation, and
        stale asset caching leaves the in-app browser on an older bundle while
        the API already serves fresh data.
        """
        candidate = resolve_contained_path(assets_path, asset_path)
        if candidate is None:
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
