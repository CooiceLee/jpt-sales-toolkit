"""
Admin service - backup, restore, and migration operations.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..config import APP_VERSION
from ..repositories import close_db
from ..migration import run_migration, run_dry_migration


class AdminService:
    """Admin operations service."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir

    def _database_path(self) -> Path:
        if not self.data_dir:
            raise ValueError("Data directory not configured")
        return self.data_dir / "database.sqlite"

    def _validate_zip_members(self, zf: zipfile.ZipFile) -> dict:
        bad_member = zf.testzip()
        if bad_member:
            raise ValueError(f"Invalid backup: corrupt member {bad_member}")

        for name in zf.namelist():
            member_path = Path(name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Invalid backup: unsafe path {name}")

        if "manifest.json" not in zf.namelist():
            raise ValueError("Invalid backup: missing manifest.json")
        if "database.sqlite" not in zf.namelist():
            raise ValueError("Invalid backup: missing database.sqlite")

        return json.loads(zf.read("manifest.json"))

    def _validate_database_file(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError(f"Invalid backup database: integrity_check={result[0] if result else None}")

            foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise ValueError(f"Invalid backup database: foreign_key_check failed ({len(foreign_key_errors)} rows)")
        finally:
            conn.close()

    def _write_database_snapshot(self, snapshot_path: Path) -> None:
        """Create a consistent SQLite snapshot using the online backup API."""
        db_path = self._database_path()
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        source = sqlite3.connect(str(db_path))
        target = sqlite3.connect(str(snapshot_path))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    def _next_backup_paths(self, output_dir: Path, timestamp: str) -> tuple[str, Path, Path]:
        """Return non-conflicting backup and temporary snapshot paths."""
        suffix = 0
        while True:
            backup_name = f"backup_{timestamp}" if suffix == 0 else f"backup_{timestamp}_{suffix:02d}"
            backup_path = output_dir / f"{backup_name}.zip"
            snapshot_path = output_dir / f".{backup_name}.sqlite"
            if not backup_path.exists() and not snapshot_path.exists():
                return backup_name, backup_path, snapshot_path
            suffix += 1

    def backup(self, output_dir: Path, actor_id: str) -> dict:
        """
        Create full backup (database + attachments).

        Returns backup metadata.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        output_dir.mkdir(parents=True, exist_ok=True)
        backup_name, backup_path, snapshot_path = self._next_backup_paths(output_dir, timestamp)

        # Create manifest
        manifest = {
            "backup_time": datetime.utcnow().isoformat(),
            "backup_by": actor_id,
            "version": APP_VERSION,
            "contents": [],
        }

        try:
            self._write_database_snapshot(snapshot_path)

            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add database
                zf.write(snapshot_path, "database.sqlite")
                manifest["contents"].append("database.sqlite")

                # Add attachments directory
                attachments_dir = self.data_dir / "attachments" if self.data_dir else None
                if attachments_dir and attachments_dir.exists():
                    for file_path in attachments_dir.rglob("*"):
                        if file_path.is_file():
                            arcname = f"attachments/{file_path.relative_to(attachments_dir)}"
                            zf.write(file_path, arcname)
                            manifest["contents"].append(arcname)

                # Add manifest
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        finally:
            snapshot_path.unlink(missing_ok=True)

        result = {
            "backup_path": str(backup_path),
            "backup_size": backup_path.stat().st_size,
            "manifest": manifest,
        }

        # Apply backup retention policy
        cleanup_result = self.cleanup_old_backups(output_dir)
        result["cleanup"] = cleanup_result

        return result

    def cleanup_old_backups(
        self,
        backup_dir: Path,
        keep_count: int = 10,
        keep_days: int = 30
    ) -> dict:
        """
        Clean up old backups based on retention policy.

        Policy: Keep the MOST permissive of:
        - Last N backups (default: 10)
        - Backups from last N days (default: 30)

        Args:
            backup_dir: Directory containing backups
            keep_count: Number of recent backups to keep
            keep_days: Number of days of backups to keep

        Returns:
            Cleanup report
        """
        if not backup_dir.exists():
            return {"deleted": 0, "kept": 0, "error": None}

        # Find all backup files
        backup_files = sorted(
            [f for f in backup_dir.glob("backup_*.zip")],
            key=lambda f: f.stat().st_mtime,
            reverse=True  # Newest first
        )

        if len(backup_files) <= keep_count:
            # Not enough backups to clean up
            return {
                "deleted": 0,
                "kept": len(backup_files),
                "error": None,
                "reason": f"Total backups ({len(backup_files)}) <= keep_count ({keep_count})"
            }

        cutoff_time = datetime.now().timestamp() - (keep_days * 24 * 3600)

        # Determine which backups to keep
        keep_files = set()

        # Keep last N backups (by modification time)
        keep_files.update(backup_files[:keep_count])

        # Keep backups from last N days
        for backup_file in backup_files:
            if backup_file.stat().st_mtime >= cutoff_time:
                keep_files.add(backup_file)

        # Delete old backups
        deleted = []
        errors = []

        for backup_file in backup_files:
            if backup_file not in keep_files:
                try:
                    # Get file info before deletion
                    stat_info = backup_file.stat()
                    backup_size = stat_info.st_size
                    backup_mtime = datetime.fromtimestamp(stat_info.st_mtime).isoformat()

                    # Delete file
                    backup_file.unlink()

                    deleted.append({
                        "file": backup_file.name,
                        "size": backup_size,
                        "mtime": backup_mtime
                    })
                except Exception as exc:
                    errors.append({
                        "file": backup_file.name,
                        "error": str(exc)
                    })

        return {
            "deleted": len(deleted),
            "kept": len(keep_files),
            "deleted_files": deleted,
            "errors": errors if errors else None,
            "policy": {
                "keep_count": keep_count,
                "keep_days": keep_days
            }
        }

    def restore(self, backup_path: Path, actor_id: str) -> dict:
        """
        Restore from backup (full replacement).

        Returns restore report.
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        if not self.data_dir:
            raise ValueError("Data directory not configured")

        # Validate backup
        with zipfile.ZipFile(backup_path, "r") as zf:
            manifest = self._validate_zip_members(zf)

        # Create pre-restore backup
        pre_restore = None
        pre_restore_error = None
        if self._database_path().exists():
            try:
                pre_restore = self.backup(self.data_dir / "backups", actor_id)
            except Exception as exc:
                # A corrupt current database must not prevent restoring a valid backup.
                pre_restore_error = str(exc)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        stage_dir = self.data_dir / f".restore_stage_{timestamp}"
        old_db_path = self.data_dir / f".database_before_restore_{timestamp}.sqlite"
        old_attachments_dir = self.data_dir / f".attachments_before_restore_{timestamp}"

        # Extract backup
        if stage_dir.exists():
            shutil.rmtree(stage_dir)
        stage_dir.mkdir(parents=True)

        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                # Extract database
                zf.extract("database.sqlite", stage_dir)

                # Extract attachments
                for name in zf.namelist():
                    if name.startswith("attachments/"):
                        zf.extract(name, stage_dir)

            staged_db = stage_dir / "database.sqlite"
            staged_attachments = stage_dir / "attachments"
            self._validate_database_file(staged_db)

            db_path = self._database_path()
            attachments_dir = self.data_dir / "attachments"

            close_db()

            if old_db_path.exists():
                old_db_path.unlink()
            if db_path.exists():
                db_path.replace(old_db_path)

            if old_attachments_dir.exists():
                shutil.rmtree(old_attachments_dir)
            if attachments_dir.exists():
                attachments_dir.replace(old_attachments_dir)

            try:
                staged_db.replace(db_path)
                if staged_attachments.exists():
                    staged_attachments.replace(attachments_dir)
                else:
                    attachments_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                if db_path.exists():
                    db_path.unlink()
                if old_db_path.exists():
                    old_db_path.replace(db_path)

                if attachments_dir.exists():
                    shutil.rmtree(attachments_dir)
                if old_attachments_dir.exists():
                    old_attachments_dir.replace(attachments_dir)
                raise
        finally:
            if stage_dir.exists():
                shutil.rmtree(stage_dir)
            old_db_path.unlink(missing_ok=True)
            if old_attachments_dir.exists():
                shutil.rmtree(old_attachments_dir)

        return {
            "restore_time": datetime.utcnow().isoformat(),
            "restored_by": actor_id,
            "source_backup": str(backup_path),
            "pre_restore_backup": pre_restore["backup_path"] if pre_restore else None,
            "pre_restore_error": pre_restore_error,
            "manifest": manifest,
        }

    def migrate_legacy(
        self,
        legacy_data_dir: Path,
        output_dir: Path,
        dry_run: bool = False,
    ) -> dict:
        """
        Run legacy data migration.

        Args:
            legacy_data_dir: Path to old data/ directory
            output_dir: Path for new database and reports
            dry_run: If True, run in-memory without writing files

        Returns:
            Migration report
        """
        if dry_run:
            return run_dry_migration(legacy_data_dir)
        else:
            return run_migration(legacy_data_dir, output_dir)

    def get_system_info(self) -> dict:
        """Get system information for admin page."""
        info = {
            "version": APP_VERSION,
            "database_path": None,
            "database_size": None,
            "attachments_count": 0,
            "attachments_size": 0,
        }

        if self.data_dir:
            db_path = self.data_dir / "database.sqlite"
            if db_path.exists():
                info["database_path"] = str(db_path)
                info["database_size"] = db_path.stat().st_size

            attachments_dir = self.data_dir / "attachments"
            if attachments_dir.exists():
                files = list(attachments_dir.rglob("*"))
                info["attachments_count"] = len([f for f in files if f.is_file()])
                info["attachments_size"] = sum(f.stat().st_size for f in files if f.is_file())

        return info
