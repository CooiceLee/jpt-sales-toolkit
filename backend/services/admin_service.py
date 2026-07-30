"""
Admin service - backup, restore, and migration operations.
"""

from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
import stat
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional

from ..config import APP_VERSION
from ..repositories import close_db
from ..migration import run_migration, run_dry_migration


class AdminService:
    """Admin operations service."""

    # Limits apply to the uncompressed archive contents. They protect the
    # validator and the restore staging area from zip bombs even when the
    # uploaded compressed file itself is within the HTTP upload limit.
    _MAX_BACKUP_MEMBERS = 50_000
    _MAX_BACKUP_MEMBER_SIZE = 2 * 1024 * 1024 * 1024
    _MAX_BACKUP_EXTRACTED_SIZE = 5 * 1024 * 1024 * 1024
    _MAX_BACKUP_MANIFEST_SIZE = 2 * 1024 * 1024
    _MAX_BACKUP_COMPRESSION_RATIO = 1_000
    _COMPRESSION_RATIO_MIN_SIZE = 1024 * 1024
    _ALLOWED_DIRECTORY_MARKERS = {"attachments/", "config/"}

    _TRANSIENT_RUNTIME_FILES = {
        "desktop.lock",
        "desktop_instance.json",
        "desktop_instance.tmp",
    }
    _TRANSIENT_RUNTIME_MEMBERS = {
        f"config/{name}" for name in _TRANSIENT_RUNTIME_FILES
    }

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir

    def _database_path(self) -> Path:
        if not self.data_dir:
            raise ValueError("Data directory not configured")
        return self.data_dir / "database.sqlite"

    @classmethod
    def _validate_archive_name(cls, name: str, *, directory: bool) -> None:
        """Reject paths whose meaning changes across macOS and Windows."""
        if not name or len(name) > 1024 or "\x00" in name or "\\" in name:
            raise ValueError(f"Invalid backup: unsafe path {name!r}")
        if PurePosixPath(name).is_absolute() or name.startswith("/"):
            raise ValueError(f"Invalid backup: unsafe path {name}")

        body = name[:-1] if directory and name.endswith("/") else name
        parts = body.split("/")
        if (
            not body
            or any(not part or part in {".", ".."} for part in parts)
            or any(part.endswith((".", " ")) for part in parts)
            or any(":" in part or PureWindowsPath(part).is_reserved() for part in parts)
        ):
            raise ValueError(f"Invalid backup: unsafe path {name}")

        if directory:
            if not name.endswith("/") or name not in cls._ALLOWED_DIRECTORY_MARKERS:
                raise ValueError(f"Invalid backup: unlisted directory {name}")
            return

        if name in {"manifest.json", "database.sqlite"}:
            return
        if not (name.startswith("attachments/") or name.startswith("config/")):
            raise ValueError(f"Invalid backup: unlisted file {name}")

    @staticmethod
    def _manifest_object(pairs: list[tuple[str, object]]) -> dict:
        """JSON hook that prevents duplicate keys from hiding inventory data."""
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Invalid backup: duplicate manifest key {key}")
            result[key] = value
        return result

    @classmethod
    def _read_manifest(cls, zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict:
        if info.file_size > cls._MAX_BACKUP_MANIFEST_SIZE:
            raise ValueError("Invalid backup: manifest exceeds size limit")
        try:
            payload = zf.read(info)
            manifest = json.loads(payload, object_pairs_hook=cls._manifest_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid backup: malformed manifest.json") from exc
        if not isinstance(manifest, dict):
            raise ValueError("Invalid backup: manifest must be an object")
        return manifest

    @staticmethod
    def _hash_zip_member(
        zf: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        *,
        output_path: Optional[Path] = None,
        maximum_size: int,
        total_budget: Optional[list[int]] = None,
        maximum_total_size: Optional[int] = None,
    ) -> tuple[int, str]:
        digest = hashlib.sha256()
        size = 0
        target = output_path.open("wb") if output_path is not None else None
        try:
            with zf.open(info) as member:
                while chunk := member.read(1024 * 1024):
                    size += len(chunk)
                    if size > maximum_size:
                        raise ValueError(
                            f"Invalid backup: extracted size limit exceeded for {info.filename}"
                        )
                    if total_budget is not None:
                        total_budget[0] += len(chunk)
                        if (
                            maximum_total_size is not None
                            and total_budget[0] > maximum_total_size
                        ):
                            raise ValueError(
                                "Invalid backup: streamed extracted size limit exceeded"
                            )
                    digest.update(chunk)
                    if target is not None:
                        target.write(chunk)
        finally:
            if target is not None:
                target.close()
        return size, digest.hexdigest()

    @classmethod
    def _validate_zip_members(cls, zf: zipfile.ZipFile) -> dict:
        infos = zf.infolist()
        if len(infos) > cls._MAX_BACKUP_MEMBERS:
            raise ValueError("Invalid backup: too many archive members")

        info_by_name: dict[str, zipfile.ZipInfo] = {}
        portable_names: set[str] = set()
        extracted_size = 0
        for info in infos:
            name = info.filename
            directory = info.is_dir()
            cls._validate_archive_name(name, directory=directory)
            portable_name = unicodedata.normalize("NFC", name).casefold()
            if name in info_by_name or portable_name in portable_names:
                raise ValueError(f"Invalid backup: duplicate archive member {name}")
            info_by_name[name] = info
            portable_names.add(portable_name)

            member_mode = (info.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(member_mode):
                raise ValueError(f"Invalid backup: symbolic link {name}")
            if member_mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ValueError(f"Invalid backup: special file {name}")
            if directory and member_mode not in {0, stat.S_IFDIR}:
                raise ValueError(f"Invalid backup: invalid directory type {name}")
            if directory and info.file_size:
                raise ValueError(f"Invalid backup: directory contains data {name}")
            if not directory and member_mode == stat.S_IFDIR:
                raise ValueError(f"Invalid backup: invalid file type {name}")
            if info.flag_bits & 0x1:
                raise ValueError(f"Invalid backup: encrypted member {name}")
            if info.file_size < 0 or info.file_size > cls._MAX_BACKUP_MEMBER_SIZE:
                raise ValueError(f"Invalid backup: member exceeds size limit {name}")
            if info.compress_size < 0:
                raise ValueError(f"Invalid backup: invalid compressed size {name}")
            if info.file_size >= cls._COMPRESSION_RATIO_MIN_SIZE:
                if info.compress_size == 0:
                    raise ValueError(f"Invalid backup: compression ratio too high for {name}")
                if info.file_size / info.compress_size > cls._MAX_BACKUP_COMPRESSION_RATIO:
                    raise ValueError(f"Invalid backup: compression ratio too high for {name}")
            extracted_size += info.file_size
            if extracted_size > cls._MAX_BACKUP_EXTRACTED_SIZE:
                raise ValueError("Invalid backup: total extracted size limit exceeded")

        manifest_info = info_by_name.get("manifest.json")
        if manifest_info is None or manifest_info.is_dir():
            raise ValueError("Invalid backup: missing manifest.json")
        database_info = info_by_name.get("database.sqlite")
        if database_info is None or database_info.is_dir():
            raise ValueError("Invalid backup: missing database.sqlite")

        manifest = cls._read_manifest(zf, manifest_info)
        contents = manifest.get("contents")
        if not isinstance(contents, list) or not all(isinstance(name, str) for name in contents):
            raise ValueError("Invalid backup: manifest contents must be a list of paths")
        if len({unicodedata.normalize("NFC", name).casefold() for name in contents}) != len(contents):
            raise ValueError("Invalid backup: duplicate manifest content")
        for name in contents:
            cls._validate_archive_name(name, directory=name.endswith("/"))

        inventory_present = "files" in manifest
        file_inventory = manifest.get("files")
        if inventory_present and not isinstance(file_inventory, dict):
            raise ValueError("Invalid backup: manifest files must be an object")

        archive_files = {
            name for name, info in info_by_name.items()
            if not info.is_dir() and name != "manifest.json"
        }
        directory_markers = {
            name for name, info in info_by_name.items() if info.is_dir()
        }
        content_names = set(contents)

        if not inventory_present:
            # Legacy full backups used `contents` as their only inventory.
            # Require an exact archive match, stream every member for CRC and
            # size enforcement, then synthesize an in-memory hash inventory.
            # Desktop lock/instance files are accepted for compatibility but
            # deliberately omitted from the restore inventory.
            archive_names = archive_files | directory_markers
            if content_names != archive_names:
                unlisted = sorted(archive_names - content_names)
                missing = sorted(content_names - archive_names)
                detail = unlisted[0] if unlisted else missing[0]
                label = "unlisted" if unlisted else "missing recorded"
                raise ValueError(f"Invalid backup: {label} legacy member {detail}")

            streamed_size = [manifest_info.file_size]
            synthesized_inventory = {}
            ignored_runtime_files = []
            for name in sorted(archive_files):
                size, digest = cls._hash_zip_member(
                    zf,
                    info_by_name[name],
                    maximum_size=cls._MAX_BACKUP_MEMBER_SIZE,
                    total_budget=streamed_size,
                    maximum_total_size=cls._MAX_BACKUP_EXTRACTED_SIZE,
                )
                if name in cls._TRANSIENT_RUNTIME_MEMBERS:
                    ignored_runtime_files.append(name)
                    continue
                synthesized_inventory[name] = {
                    "size": size,
                    "sha256": digest,
                }

            if "database.sqlite" not in synthesized_inventory:
                raise ValueError("Invalid backup: database.sqlite is not restorable")
            manifest = dict(manifest)
            manifest["files"] = synthesized_inventory
            manifest["_legacy_inventory_synthesized"] = True
            manifest["_legacy_ignored_runtime_files"] = ignored_runtime_files
            return manifest

        inventory_names = set(file_inventory)
        transient_inventory = sorted(
            inventory_names & cls._TRANSIENT_RUNTIME_MEMBERS
        )
        if transient_inventory:
            raise ValueError(
                "Invalid backup: transient runtime file is not restorable "
                f"{transient_inventory[0]}"
            )
        if "database.sqlite" not in inventory_names:
            raise ValueError("Invalid backup: database.sqlite is not recorded in manifest")
        if archive_files != inventory_names:
            unlisted = sorted(archive_files - inventory_names)
            missing = sorted(inventory_names - archive_files)
            detail = unlisted[0] if unlisted else missing[0]
            label = "unlisted" if unlisted else "missing recorded"
            raise ValueError(f"Invalid backup: {label} file {detail}")
        if content_names != inventory_names | directory_markers:
            raise ValueError("Invalid backup: manifest contents do not match archive")

        streamed_size = [manifest_info.file_size]
        for name, expected in file_inventory.items():
            cls._validate_archive_name(name, directory=False)
            if not isinstance(expected, dict):
                raise ValueError(f"Invalid backup: malformed inventory for {name}")
            expected_size = expected.get("size")
            expected_digest = expected.get("sha256")
            if (
                isinstance(expected_size, bool)
                or not isinstance(expected_size, int)
                or expected_size < 0
                or not isinstance(expected_digest, str)
                or len(expected_digest) != 64
                or any(char not in "0123456789abcdef" for char in expected_digest)
            ):
                raise ValueError(f"Invalid backup: malformed inventory for {name}")
            info = info_by_name[name]
            if info.file_size != expected_size:
                raise ValueError(f"Invalid backup: size mismatch for {name}")
            size, digest = cls._hash_zip_member(
                zf,
                info,
                maximum_size=cls._MAX_BACKUP_MEMBER_SIZE,
                total_budget=streamed_size,
                maximum_total_size=cls._MAX_BACKUP_EXTRACTED_SIZE,
            )
            if size != expected_size:
                raise ValueError(f"Invalid backup: size mismatch for {name}")
            if digest != expected_digest:
                raise ValueError(f"Invalid backup: checksum mismatch for {name}")
        # Never trust internal validation markers supplied by an archive.
        manifest = dict(manifest)
        manifest.pop("_legacy_inventory_synthesized", None)
        manifest.pop("_legacy_ignored_runtime_files", None)
        return manifest

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

    def validate_database_file(self, db_path: Path) -> None:
        """Public startup/recovery validation entry point."""
        self._validate_database_file(db_path)

    def _validate_database_against_manifest(self, db_path: Path, manifest: dict) -> None:
        self._validate_database_file(db_path)
        expected_counts = (manifest.get("database") or {}).get("table_counts")
        if expected_counts is not None:
            if not isinstance(expected_counts, dict):
                raise ValueError("Invalid backup: database table counts are malformed")
            actual_counts = self._database_inventory(db_path)
            if actual_counts != expected_counts:
                raise ValueError("Invalid backup: database table counts changed")

    @classmethod
    def _extract_recorded_member(
        cls,
        zf: zipfile.ZipFile,
        manifest: dict,
        name: str,
        target: Path,
        *,
        total_budget: Optional[list[int]] = None,
    ) -> None:
        """Stream one already-approved member and verify it again while writing."""
        inventory = manifest.get("files")
        expected = inventory.get(name) if isinstance(inventory, dict) else None
        if expected is None:
            raise ValueError(f"Invalid backup: unrecorded restore member {name}")

        info = zf.getinfo(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        size, digest = cls._hash_zip_member(
            zf,
            info,
            output_path=target,
            maximum_size=cls._MAX_BACKUP_MEMBER_SIZE,
            total_budget=total_budget,
            maximum_total_size=cls._MAX_BACKUP_EXTRACTED_SIZE,
        )
        if size != expected["size"]:
            raise ValueError(f"Invalid backup: size mismatch for {name}")
        if digest != expected["sha256"]:
            raise ValueError(f"Invalid backup: checksum mismatch for {name}")

    @staticmethod
    def _database_inventory(db_path: Path) -> dict[str, int]:
        conn = sqlite3.connect(str(db_path))
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            inventory = {}
            for (name,) in tables:
                identifier = name.replace('"', '""')
                inventory[name] = int(
                    conn.execute(f'SELECT COUNT(*) FROM "{identifier}"').fetchone()[0]
                )
            return inventory
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

    def _next_backup_paths(
        self,
        output_dir: Path,
        timestamp: str,
        prefix: str = "backup",
    ) -> tuple[str, Path, Path]:
        """Return non-conflicting backup and temporary snapshot paths."""
        suffix = 0
        while True:
            backup_name = f"{prefix}_{timestamp}" if suffix == 0 else f"{prefix}_{timestamp}_{suffix:02d}"
            backup_path = output_dir / f"{backup_name}.zip"
            snapshot_path = output_dir / f".{backup_name}.sqlite"
            if not backup_path.exists() and not snapshot_path.exists():
                return backup_name, backup_path, snapshot_path
            suffix += 1

    @staticmethod
    def _add_file(
        zf: zipfile.ZipFile,
        file_path: Path,
        arcname: str,
        manifest: dict,
    ) -> None:
        digest = hashlib.sha256()
        size = 0
        with file_path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        zf.write(file_path, arcname)
        manifest["contents"].append(arcname)
        manifest["files"][arcname] = {
            "size": size,
            "sha256": digest.hexdigest(),
        }

    @classmethod
    def _add_directory(
        cls,
        zf: zipfile.ZipFile,
        source_dir: Path,
        archive_dir: str,
        manifest: dict,
        include_root: bool = False,
    ) -> None:
        """Add regular files from one data directory to a backup archive."""
        if include_root:
            root_name = f"{archive_dir}/"
            zf.writestr(root_name, b"")
            manifest["contents"].append(root_name)
        if not source_dir.exists():
            return
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            if file_path.name in cls._TRANSIENT_RUNTIME_FILES:
                continue
            arcname = f"{archive_dir}/{file_path.relative_to(source_dir)}"
            cls._add_file(zf, file_path, arcname, manifest)

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    @staticmethod
    def _secure_runtime_config(config_dir: Path) -> None:
        """Keep restored installation secrets private on POSIX systems."""
        try:
            config_dir.chmod(0o700)
        except OSError:
            pass
        for path in config_dir.rglob("*"):
            try:
                path.chmod(0o700 if path.is_dir() else 0o600)
            except OSError:
                pass

    @classmethod
    def _stage_runtime_config(
        cls,
        staged_config: Path,
        active_config: Path,
        previous_config: Path,
        moved_entries: list[str],
        installed_entries: list[str],
    ) -> None:
        """Replace restorable config entries while keeping live lock files in place."""
        active_config.mkdir(parents=True, exist_ok=True)
        previous_config.mkdir(parents=True, exist_ok=False)
        for entry in sorted(active_config.iterdir(), key=lambda path: path.name):
            if entry.name in cls._TRANSIENT_RUNTIME_FILES:
                continue
            entry.replace(previous_config / entry.name)
            moved_entries.append(entry.name)
        if not staged_config.exists():
            return
        for entry in sorted(staged_config.iterdir(), key=lambda path: path.name):
            if entry.name in cls._TRANSIENT_RUNTIME_FILES:
                raise ValueError(
                    f"Invalid backup: transient runtime file reached staging {entry.name}"
                )
            entry.replace(active_config / entry.name)
            installed_entries.append(entry.name)

    @classmethod
    def _rollback_runtime_config(
        cls,
        active_config: Path,
        previous_config: Path,
        moved_entries: list[str],
        installed_entries: list[str],
    ) -> None:
        """Undo a staged config replacement without touching live lock files."""
        for name in reversed(installed_entries):
            cls._remove_path(active_config / name)
        for name in reversed(moved_entries):
            (previous_config / name).replace(active_config / name)

    def validate_backup_archive(self, backup_path: Path) -> dict:
        """Fully validate archive checksums, SQLite integrity, FKs and row counts."""
        if not backup_path.is_file():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        with zipfile.ZipFile(backup_path, "r") as zf:
            manifest = self._validate_zip_members(zf)
            with tempfile.TemporaryDirectory(prefix="jpt_backup_validate_") as temp_dir:
                db_path = Path(temp_dir) / "database.sqlite"
                self._extract_recorded_member(
                    zf,
                    manifest,
                    "database.sqlite",
                    db_path,
                    total_budget=[0],
                )
                self._validate_database_against_manifest(db_path, manifest)
        return manifest

    def backup(
        self,
        output_dir: Path,
        actor_id: str,
        *,
        filename_prefix: str = "backup",
        manifest_extra: Optional[dict] = None,
        apply_retention: bool = True,
    ) -> dict:
        """
        Create full backup (database + attachments + runtime configuration).

        Returns backup metadata.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        output_dir.mkdir(parents=True, exist_ok=True)
        backup_name, backup_path, snapshot_path = self._next_backup_paths(
            output_dir, timestamp, filename_prefix
        )

        # Create manifest
        manifest = {
            "backup_time": datetime.utcnow().isoformat(),
            "backup_by": actor_id,
            "version": APP_VERSION,
            "contents": [],
            "files": {},
        }
        if manifest_extra:
            manifest.update(manifest_extra)

        try:
            self._write_database_snapshot(snapshot_path)
            self._validate_database_file(snapshot_path)
            manifest["database"] = {
                "integrity_check": "ok",
                "foreign_key_violations": 0,
                "table_counts": self._database_inventory(snapshot_path),
            }

            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add database
                self._add_file(zf, snapshot_path, "database.sqlite", manifest)

                # Add attachments directory
                attachments_dir = self.data_dir / "attachments" if self.data_dir else None
                if attachments_dir:
                    self._add_directory(zf, attachments_dir, "attachments", manifest)

                # Always write the directory marker so an empty runtime config
                # can be distinguished from a legacy backup without config.
                runtime_config_dir = self.data_dir / "config" if self.data_dir else None
                if runtime_config_dir:
                    self._add_directory(
                        zf,
                        runtime_config_dir,
                        "config",
                        manifest,
                        include_root=True,
                    )

                # Add manifest
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            try:
                backup_path.chmod(0o600)
            except OSError:
                pass
        finally:
            snapshot_path.unlink(missing_ok=True)

        result = {
            "backup_path": str(backup_path),
            "backup_size": backup_path.stat().st_size,
            "manifest": manifest,
        }

        # A backup is not successful until the finished archive itself passes
        # CRC, per-file digest, SQLite integrity, FK and count validation.
        self.validate_backup_archive(backup_path)
        result["validated"] = True

        # Apply backup retention policy
        cleanup_result = (
            self.cleanup_old_backups(output_dir)
            if apply_retention
            else {"deleted": 0, "kept": None, "error": None, "reason": "disabled"}
        )
        result["cleanup"] = cleanup_result

        return result

    def create_pre_upgrade_backup(
        self,
        output_dir: Path,
        actor_id: str,
        *,
        source_schema_version: int,
        target_schema_version: int,
        target_app_version: str,
    ) -> dict:
        """Create a durable, validated backup before the first schema write."""
        prefix = (
            f"pre_upgrade_schema{source_schema_version}"
            f"_to_schema{target_schema_version}"
        )
        return self.backup(
            output_dir,
            actor_id,
            filename_prefix=prefix,
            manifest_extra={
                "backup_kind": "pre_upgrade",
                "source_schema_version": source_schema_version,
                "target_schema_version": target_schema_version,
                "target_app_version": target_app_version,
            },
            apply_retention=False,
        )

    def restore_database_from_backup(
        self,
        backup_path: Path,
        *,
        preserve_current: bool = False,
    ) -> dict:
        """Atomically restore only SQLite after a failed startup migration.

        Runtime configuration and attachments are intentionally untouched: a
        schema migration writes only the database, and the desktop lock inside
        config may be open on Windows while startup is in progress. This entry
        accepts only archives created by the automatic pre-upgrade gate; a
        normal full backup must use the normal full-restore workflow.
        """
        if not self.data_dir:
            raise ValueError("Data directory not configured")
        manifest = self.validate_backup_archive(backup_path)
        if manifest.get("backup_kind") != "pre_upgrade":
            raise ValueError(
                "Recovery requires an automatic pre-upgrade backup; "
                "use the full restore workflow for ordinary backups"
            )
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        safety_db: Optional[Path] = None
        if preserve_current and self._database_path().is_file():
            safety_dir = self.data_dir / "backups"
            safety_dir.mkdir(parents=True, exist_ok=True)
            suffix = 0
            while True:
                name = (
                    f"pre_recovery_current_{timestamp}"
                    if suffix == 0
                    else f"pre_recovery_current_{timestamp}_{suffix:02d}"
                )
                candidate = safety_dir / f"{name}.sqlite"
                staged_safety = safety_dir / f".{name}.tmp.sqlite"
                if not candidate.exists() and not staged_safety.exists():
                    safety_db = candidate
                    break
                suffix += 1

            snapshot_validated = False
            try:
                self._write_database_snapshot(staged_safety)
                self._validate_database_file(staged_safety)
                snapshot_validated = True
                staged_safety.chmod(0o600)
                staged_safety.replace(safety_db)
                # Validate the durable final path before touching active data.
                self._validate_database_file(safety_db)
            except Exception as exc:
                # Remove only an unvalidated temporary file created by this
                # attempt. A validated copy is retained even if chmod, rename,
                # or the final verification fails; never delete the sole
                # forensic recovery point while reporting an aborted restore.
                if not snapshot_validated:
                    staged_safety.unlink(missing_ok=True)
                raise RuntimeError(
                    "Current database could not be preserved; recovery was not started"
                ) from exc
        staged_db = self.data_dir / f".database_upgrade_rollback_{timestamp}.sqlite"
        previous_db = self.data_dir / f".database_failed_upgrade_{timestamp}.sqlite"
        db_path = self._database_path()
        installed_replacement = False
        moved_original = False
        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                manifest = self._validate_zip_members(zf)
                self._extract_recorded_member(
                    zf,
                    manifest,
                    "database.sqlite",
                    staged_db,
                    total_budget=[0],
                )
            self._validate_database_against_manifest(staged_db, manifest)
            close_db()
            if db_path.exists():
                db_path.replace(previous_db)
                moved_original = True
            staged_db.replace(db_path)
            installed_replacement = True
            self._validate_database_against_manifest(db_path, manifest)
        except Exception as restore_error:
            rollback_errors = []
            try:
                if installed_replacement:
                    self._remove_path(db_path)
                if moved_original:
                    previous_db.replace(db_path)
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
            if rollback_errors:
                raise RuntimeError(
                    "Database rollback failed and the previous database could not be restored: "
                    + "; ".join(rollback_errors)
                ) from restore_error
            raise
        finally:
            staged_db.unlink(missing_ok=True)
        previous_db.unlink(missing_ok=True)
        return {
            "restored": True,
            "source_backup": str(backup_path),
            "safety_database": str(safety_db) if safety_db else None,
            "manifest": manifest,
        }

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

    def restore(
        self,
        backup_path: Path,
        actor_id: str,
        *,
        create_pre_restore: bool = True,
    ) -> dict:
        """
        Restore from backup (full replacement).

        Returns restore report.
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        if not self.data_dir:
            raise ValueError("Data directory not configured")

        # Validate backup
        manifest = self.validate_backup_archive(backup_path)

        # Create pre-restore backup
        pre_restore = None
        pre_restore_error = None
        if create_pre_restore and self._database_path().exists():
            try:
                pre_restore = self.backup(
                    self.data_dir / "backups",
                    actor_id,
                    apply_retention=False,
                )
            except Exception as exc:
                raise RuntimeError(
                    "Current data could not be preserved; restore was not started"
                ) from exc
            if not pre_restore.get("validated"):
                raise RuntimeError(
                    "Current data could not be preserved; restore was not started"
                )

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        stage_dir = Path(tempfile.mkdtemp(prefix=".restore_stage_", dir=self.data_dir))
        old_db_path = self.data_dir / f".database_before_restore_{timestamp}.sqlite"
        old_attachments_dir = self.data_dir / f".attachments_before_restore_{timestamp}"
        old_config_dir = self.data_dir / f".config_before_restore_{timestamp}"
        restore_succeeded = False

        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                # Re-validate in the same open archive used for extraction so
                # a replaced upload cannot bypass the first validation pass.
                manifest = self._validate_zip_members(zf)
                inventory = manifest.get("files")
                recorded_names = (
                    sorted(inventory)
                    if isinstance(inventory, dict)
                    else ["database.sqlite"]
                )
                extracted_budget = [0]
                for name in recorded_names:
                    target = stage_dir.joinpath(*PurePosixPath(name).parts)
                    self._extract_recorded_member(
                        zf,
                        manifest,
                        name,
                        target,
                        total_budget=extracted_budget,
                    )

                # Restore runtime configuration only when the validated
                # archive explicitly records restorable config content.
                restore_config = (
                    "config/" in set(manifest["contents"])
                    or any(name.startswith("config/") for name in recorded_names)
                )
                legacy_inventory = bool(
                    manifest.get("_legacy_inventory_synthesized")
                )
                # A database-only legacy archive means exactly that: preserve
                # both attachments and runtime configuration. Any richer
                # legacy archive, and every current full backup, keeps full
                # replacement semantics for attachments.
                restore_attachments = (
                    not legacy_inventory
                    or set(manifest["contents"]) != {"database.sqlite"}
                )

            staged_db = stage_dir / "database.sqlite"
            staged_attachments = stage_dir / "attachments"
            staged_config = stage_dir / "config"
            self._validate_database_against_manifest(staged_db, manifest)

            db_path = self._database_path()
            attachments_dir = self.data_dir / "attachments"
            config_dir = self.data_dir / "config"

            close_db()
            moved_original = {"database": False, "attachments": False}
            installed_replacement = {"database": False, "attachments": False}
            moved_config_entries: list[str] = []
            installed_config_entries: list[str] = []
            try:
                if db_path.exists():
                    db_path.replace(old_db_path)
                    moved_original["database"] = True
                if restore_attachments and attachments_dir.exists():
                    attachments_dir.replace(old_attachments_dir)
                    moved_original["attachments"] = True

                staged_db.replace(db_path)
                installed_replacement["database"] = True
                if restore_attachments:
                    if staged_attachments.exists():
                        staged_attachments.replace(attachments_dir)
                    else:
                        attachments_dir.mkdir(parents=True, exist_ok=True)
                    installed_replacement["attachments"] = True
                if restore_config:
                    self._stage_runtime_config(
                        staged_config,
                        config_dir,
                        old_config_dir,
                        moved_config_entries,
                        installed_config_entries,
                    )
                    self._secure_runtime_config(config_dir)
                self._validate_database_against_manifest(db_path, manifest)
            except Exception as restore_error:
                rollback_errors = []
                if restore_config and old_config_dir.exists():
                    try:
                        self._rollback_runtime_config(
                            config_dir,
                            old_config_dir,
                            moved_config_entries,
                            installed_config_entries,
                        )
                    except Exception as rollback_error:
                        rollback_errors.append(f"config: {rollback_error}")
                paths = (
                    (attachments_dir, old_attachments_dir, "attachments"),
                    (db_path, old_db_path, "database"),
                )
                for current, previous, label in paths:
                    if label == "attachments" and not restore_attachments:
                        continue
                    try:
                        if moved_original[label] or installed_replacement[label]:
                            self._remove_path(current)
                        if moved_original[label]:
                            previous.replace(current)
                    except Exception as rollback_error:
                        rollback_errors.append(f"{label}: {rollback_error}")
                if rollback_errors:
                    details = "; ".join(rollback_errors)
                    raise RuntimeError(
                        f"Restore failed and rollback was incomplete ({details})"
                    ) from restore_error
                raise
            restore_succeeded = True
        finally:
            if stage_dir.exists():
                shutil.rmtree(stage_dir)
            if restore_succeeded:
                self._remove_path(old_db_path)
                self._remove_path(old_attachments_dir)
                self._remove_path(old_config_dir)

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
