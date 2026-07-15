"""Convert parser and mapping diagnostics into UI quality issues."""

from __future__ import annotations

PARTIAL_REQUIRED_FIELDS = {
    "leads": {"sales_stage"},
    "activities": {"activity_type", "occurred_at", "content", "visibility"},
    "pre_sales_tasks": {"status"},
    "after_sales_tasks": {"issue_type", "status", "issue_description"},
}


def parser_issues(canonical: dict, excluded: set[str], entities: dict,
                  bound_keys: set[tuple[str, str]]) -> list[dict]:
    key_types = {item.get("external_key"): kind
                 for kind, items in entities.items() for item in items}
    trace_targets = _trace_targets(canonical.get("source_trace") or [])
    result = []
    for raw in canonical.get("issues") or []:
        ref = raw.get("source_ref") or {}
        record_key = str(ref.get("record_key") or "")
        identities = {str(raw.get("entity_key") or ""), record_key,
                      f"{ref.get('sheet')}:{ref.get('row')}"}
        if identities & excluded:
            continue
        external_key = raw.get("entity_key")
        if not external_key:
            external_key = _preferred_target(trace_targets.get(record_key, []), key_types)
        kind = key_types.get(external_key)
        if _bound_partial_omission(raw, kind, external_key, bound_keys):
            continue
        result.append({
            "severity": "error" if raw.get("severity") in {"blocker", "error"}
            else raw.get("severity", "warning"),
            "code": raw.get("code", "source_issue"),
            "entity_type": kind, "external_key": external_key,
            "field": raw.get("field"), "message": raw.get("message", "Source record needs review"),
            "raw_value": raw.get("raw_value"), "source_ref": ref,
            "source_record_key": record_key or None,
        })
    return result


def _bound_partial_omission(raw, kind, external_key, bound_keys):
    return (
        raw.get("code") == "missing_required_field"
        and raw.get("field") in PARTIAL_REQUIRED_FIELDS.get(kind, set())
        and (kind, external_key) in bound_keys
    )


def mapping_issues(members: list[dict], customers: list[dict]) -> list[dict]:
    result = [{
        "severity": "error", "code": item.get("code") or "unresolved_member",
        "entity_type": "member", "external_key": item["source_name"], "field": item["purpose"],
        "message": item.get("message") or "Member mapping requires Leader confirmation",
    } for item in members if item["status"] == "blocker"]
    result.extend({
        "severity": "error", "code": "ambiguous_customer", "entity_type": "customers",
        "external_key": item["external_key"], "field": "customer_mapping",
        "message": item.get("message") or "Customer mapping requires Leader confirmation",
    } for item in customers if item["status"] == "blocker")
    return result


def _trace_targets(traces: list[dict]) -> dict[str, list[str]]:
    result = {}
    for trace in traces:
        record_key = str((trace.get("source_ref") or {}).get("record_key") or "")
        if record_key:
            result[record_key] = list(trace.get("target_entity_keys") or [])
    return result


def _preferred_target(targets: list[str], key_types: dict[str, str]):
    active = [key for key in targets if key in key_types]
    for kind in ("leads", "pre_sales_tasks", "after_sales_tasks", "customers"):
        match = next((key for key in active if key_types[key] == kind), None)
        if match:
            return match
    return active[0] if active else None
