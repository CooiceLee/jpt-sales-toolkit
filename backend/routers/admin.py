"""
Admin router - backup, restore, and migration endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from .deps import require_role, get_admin_service
from ..services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])

MAX_BACKUP_UPLOAD_SIZE = 1024 * 1024 * 1024
BACKUP_UPLOAD_CHUNK_SIZE = 1024 * 1024
_T = TypeVar("_T")
logger = logging.getLogger(__name__)


class MigrateLegacyRequest(BaseModel):
    legacy_data_dir: str
    output_dir: str
    dry_run: bool = False


class BackupCleanupRequest(BaseModel):
    keep_count: int = 10
    keep_days: int = 30


async def _stage_backup_upload(backup_file: UploadFile, staging_dir: Path) -> Path:
    """Stream one bounded upload to a server-named private staging file."""
    staging_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if staging_dir.is_symlink() or not staging_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Secure restore staging directory is unavailable",
        )
    try:
        staging_dir.chmod(0o700)
    except OSError:
        pass
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix="restore_upload_",
        suffix=".zip",
        dir=staging_dir,
        delete=False,
    )
    staged_path = Path(handle.name)
    size = 0
    try:
        with handle:
            while chunk := await backup_file.read(BACKUP_UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_BACKUP_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Backup exceeds the 1 GB upload limit",
                    )
                handle.write(chunk)
        if size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Backup file is empty",
            )
        try:
            staged_path.chmod(0o600)
        except OSError:
            pass
        return staged_path
    except BaseException:
        staged_path.unlink(missing_ok=True)
        raise


async def _run_sync_to_completion(
    callback: Callable[..., _T],
    *args: object,
) -> _T:
    """Keep destructive disk work alive and gated after request cancellation."""
    worker = asyncio.create_task(asyncio.to_thread(callback, *args))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError as cancelled:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            worker.result()
        except Exception:
            logger.exception("Database maintenance worker failed after cancellation")
        raise cancelled


@router.post("/backup")
async def create_backup(
    user: dict = Depends(require_role("leader")),
    service: AdminService = Depends(get_admin_service),
):
    """Create full backup (leader only)."""
    if not service.data_dir:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Data directory not configured",
        )

    output_dir = service.data_dir / "backups"
    return service.backup(output_dir, user["id"])


@router.post("/backups/cleanup")
async def cleanup_backups(
    request: BackupCleanupRequest = BackupCleanupRequest(),
    user: dict = Depends(require_role("leader")),
    service: AdminService = Depends(get_admin_service),
):
    """Clean old backups according to retention policy (leader only)."""
    if not service.data_dir:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Data directory not configured",
        )

    if request.keep_count < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keep_count must be at least 1",
        )
    if request.keep_days < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keep_days must be non-negative",
        )

    return service.cleanup_old_backups(
        service.data_dir / "backups",
        keep_count=request.keep_count,
        keep_days=request.keep_days,
    )


@router.post("/restore")
async def restore_backup(
    backup_file: UploadFile = File(...),
    user: dict = Depends(require_role("leader")),
    service: AdminService = Depends(get_admin_service),
):
    """Restore from backup (leader only)."""
    if not service.data_dir:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Data directory not configured",
        )

    staging_dir = service.data_dir / ".restore_uploads"
    staged_path: Path | None = None
    try:
        staged_path = await _stage_backup_upload(backup_file, staging_dir)
        # Reject a corrupt, unsafe, or inconsistent archive before restore can
        # create a safety backup or touch the active database.
        await _run_sync_to_completion(service.validate_backup_archive, staged_path)
        result = await _run_sync_to_completion(service.restore, staged_path, user["id"])
        result["source_backup"] = "uploaded backup"
        return result
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except (ValueError, zipfile.BadZipFile) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    finally:
        try:
            await backup_file.close()
        finally:
            if staged_path is not None:
                staged_path.unlink(missing_ok=True)
            try:
                staging_dir.rmdir()
            except OSError:
                pass


@router.post("/migrate-legacy")
async def migrate_legacy_data(
    request: MigrateLegacyRequest,
    user: dict = Depends(require_role("leader")),
    service: AdminService = Depends(get_admin_service),
):
    """Run legacy data migration (leader only)."""
    legacy_dir = Path(request.legacy_data_dir)
    output_dir = Path(request.output_dir)

    if not legacy_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Legacy data directory not found: {legacy_dir}",
        )

    return service.migrate_legacy(legacy_dir, output_dir, request.dry_run)


@router.get("/system-info")
async def get_system_info(
    user: dict = Depends(require_role("leader")),
    service: AdminService = Depends(get_admin_service),
):
    """Get system information (leader only)."""
    return service.get_system_info()
