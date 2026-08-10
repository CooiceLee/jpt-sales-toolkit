"""Role-gated endpoints for offline Leader/Tech task packages."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services.tech_task_exchange_contract import ASSIGNMENT_TYPE, RESULT_TYPE
from ..services.tech_task_exchange_service import (
    TechTaskExchangeError,
    TechTaskExchangeService,
)
from .deps import get_current_user, require_role


router = APIRouter(prefix="/data/tech-tasks", tags=["tech_task_exchange"])
MAX_PACKAGE_BYTES = 10 * 1024 * 1024


class AssignmentExportRequest(BaseModel):
    recipient_user_id: str


@router.post("/assignments/export")
async def export_assignments(
    request: AssignmentExportRequest,
    user: dict = Depends(require_role("leader")),
):
    package = _call(TechTaskExchangeService().export_assignments, user, request.recipient_user_id)
    return _download(package, "jpt-tech-assignments", "jpttask")


@router.post("/results/export")
async def export_results(user: dict = Depends(require_role("tech"))):
    package = _call(TechTaskExchangeService().export_results, user)
    return _download(package, "jpt-tech-results", "jptresult")


@router.post("/assignments/preflight")
async def preflight_assignments(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("tech")),
):
    package = await _read_package(file)
    _require_package_type(package, ASSIGNMENT_TYPE)
    return TechTaskExchangeService().preflight(package, user)


@router.post("/results/preflight")
async def preflight_results(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("leader")),
):
    package = await _read_package(file)
    _require_package_type(package, RESULT_TYPE)
    return TechTaskExchangeService().preflight(package, user)


@router.post("/assignments/import")
async def import_assignments(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("tech")),
):
    package = await _read_package(file)
    _require_package_type(package, ASSIGNMENT_TYPE)
    return _call(TechTaskExchangeService().import_package, package, user)


@router.post("/results/import")
async def import_results(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("leader")),
):
    package = await _read_package(file)
    _require_package_type(package, RESULT_TYPE)
    return _call(TechTaskExchangeService().import_package, package, user)


@router.post("/preflight")
async def preflight_package(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    _require_exchange_role(user)
    return TechTaskExchangeService().preflight(await _read_package(file), user)


@router.post("/import")
async def import_package(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    _require_exchange_role(user)
    return _call(TechTaskExchangeService().import_package, await _read_package(file), user)


async def _read_package(file: UploadFile) -> dict:
    content = await file.read(MAX_PACKAGE_BYTES + 1)
    if len(content) > MAX_PACKAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Tech task package exceeds the 10 MB limit",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Tech task package is empty")
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid Tech task package JSON")
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="Tech task package must be a JSON object")
    return value


def _call(callback, *args):
    try:
        return callback(*args)
    except TechTaskExchangeError as error:
        raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": str(error)})
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


def _require_package_type(package: dict, expected: str) -> None:
    if package.get("package_type") != expected:
        raise HTTPException(status_code=400, detail="Wrong Tech task package type for this action")


def _require_exchange_role(user: dict) -> None:
    if user.get("role") not in {"leader", "tech"}:
        raise HTTPException(status_code=403, detail="Tech task packages are limited to Leader and Tech accounts")


def _download(package: dict, prefix: str, extension: str) -> StreamingResponse:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    body = json.dumps(package, ensure_ascii=False, indent=2)
    return StreamingResponse(
        iter([body]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{prefix}_{stamp}.{extension}"'},
    )
