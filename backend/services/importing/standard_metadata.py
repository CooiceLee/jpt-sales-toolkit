"""Read the protected metadata contract from a standard workbook."""

from __future__ import annotations

from typing import Dict

from .keys import clean_text
from .models import Table, Workbook
from .standard_contract import machine_field, range_bounds


def read_metadata(workbook: Workbook) -> Dict[str, str]:
    table = workbook.tables.get("tbl_metadata")
    if table:
        metadata = _from_table(workbook, table)
        if metadata:
            return metadata
    for name in ("说明与元数据", "Metadata", "元数据"):
        sheet = workbook.sheets.get(name)
        if not sheet:
            continue
        metadata: Dict[str, str] = {}
        for number in sorted(sheet.rows):
            key = clean_text(sheet.row(number).value(1)).casefold()
            value = clean_text(sheet.row(number).value(2))
            if key in {"format_version", "dataset_id", "timezone", "generated_at"} and value:
                metadata[key] = value
        if metadata:
            return metadata
    return {}


def _from_table(workbook: Workbook, table: Table) -> Dict[str, str]:
    sheet = workbook.sheets[table.sheet_name]
    start_col, start_row, end_col, end_row = range_bounds(table.ref)
    header = sheet.row(start_row)
    fields = [machine_field(header.value(column)) or machine_field(name)
              for column, name in zip(range(start_col, end_col + 1), table.columns)]
    if "key" not in fields or "value" not in fields:
        return {}
    key_column = start_col + fields.index("key")
    value_column = start_col + fields.index("value")
    result: Dict[str, str] = {}
    for number in range(start_row + 1, end_row + 1):
        key = clean_text(sheet.row(number).value(key_column)).casefold()
        value = clean_text(sheet.row(number).value(value_column))
        if key and value:
            result[key] = value
    return result
