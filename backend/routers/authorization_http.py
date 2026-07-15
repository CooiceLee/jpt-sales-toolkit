"""HTTP-level helpers for authorization uploads and local-only setup."""

from __future__ import annotations

import json
import re
from ipaddress import ip_address

from fastapi import HTTPException, Request, UploadFile, status
from fastapi.responses import Response


MAX_AUTHORIZATION_FILE_SIZE = 1024 * 1024


async def read_json_upload(upload: UploadFile, expected_suffix: str) -> dict:
    filename = upload.filename or ""
    if filename and not filename.lower().endswith(expected_suffix):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected a {expected_suffix} file",
        )
    content = await upload.read(MAX_AUTHORIZATION_FILE_SIZE + 1)
    await upload.close()
    if len(content) > MAX_AUTHORIZATION_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Authorization file is too large",
        )
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization file is not valid JSON",
        ) from exc
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization file must contain a JSON object",
        )
    return value


def json_attachment(value: dict, filename: str) -> Response:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def member_filename(member: dict) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", member.get("username") or "member")
    return f"jpt-{safe_name.strip('-') or 'member'}.jptauth"


def raise_service_error(exc: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host in {"localhost", "testclient"}:
        return
    try:
        if ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="First-run setup is available only from this computer",
    )
