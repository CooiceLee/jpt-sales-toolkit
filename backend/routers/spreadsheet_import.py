"""Leader-only correction-first spreadsheet import endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..config import MAX_UPLOAD_SIZE
from ..repositories.base import request_db_connection
from ..services.spreadsheet_import import SpreadsheetImportService
from ..services.spreadsheet_import.errors import ImportBlockedError, SpreadsheetImportError
from .deps import get_current_user, require_role

router = APIRouter(
    prefix="/data", tags=["spreadsheet_import"],
    dependencies=[Depends(require_role("leader"))],
)
@router.post("/spreadsheet/preflight")
async def spreadsheet_preflight(
    file: UploadFile = File(...),
    resolutions: str = Form("{}"),
    user: dict = Depends(get_current_user),
):
    content = await _read_xlsx(file)
    try:
        with request_db_connection() as conn:
            return SpreadsheetImportService(conn).preflight(
                content, file.filename or "import.xlsx", resolutions, user
            )
    except SpreadsheetImportError as exc:
        raise _http_error(exc) from exc


@router.post("/spreadsheet/import")
async def spreadsheet_import(
    file: UploadFile = File(...),
    resolutions: str = Form("{}"),
    expected_source_hash: str = Form(...),
    user: dict = Depends(get_current_user),
):
    content = await _read_xlsx(file)
    try:
        with request_db_connection() as conn:
            return SpreadsheetImportService(conn).commit(
                content, file.filename or "import.xlsx", resolutions,
                expected_source_hash, user,
            )
    except SpreadsheetImportError as exc:
        raise _http_error(exc) from exc


async def _read_xlsx(file: UploadFile) -> bytes:
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx workbooks are supported")
    content = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Workbook exceeds the 25 MB limit")
    if not content:
        raise HTTPException(status_code=400, detail="Workbook is empty")
    return content


def _http_error(exc: SpreadsheetImportError) -> HTTPException:
    detail = {"code": exc.code, "message": str(exc)}
    if isinstance(exc, ImportBlockedError):
        detail["report"] = exc.report
    return HTTPException(status_code=exc.status_code, detail=detail)
