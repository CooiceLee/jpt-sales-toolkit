"""Authenticated lifecycle controls for the packaged desktop application."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from .authorization_http import require_loopback
from .deps import get_current_user


router = APIRouter(prefix="/desktop", tags=["desktop"])


@router.post("/shutdown")
async def shutdown_desktop(
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Return the response, then stop this user's loopback desktop process."""
    require_loopback(request)
    shutdown = getattr(request.app.state, "desktop_shutdown", None)
    if not callable(shutdown):
        raise HTTPException(status_code=404, detail="Desktop shutdown is unavailable")
    background_tasks.add_task(shutdown)
    return {"status": "shutting_down"}
