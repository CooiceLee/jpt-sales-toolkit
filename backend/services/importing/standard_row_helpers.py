"""Header, blank-row, and member-token helpers for standard tables."""

from __future__ import annotations

from typing import Dict

from .exceptions import UnsupportedWorkbookError
from .models import Row, Table
from .standard_contract import machine_field


def headers_for(row: Row, table: Table, start_col: int, end_col: int) -> Dict[int, str]:
    result: Dict[int, str] = {}
    for offset, column in enumerate(range(start_col, end_col + 1)):
        fallback = table.columns[offset] if offset < len(table.columns) else ""
        field = machine_field(row.value(column)) or machine_field(fallback)
        if not field:
            raise UnsupportedWorkbookError(
                f"Table '{table.name}' has a header without a machine field id at column {column}"
            )
        if field in result.values():
            raise UnsupportedWorkbookError(f"Table '{table.name}' has duplicate machine header: {field}")
        result[column] = field
    return result


def record_member(members: Dict[str, dict], token: str, raw_name: str, ref: dict) -> None:
    item = members.setdefault(token, {
        "username_token": token, "role_hint": "unknown", "raw_names": [],
        "occurrences": 0, "source_refs": [],
    })
    if raw_name not in item["raw_names"]:
        item["raw_names"].append(raw_name)
    item["occurrences"] += 1
    if ref not in item["source_refs"]:
        item["source_refs"].append(ref)


def has_values(row: Row, start: int, end: int) -> bool:
    return any(not is_missing(row.value(column)) for column in range(start, end + 1))


def is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
