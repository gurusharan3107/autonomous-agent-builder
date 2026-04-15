"""FastAPI application — main entry point for the API and dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from autonomous_agent_builder.api.routes import (
    dashboard_api,
    dispatch,
    features,
    gates,
    knowledge,
    memory_api,
    projects,
)
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.dashboard.routes import router as dashboard_router
from autonomous_agent_builder.db.session import close_db, init_db
from autonomous_agent_builder.observability.logging import configure_logging

STATIC_DIR = Path(__file__).parent.parent / "dashboard" / "static"
FRONTEND_DIST = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — startup and shutdown."""
    settings = get_settings()
    configure_logging(debug=settings.debug)

    # Initialize DB (create tables if needed — use Alembic in prod)
    await init_db()

    yield

    # Cleanup
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Production-grade autonomous SDLC builder",
        lifespan=lifespan,
    )

    # CORS — allow React dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes (JSON)
    app.include_router(projects.router, prefix="/api")
    app.include_router(features.router, prefix="/api")
    app.include_router(gates.router, prefix="/api")
    app.include_router(dispatch.router, prefix="/api")
    app.include_router(dashboard_api.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")
    app.include_router(memory_api.router, prefix="/api")

    # Health check (before static mount so it's not caught by SPA)
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    # Legacy dashboard routes (Jinja2 — kept during migration, skipped if SPA exists)
    if not FRONTEND_DIST.exists():
        app.include_router(dashboard_router)
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:
        # Serve React SPA assets
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

        # SPA fallback — serve index.html for all non-API routes
        from fastapi.responses import FileResponse

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            index = FRONTEND_DIST / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return {"error": "Frontend not built"}

    return app


# Application instance
app = create_app()
