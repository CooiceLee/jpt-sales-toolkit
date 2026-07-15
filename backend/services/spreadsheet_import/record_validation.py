"""Cross-entity and database-enum checks for canonical records."""

from .member_matching import resolution_name
from .persistence_common import CLEAR_TOKEN

ENUMS = {
    ("leads", "sales_stage"): {"New", "Assigned", "Following", "Quoted", "Won", "Lost"},
    ("leads", "fulfillment_status"): {"Not Started", "In Progress", "Completed"},
    ("leads", "service_status"): {"None", "Open", "In Progress", "Resolved", "Closed"},
    ("assignments", "assignment_type"): {"collaborator", "watcher"},
    ("pre_sales_tasks", "status"): {"Open", "In Progress", "Completed", "Cancelled"},
    ("after_sales_tasks", "status"): {"Open", "In Progress", "Resolved", "Closed"},
    ("after_sales_tasks", "issue_type"): {"Technical", "Quality", "Delivery", "Other"},
}
REQUIRED = {
    "customers": ("external_key", "display_name"),
    "aliases": ("external_key", "customer_key", "alias_name"),
    "contacts": ("external_key", "customer_key", "name"),
    "leads": ("external_key", "customer_key", "title"),
    "assignments": ("external_key", "lead_key", "assignment_type"),
    "activities": ("external_key", "lead_key"),
    "pre_sales_tasks": ("external_key", "lead_key"),
    "after_sales_tasks": ("external_key", "lead_key"),
}


def record_issues(entities: dict, members: dict, customers: dict) -> list[dict]:
    result = []
    customer_keys, lead_keys = set(customers), _keys(entities["leads"])
    contact_keys = _keys(entities["contacts"])
    for kind, items in entities.items():
        for item in items:
            action = str(item.get("action") or "UPSERT").upper()
            if action not in {"UPSERT", "ARCHIVE", "RESTORE"}:
                result.append(_issue("invalid_action", kind, item, "action", "Unsupported import action"))
            if action == "UPSERT":
                result.extend(_required(kind, item))
                result.extend(_enums(kind, item))
                result.extend(_booleans(kind, item))
    for lead in entities["leads"]:
        if not _is_upsert(lead):
            continue
        owner = resolution_name(lead, "owner")
        if (owner, "owner") not in members:
            pass  # resolve_members already supplies candidates and the blocking issue.
        if lead.get("customer_key") not in customer_keys:
            result.append(_bad_ref("leads", lead, "customer_key", "customer"))
        primary = lead.get("primary_contact_key")
        if primary and primary != CLEAR_TOKEN and primary not in contact_keys:
            result.append(_issue(
                "unresolved_primary_contact", "leads", lead, "primary_contact_key",
                "Primary contact was excluded or could not be resolved; import will leave it unset",
                "warning",
            ))
    for kind in ("contacts", "aliases"):
        for item in entities[kind]:
            if not _is_upsert(item):
                continue
            if item.get("customer_key") not in customer_keys:
                result.append(_bad_ref(kind, item, "customer_key", "customer"))
    for kind in ("assignments", "activities", "pre_sales_tasks", "after_sales_tasks"):
        for item in entities[kind]:
            if not _is_upsert(item):
                continue
            if item.get("lead_key") not in lead_keys:
                result.append(_bad_ref(kind, item, "lead_key", "lead"))
    for item in entities["assignments"]:
        if not _is_upsert(item):
            continue
        purpose = item.get("assignment_type") or "collaborator"
        token = resolution_name(item, purpose) if purpose in {"collaborator", "watcher"} else ""
        if token and (token, purpose) not in members:
            pass  # resolve_members owns the actionable mapping error.
    return result


def _required(kind: str, item: dict) -> list[dict]:
    return [_issue("missing_required_field", kind, item, field, f"{field} is required")
            for field in REQUIRED[kind] if item.get(field) in (None, "", CLEAR_TOKEN)]


def _enums(kind: str, item: dict) -> list[dict]:
    result = []
    for (target_kind, field), allowed in ENUMS.items():
        value = item.get(field)
        if target_kind == kind and value not in (None, "", CLEAR_TOKEN) and value not in allowed:
            result.append(_issue("invalid_enum", kind, item, field, f"Invalid {field}: {value}"))
    return result


def _booleans(kind: str, item: dict) -> list[dict]:
    fields = {"customers": ("geocode_locked",), "contacts": ("is_primary",)}.get(kind, ())
    allowed = {True, False, 0, 1, "0", "1", "true", "false", "yes", "no", "y", "n",
               CLEAR_TOKEN.casefold()}
    result = []
    for field in fields:
        value = item.get(field)
        normalized = value.casefold() if isinstance(value, str) else value
        if value not in (None, "") and normalized not in allowed:
            result.append(_issue("invalid_boolean", kind, item, field,
                                 f"Invalid boolean value: {value}"))
    return result


def _bad_ref(kind, item, field, target):
    return _issue(f"unknown_{target}_reference", kind, item, field,
                  f"Record refers to an excluded or unknown {target}")


def _issue(code, kind, item, field, message, severity="error"):
    ref = item.get("source_ref") or {}
    return {"severity": severity, "code": code, "entity_type": kind,
            "external_key": item.get("external_key"), "field": field, "message": message,
            "source_ref": ref, "source_record_key": ref.get("record_key")}


def _keys(items: list[dict]) -> set[str]:
    return {item.get("external_key") for item in items}


def _is_upsert(item: dict) -> bool:
    return str(item.get("action") or "UPSERT").upper() == "UPSERT"
