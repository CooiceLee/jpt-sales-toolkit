"""
JPT Sales Toolkit v2 - FastAPI Application

New layered architecture with SQLite backend.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import re
from fastapi.responses import FileResponse, HTMLResponse

from .config import APP_VERSION, init_settings
from .database_access import database_access_gate
from .startup_upgrade import initialize_database_safely
from .routers import (
    auth_router,
    config_router,
    customers_router,
    leads_router,
    intake_router,
    tasks_router,
    review_router,
    admin_router,
    data_exchange_router,
    authorization_router,
    desktop_router,
    spreadsheet_import_router,
    data_quality_issues_router,
    inquiry_aggregate_router,
    tech_task_exchange_router,
)

# Application root directory
APP_ROOT = Path(__file__).parent.parent


# Any asset URL carrying a hand-written version marker.
ASSET_VERSION_PATTERN = re.compile(r'(/static/[^"\'?\s]+)\?v=[^"\'\s]*')


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    configured_origins = [
        value.strip()
        for value in os.environ.get("JPT_CORS_ORIGINS", "").split(",")
        if value.strip()
    ]
    app = FastAPI(
        title="JPT Sales Toolkit",
        version=APP_VERSION,
        description="Sales lead management system with Customer + Lead data model",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def database_maintenance_policy(request, call_next):
        """Drain API work before an online restore replaces the database."""
        path = request.url.path
        if path != "/api" and not path.startswith("/api/"):
            return await call_next(request)
        is_restore = (
            request.method == "POST"
            and path.rstrip("/") == "/api/admin/restore"
        )
        access = (
            database_access_gate.exclusive
            if is_restore
            else database_access_gate.shared
        )
        async with access():
            return await call_next(request)

    @app.middleware("http")
    async def desktop_cache_policy(request, call_next):
        """Never let an upgraded desktop app reuse stale HTML or static assets."""
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith("/index.html"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        elif path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    # Mount API routers
    app.include_router(auth_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(customers_router, prefix="/api")
    app.include_router(leads_router, prefix="/api")
    app.include_router(intake_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(review_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(data_exchange_router, prefix="/api")
    app.include_router(authorization_router, prefix="/api")
    app.include_router(desktop_router, prefix="/api")
    app.include_router(spreadsheet_import_router, prefix="/api")
    app.include_router(data_quality_issues_router, prefix="/api")
    app.include_router(inquiry_aggregate_router, prefix="/api")
    app.include_router(tech_task_exchange_router, prefix="/api")

    @app.get("/api/health", include_in_schema=False)
    async def health_check():
        return {
            "status": "ok",
            "version": APP_VERSION,
            "desktop": callable(getattr(app.state, "desktop_shutdown", None)),
            "running_from_disk_image": os.environ.get("JPT_RUNNING_FROM_DISK_IMAGE") == "1",
        }

    # Startup event
    @app.on_event("startup")
    async def startup():
        # Initialize settings first
        settings = init_settings(APP_ROOT)
        # Back up and verify existing user data before any schema migration.
        app.state.startup_upgrade = initialize_database_safely(settings)

    # Serve frontend static files
    frontend_dir = APP_ROOT / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        def index_html() -> HTMLResponse:
            """The page with every asset stamped with this build.

            The version markers in index.html are written by hand, so an asset
            whose contents changed kept the same URL and browsers went on using
            the copy they already had - which shows up as a half-updated page:
            new labels from one module beside old behaviour from another. The
            stamp is the application version and the file's own modification
            time, so it changes whenever either does.
            """
            source = frontend_dir / "index.html"
            stamp = f"{APP_VERSION}-{int(source.stat().st_mtime)}"
            html = ASSET_VERSION_PATTERN.sub(
                lambda match: f"{match.group(1)}?v={stamp}",
                source.read_text(encoding="utf-8"),
            )
            return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})

        @app.get("/")
        async def serve_index():
            return index_html()

        @app.get("/{path:path}")
        async def serve_frontend(path: str):
            """Serve frontend files or fallback to index.html for SPA routes."""
            if path == "api" or path.startswith("api/"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API endpoint not found",
                )
            file_path = frontend_dir / path
            # index.html is always built rather than sent from disk, whichever
            # name it is asked for: the copy on disk still carries the version
            # markers that are rewritten per build, and serving it raw hands the
            # browser the old asset URLs it already has cached.
            if file_path.name == "index.html" or not (
                file_path.exists() and file_path.is_file()
            ):
                return index_html()
            return FileResponse(file_path)

    return app


# Create application instance
app = create_app()
