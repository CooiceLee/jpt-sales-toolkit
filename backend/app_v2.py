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
from fastapi.responses import FileResponse

from .config import APP_VERSION, init_settings
from .repositories import init_db
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
)

# Application root directory
APP_ROOT = Path(__file__).parent.parent


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
        # Initialize database
        init_db(settings.db_path)

    # Serve frontend static files
    frontend_dir = APP_ROOT / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        @app.get("/")
        async def serve_index():
            return FileResponse(frontend_dir / "index.html")

        @app.get("/{path:path}")
        async def serve_frontend(path: str):
            """Serve frontend files or fallback to index.html for SPA routes."""
            if path == "api" or path.startswith("api/"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API endpoint not found",
                )
            file_path = frontend_dir / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(frontend_dir / "index.html")

    return app


# Create application instance
app = create_app()
