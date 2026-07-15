"""Normalize the small, explicit manual-resolution contract."""

from __future__ import annotations

import json

from .errors import SpreadsheetImportError


def parse_resolutions(value: object) -> dict:
    if value in (None, ""):
        raw = {}
    elif isinstance(value, str):
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SpreadsheetImportError(
                "invalid_resolutions", "resolutions must be valid JSON", 400
            ) from exc
    elif isinstance(value, dict):
        raw = value
    else:
        raise SpreadsheetImportError("invalid_resolutions", "resolutions must be an object", 400)
    if not isinstance(raw, dict):
        raise SpreadsheetImportError("invalid_resolutions", "resolutions must be an object", 400)
    return {
        "member_mappings": _mapping(raw.get("member_mappings")),
        "customer_mappings": _mapping(raw.get("customer_mappings")),
        "excluded_records": _exclusions(raw.get("excluded_records")),
    }


def _mapping(value: object) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return {str(key).strip(): str(item).strip() for key, item in value.items() if item}
    if isinstance(value, list):
        result = {}
        for item in value:
            if not isinstance(item, dict):
                raise SpreadsheetImportError("invalid_resolutions", "mapping entries must be objects", 400)
            key = item.get("source_token") or item.get("external_key") or item.get("key")
            target = item.get("user_id") or item.get("customer_id") or item.get("target")
            if key and target:
                result[str(key).strip()] = str(target).strip()
        return result
    raise SpreadsheetImportError("invalid_resolutions", "mappings must be an object or list", 400)


def _exclusions(value: object) -> set[str]:
    if value in (None, ""):
        return set()
    if not isinstance(value, list):
        raise SpreadsheetImportError("invalid_resolutions", "excluded_records must be a list", 400)
    return {str(item).strip() for item in value if str(item).strip()}


def is_excluded(item: dict, excluded: set[str]) -> bool:
    if not excluded:
        return False
    # Aggregated leads can reference several source rows. Excluding a secondary
    # task row must not discard the valid opportunity created by its primary row.
    refs = [item.get("source_ref")]
    keys = {str(item.get("external_key") or "")}
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        keys.update({
            str(ref.get("record_key") or ""),
            f"{ref.get('sheet')}:{ref.get('row')}",
        })
    return bool(keys & excluded)
