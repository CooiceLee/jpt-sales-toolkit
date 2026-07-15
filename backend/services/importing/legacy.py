"""Verified legacy Europe workbook adapter."""

from __future__ import annotations

from .exceptions import UnsupportedWorkbookError
from .legacy_aftersales import convert_aftersales
from .legacy_builder import CanonicalBuilder
from .legacy_constants import LEGACY_SHEETS
from .legacy_potential import convert_potential
from .legacy_presales import convert_presales
from .legacy_won import convert_won
from .models import Workbook

HEADER_SIGNATURES = {
    "潜在商业机会": ((1, "序号"), (2, "业务名称"), (4, "潜在客户名称")),
    "售前（技术问题）": ((1, "序号"), (3, "业务内容详述"), (4, "客户名称")),
    "赢单": ((1, "序号"), (3, "合同内容"), (5, "客户名称")),
    "售后": ((1, "序号"), (3, "售后内容"), (4, "客户名称")),
}


def is_legacy_workbook(workbook: Workbook) -> bool:
    return all(name in workbook.sheets for name in LEGACY_SHEETS)


def convert_legacy_workbook(workbook: Workbook) -> dict:
    _validate_headers(workbook)
    builder = CanonicalBuilder(workbook)
    convert_potential(builder)
    convert_presales(builder)
    convert_won(builder)
    convert_aftersales(builder)
    _trace_exclusions(builder)
    return builder.finalize()


def _validate_headers(workbook: Workbook) -> None:
    for sheet_name, expected in HEADER_SIGNATURES.items():
        sheet = workbook.sheets[sheet_name]
        actual = {column: str(sheet.row(1).value(column) or "").strip()
                  for column, _ in expected}
        missing = [label for column, label in expected if actual[column] != label]
        if missing:
            raise UnsupportedWorkbookError(
                f"Legacy sheet '{sheet_name}' header mismatch; missing: {', '.join(missing)}"
            )


def _trace_exclusions(builder: CanonicalBuilder) -> None:
    exclusions = {
        "潜在商业机会": {2: "excluded_example", 246: "excluded_instruction",
                         247: "excluded_instruction", 248: "excluded_instruction"},
        "售前（技术问题）": {2: "excluded_example"},
        "赢单": {160: "excluded_pollution", 161: "excluded_embedded_template",
                  162: "excluded_example"},
        "售后": {2: "excluded_example"},
    }
    for sheet_name, rows in exclusions.items():
        sheet = builder.workbook.sheets[sheet_name]
        for row_number, disposition in rows.items():
            row = sheet.row(row_number)
            if row.nonempty():
                builder.add_trace(sheet_name, row, disposition, {}, [])
            if disposition == "excluded_pollution":
                ref = builder.source_ref(sheet_name, row_number)
                builder.add_issue("warning", "excluded_pollution", ref,
                                  "Stray copied value was excluded outside the verified data boundary")
