"""JPT-XLSX-1.0 standard workbook adapter."""

from __future__ import annotations

from collections import Counter
import uuid
from typing import Optional

from .exceptions import UnsupportedWorkbookError
from .models import Workbook
from .standard_contract import TABLE_SPECS
from .standard_metadata import read_metadata
from .standard_rows import parse_entity_table
from .standard_validation import validate_standard


def is_standard_workbook(workbook: Workbook) -> bool:
    metadata = read_metadata(workbook)
    return metadata.get("format_version", "").startswith("JPT-XLSX-") or any(
        name in workbook.tables for name in TABLE_SPECS
    )


def convert_standard_workbook(workbook: Workbook) -> dict:
    metadata = read_metadata(workbook)
    version = metadata.get("format_version")
    if version != "JPT-XLSX-1.0":
        raise UnsupportedWorkbookError(
            f"Unsupported or missing format_version; expected JPT-XLSX-1.0, got {version or 'empty'}"
        )
    dataset_id = _dataset_id(metadata.get("dataset_id"))
    missing_tables = [name for name in TABLE_SPECS if name not in workbook.tables]
    if missing_tables:
        raise UnsupportedWorkbookError(
            "JPT-XLSX-1.0 workbook is missing Excel tables: " + ", ".join(missing_tables)
        )

    entities = {spec.entity_name: [] for spec in TABLE_SPECS.values()}
    issues: list[dict] = []
    traces: list[dict] = []
    members: dict[str, dict] = {}
    source_rows: dict[str, int] = {}
    for table_name, spec in TABLE_SPECS.items():
        table = workbook.tables[table_name]
        rows, table_traces = parse_entity_table(
            workbook, table, spec, dataset_id, issues, members,
        )
        entities[spec.entity_name].extend(rows)
        traces.extend(table_traces)
        source_rows[table_name] = len(rows)

    canonical = {
        "format": "JPT-XLSX-1.0-canonical", "dataset_id": dataset_id,
        "source_hash": workbook.source_hash,
        "source": {
            "filename": workbook.source_name, "kind": "JPT-XLSX-1.0",
            "timezone": metadata.get("timezone") or "Asia/Shanghai",
        },
        "entities": entities, "source_trace": traces, "issues": issues,
        "member_name_tokens": sorted(members.values(), key=lambda item: item["username_token"]),
        "summary": {},
    }
    validate_standard(canonical)
    canonical["summary"] = _summary(source_rows, entities, traces, issues)
    return canonical


def _dataset_id(value: Optional[str]) -> str:
    try:
        return str(uuid.UUID(str(value or "")))
    except ValueError as exc:
        raise UnsupportedWorkbookError(
            "JPT-XLSX-1.0 metadata requires dataset_id as a UUID"
        ) from exc


def _summary(source_rows: dict, entities: dict, traces: list[dict], issues: list[dict]) -> dict:
    issue_counts = Counter(item["severity"] for item in issues)
    style_counts = Counter(item["style_class"] for item in traces)
    return {
        "source_rows": source_rows, "total_source_rows": sum(source_rows.values()),
        "entity_counts": {name: len(rows) for name, rows in entities.items()},
        "issues": dict(issue_counts), "style_rows": dict(style_counts),
        "can_import": issue_counts.get("blocker", 0) == 0,
    }
