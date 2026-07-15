"""Public application service for parse, preflight, and commit."""

from __future__ import annotations

import hashlib
import hmac
from typing import Callable, Optional

from ...repositories.base import get_db
from .commit import commit_canonical
from .errors import ImportBlockedError, SpreadsheetImportError
from .preflight import build_preflight
from .resolutions import parse_resolutions


class SpreadsheetImportService:
    def __init__(self, conn=None, parser: Optional[Callable] = None, before_complete=None):
        self.conn = conn or get_db()
        self.parser = parser or _parse_workbook
        self.before_complete = before_complete

    def preflight(self, content: bytes, filename: str, resolutions: object, actor: dict) -> dict:
        self._require_leader(actor)
        canonical = self._parse(content, filename)
        normalized = parse_resolutions(resolutions)
        report, _ = build_preflight(self.conn, canonical, normalized)
        return report

    def commit(self, content: bytes, filename: str, resolutions: object,
               expected_source_hash: str, actor: dict) -> dict:
        self._require_leader(actor)
        canonical = self._parse(content, filename)
        if not expected_source_hash or not hmac.compare_digest(
            str(expected_source_hash), str(canonical["source_hash"])
        ):
            raise SpreadsheetImportError(
                "source_hash_mismatch",
                "The uploaded workbook changed after preflight; run preflight again",
                409,
            )
        normalized = parse_resolutions(resolutions)
        report, context = build_preflight(self.conn, canonical, normalized)
        if not report["can_commit"]:
            raise ImportBlockedError(report)
        return commit_canonical(
            self.conn, canonical, context, actor["id"], report, self.before_complete
        )

    def _parse(self, content: bytes, filename: str) -> dict:
        if not content:
            raise SpreadsheetImportError("empty_file", "Workbook is empty", 400)
        try:
            canonical = self.parser(content, filename)
        except SpreadsheetImportError:
            raise
        except ValueError as exc:
            raise SpreadsheetImportError("invalid_workbook", str(exc), 400) from exc
        required = {"format", "dataset_id", "source_hash", "entities", "issues", "summary"}
        if not isinstance(canonical, dict) or not required.issubset(canonical):
            raise SpreadsheetImportError("invalid_canonical", "Workbook parser returned invalid data", 400)
        actual_hash = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(str(canonical["source_hash"]), actual_hash):
            raise SpreadsheetImportError("invalid_source_hash", "Workbook hash validation failed", 400)
        return canonical

    def _require_leader(self, actor: dict) -> None:
        row = self.conn.execute(
            "SELECT role, is_active FROM users WHERE id = ?", (actor.get("id"),)
        ).fetchone()
        if actor.get("role") != "leader" or not row or row["role"] != "leader" or not row["is_active"]:
            raise SpreadsheetImportError(
                "leader_required", "Only an active Leader can import spreadsheets", 403
            )


def _parse_workbook(content: bytes, filename: str) -> dict:
    from ..importing import parse_import_workbook

    return parse_import_workbook(content, filename)
