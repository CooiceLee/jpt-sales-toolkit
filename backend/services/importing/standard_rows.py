"""Convert one standard Excel table into canonical import rows."""

from __future__ import annotations

from typing import Dict, List, Tuple

from .dates import parse_excel_date, parse_excel_datetime
from .exceptions import UnsupportedWorkbookError
from .keys import clean_text, stable_external_key
from .models import Row, Table, Workbook
from .standard_contract import TOKEN_RENAMES, TableSpec, range_bounds
from .standard_row_helpers import headers_for, has_values, is_missing, record_member
from .standard_trace import build_standard_trace

DATETIME_FIELDS = {"occurred_at"}
DATE_FIELDS = {
    "inquiry_date", "quotation_date", "po_date", "response_date", "next_action_date",
    "request_date", "issue_date", "due_date", "expected_close_date",
}


def parse_entity_table(workbook: Workbook, table: Table, spec: TableSpec, dataset_id: str,
                       issues: list[dict], members: Dict[str, dict]) -> Tuple[List[dict], List[dict]]:
    sheet = workbook.sheets[table.sheet_name]
    start_col, start_row, end_col, end_row = range_bounds(table.ref)
    headers = headers_for(sheet.row(start_row), table, start_col, end_col)
    missing_headers = [field for field in spec.required_fields if field not in headers.values()]
    if missing_headers:
        raise UnsupportedWorkbookError(
            f"Table '{table.name}' is missing machine headers: {', '.join(missing_headers)}"
        )
    entities: List[dict] = []
    traces: List[dict] = []
    for number in range(start_row + 1, end_row + 1):
        row = sheet.row(number)
        if not has_values(row, start_col, end_col):
            continue
        source_ref = {"sheet": table.sheet_name, "row": number,
                      "record_key": f"{table.name}:{number:04d}"}
        raw_data = {field: row.value(column) for column, field in headers.items()}
        canonical, raw_dates = _canonical_values(
            workbook, row, headers, source_ref, issues, members,
        )
        key_value = clean_text(raw_data.get(spec.key_field))
        external_key = key_value or stable_external_key(
            dataset_id, f"INVALID-{spec.entity_name}", table.name, number,
        )
        entity = {"external_key": external_key, "source_ref": source_ref}
        entity.update(canonical)
        action = clean_text(raw_data.get("action")).upper()
        required_fields = spec.required_fields if action in {"", "UPSERT"} else (
            "action", spec.key_field,
        )
        for required in required_fields:
            if is_missing(raw_data.get(required)):
                issues.append({
                    "severity": "blocker", "code": "missing_required_field",
                    "source_ref": source_ref, "entity_key": external_key,
                    "field": required, "message": f"Required field is empty: {required}",
                })
            elif clean_text(raw_data.get(required)).upper() == "__CLEAR__":
                issues.append({
                    "severity": "blocker", "code": "cannot_clear_required_field",
                    "source_ref": source_ref, "entity_key": external_key,
                    "field": required, "message": f"Required field cannot be cleared: {required}",
                })
        entities.append(entity)
        trace = build_standard_trace(
            row, source_ref, headers, start_col, end_col, raw_dates, external_key,
        )
        traces.append(trace)
        if row.hidden:
            issues.append({
                "severity": "warning", "code": "hidden_business_row", "source_ref": source_ref,
                "entity_key": external_key, "message": "Hidden rows are still imported",
            })
        if trace["formula_cells"]:
            issues.append({
                "severity": "blocker", "code": "formula_not_allowed", "source_ref": source_ref,
                "entity_key": external_key, "raw_value": trace["formula_cells"],
                "message": "Import tables must contain values, not formulas",
            })
    return entities, traces


def _canonical_values(workbook: Workbook, row: Row, headers: dict, source_ref: dict,
                      issues: list[dict], members: Dict[str, dict]) -> tuple[dict, dict]:
    result, raw_dates = {}, {}
    for column, field in headers.items():
        value = row.value(column)
        target = TOKEN_RENAMES.get(field, field)
        result[target] = value if value not in ("​",) else ""
        if field in TOKEN_RENAMES and not is_missing(value):
            raw_name = clean_text(value)
            token = raw_name.casefold()
            result[target] = token
            result[target.replace("_username_token", "_name_raw")] = raw_name
            record_member(members, token, raw_name, source_ref)
        if field not in DATE_FIELDS | DATETIME_FIELDS:
            continue
        if clean_text(value).upper() == "__CLEAR__":
            result[field] = "__CLEAR__"
            raw_dates[field] = "__CLEAR__"
            continue
        parser = parse_excel_datetime if field in DATETIME_FIELDS else parse_excel_date
        parsed, raw, disposition = parser(row.cell(column), workbook.date_1904)
        result[field] = parsed
        raw_dates[field] = raw
        if raw:
            result[field + "_raw"] = raw
        if raw and disposition == "preserved_unparsed":
            issues.append({
                "severity": "blocker", "code": "invalid_date", "source_ref": source_ref,
                "field": field, "raw_value": raw,
                "message": f"Date is incomplete or invalid: {raw}",
            })
    return result, raw_dates
