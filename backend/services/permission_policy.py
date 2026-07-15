"""Shared field-level policy for the global Tech role."""

from __future__ import annotations

import json
from typing import Optional


TECH_SENSITIVE_LEAD_FIELDS = frozenset({
    "estimated_value",
    "deal_amount",
    "currency",
    "quotation_id",
    "quotation_date",
    "po_number",
    "po_date",
    "lost_reason_code",
    "lost_reason_text",
})
TECH_RESTRICTED_ATTACHMENT_CATEGORIES = frozenset({"quotation"})
TECH_PRE_SALES_UPDATE_FIELDS = frozenset({"status", "result_json"})
TECH_AFTER_SALES_UPDATE_FIELDS = frozenset({"status", "solution"})


def mask_lead_for_tech(lead: dict) -> dict:
    """Return a task-facing lead without commercial fields."""
    masked = dict(lead)
    for field in TECH_SENSITIVE_LEAD_FIELDS:
        masked.pop(field, None)
    return masked


def sanitize_activity_for_tech(activity: dict) -> Optional[dict]:
    """Remove commercial field-change rows and structured commercial claims."""
    if activity.get("changed_field") in TECH_SENSITIVE_LEAD_FIELDS:
        return None
    sanitized = dict(activity)
    raw_payload = sanitized.get("payload_json")
    payload = _parse_payload(raw_payload)
    if payload is not None:
        sanitized["payload_json"] = json.dumps(
            _drop_sensitive_keys(payload), ensure_ascii=False, separators=(",", ":")
        )
    elif raw_payload:
        sanitized["payload_json"] = None
    return sanitized


def _parse_payload(value) -> Optional[object]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _drop_sensitive_keys(value):
    if isinstance(value, dict):
        return {
            key: _drop_sensitive_keys(item)
            for key, item in value.items()
            if key not in TECH_SENSITIVE_LEAD_FIELDS
        }
    if isinstance(value, list):
        return [_drop_sensitive_keys(item) for item in value]
    return value
