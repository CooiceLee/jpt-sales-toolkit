"""Validate partial-update fields before a transaction reaches SQLite."""

from ...coordinate_validation import CoordinateValidationError, validated_coordinate_payload
from .persistence_common import CLEAR_TOKEN
from .value_normalization import boolean_value

NON_NULL_FIELDS = {
    "leads": ("sales_stage", "fulfillment_status", "service_status"),
    "activities": ("activity_type", "action_type", "visibility", "content", "summary",
                   "occurred_at", "is_formal_follow_up"),
    "pre_sales_tasks": ("status",),
    "after_sales_tasks": ("issue_type", "status", "issue_description"),
}
ACTIVITY_ENUMS = {
    "activity_type": {"follow_up", "comment", "field_change", "assignment", "system",
                      "task_update"},
    "action_type": {"follow_up", "comment", "field_change", "assignment", "system",
                    "task_update"},
    "visibility": {"all", "internal", "owner_only"},
}


def update_field_issues(entities: dict) -> list[dict]:
    result = []
    result.extend(_coordinate_issues(entities.get("customers", [])))
    for kind, fields in NON_NULL_FIELDS.items():
        for item in entities[kind]:
            if str(item.get("action") or "UPSERT").upper() != "UPSERT":
                continue
            for field in fields:
                if item.get(field) == CLEAR_TOKEN:
                    result.append(_issue(
                        "cannot_clear_required_field", kind, item, field,
                        f"Required field cannot be cleared: {field}",
                    ))
            if kind == "activities":
                result.extend(_activity_issues(item))
    return result


def _coordinate_issues(customers: list[dict]) -> list[dict]:
    result = []
    for item in customers:
        if str(item.get("action") or "UPSERT").upper() != "UPSERT":
            continue
        for field in ("lat", "lng"):
            value = item.get(field)
            if value in (None, "", CLEAR_TOKEN):
                continue
            try:
                validated_coordinate_payload({field: value})
            except CoordinateValidationError as exc:
                result.append(_issue(
                    "invalid_coordinate", "customers", item, field, str(exc),
                ))
    return result


def _activity_issues(item: dict) -> list[dict]:
    result = []
    for field, allowed in ACTIVITY_ENUMS.items():
        value = item.get(field)
        if value not in (None, "", CLEAR_TOKEN) and value not in allowed:
            result.append(_issue(
                "invalid_enum", "activities", item, field, f"Invalid {field}: {value}"
            ))
    value = item.get("is_formal_follow_up")
    if value not in (None, "", CLEAR_TOKEN):
        try:
            boolean_value(value)
        except ValueError:
            result.append(_issue(
                "invalid_boolean", "activities", item, "is_formal_follow_up",
                f"Invalid boolean value: {value}",
            ))
    return result


def _issue(code, kind, item, field, message):
    ref = item.get("source_ref") or {}
    return {
        "severity": "error", "code": code, "entity_type": kind,
        "external_key": item.get("external_key"), "field": field, "message": message,
        "source_ref": ref, "source_record_key": ref.get("record_key"),
    }
