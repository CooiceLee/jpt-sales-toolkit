"""Bounded, extraction-free OOXML package reader."""

from __future__ import annotations

import hashlib
import io
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from .exceptions import ImportWorkbookError, UnsafeWorkbookError

MAX_WORKBOOK_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 2048
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000


class SafeXlsxArchive:
    """Read OOXML members without extracting attacker-controlled paths."""

    def __init__(self, content: bytes, filename: str):
        if not isinstance(content, bytes):
            raise ImportWorkbookError("Workbook content must be bytes")
        if not content or len(content) > MAX_WORKBOOK_BYTES:
            raise UnsafeWorkbookError("Workbook is empty or exceeds the 64 MB limit")
        self.filename = filename or "import.xlsx"
        self.source_hash = hashlib.sha256(content).hexdigest()
        try:
            self._zip = ZipFile(io.BytesIO(content))
        except BadZipFile as exc:
            raise ImportWorkbookError("File is not a valid XLSX/OOXML package") from exc
        self._validate_members()

    def _validate_members(self) -> None:
        members = self._zip.infolist()
        if len(members) > MAX_MEMBERS:
            raise UnsafeWorkbookError("Workbook contains too many package members")
        total = 0
        for member in members:
            name = member.filename.replace("\\", "/")
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise UnsafeWorkbookError(f"Unsafe OOXML member path: {name}")
            if member.file_size > MAX_MEMBER_BYTES:
                raise UnsafeWorkbookError(f"OOXML member exceeds size limit: {name}")
            total += member.file_size
            compressed = max(member.compress_size, 1)
            if member.file_size / compressed > MAX_COMPRESSION_RATIO:
                raise UnsafeWorkbookError(f"Suspicious OOXML compression ratio: {name}")
        if total > MAX_TOTAL_BYTES:
            raise UnsafeWorkbookError("Workbook expands beyond the 128 MB limit")

    def names(self) -> set[str]:
        return set(self._zip.namelist())

    def read(self, name: str, required: bool = True) -> bytes:
        normalized = name.lstrip("/")
        if normalized not in self.names():
            if required:
                raise ImportWorkbookError(f"Required OOXML part is missing: {normalized}")
            return b""
        data = self._zip.read(normalized)
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise UnsafeWorkbookError(f"DTD/entity declarations are not allowed: {normalized}")
        return data
