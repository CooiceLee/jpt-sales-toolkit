"""Encode and expose lead fields stored in ``leads.extra_json``."""

from __future__ import annotations

import json
from typing import Any, Optional


EXTRA_JSON_FIELDS = (
    "special_requirements",
    "potential_needs",
    "products_detail",
)


def parse_extra_json(value: Any) -> dict:
    """Return a JSON-object value without leaking malformed storage errors."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def merge_extra_fields(data: dict, current_extra_json: Optional[str] = None) -> dict:
    """Move public extra fields into the existing JSON object without data loss."""
    result = dict(data)
    has_stored_value = "extra_json" in result
    stored_value = result.pop("extra_json", current_extra_json)
    extra = parse_extra_json(stored_value)
    touched = has_stored_value

    for field in EXTRA_JSON_FIELDS:
        if field not in result:
            continue
        touched = True
        value = result.pop(field)
        if value is None or value == "":
            extra.pop(field, None)
        else:
            extra[field] = value

    if touched:
        result["extra_json"] = (
            json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
            if extra else None
        )
    return result


def expose_extra_fields(lead: dict) -> dict:
    """Expose supported JSON-backed fields as stable API properties."""
    extra = parse_extra_json(lead.get("extra_json"))
    for field in EXTRA_JSON_FIELDS:
        lead[field] = extra.get(field)
    return lead
