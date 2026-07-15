"""Public spreadsheet-import parsing seam."""

from __future__ import annotations

from .exceptions import (ImportWorkbookError, UnsafeWorkbookError,
                         UnsupportedWorkbookError)
from .legacy import convert_legacy_workbook, is_legacy_workbook
from .preflight import build_preflight_report
from .standard import convert_standard_workbook, is_standard_workbook
from .workbook import read_workbook


def parse_import_workbook(content: bytes, filename: str) -> dict:
    """Parse a supported XLSX into non-mutating canonical import entities."""
    workbook = read_workbook(content, filename)
    if is_legacy_workbook(workbook):
        return convert_legacy_workbook(workbook)
    if is_standard_workbook(workbook):
        return convert_standard_workbook(workbook)
    raise UnsupportedWorkbookError(
        "Unsupported workbook. Expected JPT-XLSX-1.0 Excel tables or the verified "
        f"legacy four-sheet workbook; found sheets: {', '.join(workbook.sheets)}"
    )


def preflight_import_workbook(content: bytes, filename: str) -> dict:
    """Parse a workbook and return its non-mutating validation projection."""
    return build_preflight_report(parse_import_workbook(content, filename))


__all__ = [
    "ImportWorkbookError", "UnsafeWorkbookError", "UnsupportedWorkbookError",
    "parse_import_workbook", "preflight_import_workbook", "build_preflight_report",
]
