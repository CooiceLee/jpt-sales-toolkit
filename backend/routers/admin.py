"""
Admin router - backup, restore, and migration endpoints.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from .deps import require_role, get_admin_service
from ..services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


class MigrateLegacyRequest(BaseModel):
    legacy_data_dir: str
    output_dir: str
    dry_run: bool = False


class BackupCleanupRequest(BaseModel):
    keep_count: int = 10
    keep_days: int = 30


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

    # Save uploaded file
    backup_path = service.data_dir / "backups" / backup_file.filename
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    with open(backup_path, "wb") as f:
        content = await backup_file.read()
        f.write(content)

    try:
        return service.restore(backup_path, user["id"])
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


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
