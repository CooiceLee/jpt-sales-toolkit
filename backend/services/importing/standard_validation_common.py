"""Shared standard-workbook issue projection."""

from __future__ import annotations

from typing import Any


def add_issue(issues: list[dict], severity: str, code: str, entity: dict,
              message: str, field: str = "", raw_value: Any = None) -> None:
    item = {"severity": severity, "code": code, "source_ref": entity["source_ref"],
            "entity_key": entity["external_key"], "message": message}
    if field:
        item["field"] = field
    if raw_value not in (None, ""):
        item["raw_value"] = raw_value
    issues.append(item)
