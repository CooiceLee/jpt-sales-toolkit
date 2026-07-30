"""Fail-safe desktop database initialization and upgrade orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import APP_VERSION, AppSettings
from .repositories import (
    APP_SCHEMA_VERSION,
    database_requires_schema_migration,
    init_db,
    read_app_schema_version,
)
from .services.admin_service import AdminService


@dataclass(frozen=True)
class StartupUpgradeResult:
    source_schema_version: int
    target_schema_version: int
    backup_path: Optional[Path]
    migrated: bool


def initialize_database_safely(settings: AppSettings) -> StartupUpgradeResult:
    """Back up, migrate, verify and roll back an existing desktop database.

    The pre-upgrade archive is completed and validated before ``init_db`` can
    make the first schema write. Any migration or post-migration validation
    failure restores the original SQLite snapshot and leaves the archive in
    place for independent recovery.
    """
    db_path = settings.db_path
    existed = db_path.is_file()
    source_version = read_app_schema_version(db_path) if existed else 0
    if source_version > APP_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema {source_version} is newer than supported schema "
            f"{APP_SCHEMA_VERSION}; use a matching or newer JPT version"
        )

    service = AdminService(data_dir=settings.data_dir)
    backup_path: Optional[Path] = None
    needs_migration = existed and database_requires_schema_migration(db_path)
    if needs_migration:
        backup = service.create_pre_upgrade_backup(
            settings.backup_dir,
            "startup-upgrade",
            source_schema_version=source_version,
            target_schema_version=APP_SCHEMA_VERSION,
            target_app_version=APP_VERSION,
        )
        if not backup.get("validated"):
            raise RuntimeError("Pre-upgrade backup did not pass validation")
        backup_path = Path(backup["backup_path"])

    try:
        init_db(db_path, app_version=APP_VERSION)
        service.validate_database_file(db_path)
        target_version = read_app_schema_version(db_path)
        if target_version != APP_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database migration stopped at schema {target_version}; "
                f"expected {APP_SCHEMA_VERSION}"
            )
    except Exception as migration_error:
        if backup_path:
            try:
                service.restore_database_from_backup(backup_path)
            except Exception as rollback_error:
                raise RuntimeError(
                    "JPT database upgrade failed and automatic rollback was incomplete. "
                    f"Recovery archive: {backup_path}"
                ) from rollback_error
            raise RuntimeError(
                "JPT database upgrade failed; the original database was restored. "
                f"Recovery archive: {backup_path}"
            ) from migration_error
        raise

    return StartupUpgradeResult(
        source_schema_version=source_version,
        target_schema_version=APP_SCHEMA_VERSION,
        backup_path=backup_path,
        migrated=needs_migration,
    )
