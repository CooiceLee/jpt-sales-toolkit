"""Cross-table preflight validation for standard import workbooks."""

from __future__ import annotations

from .standard_business_rules import validate_business_rules
from .standard_validation_common import add_issue

ACTIONS = {"UPSERT", "ARCHIVE", "RESTORE", "SKIP"}
ENUMS = {
    ("leads", "sales_stage"): {"New", "Assigned", "Following", "Quoted", "Won", "Lost"},
    ("leads", "fulfillment_status"): {"Not Started", "In Progress", "Completed"},
    ("assignments", "assignment_type"): {"collaborator", "watcher"},
    ("activities", "activity_type"): {"follow_up", "comment"},
    ("activities", "visibility"): {"all", "internal", "owner_only"},
    ("activities", "status"): {"pending", "responded", "completed", "scheduled"},
    ("pre_sales_tasks", "status"): {"Open", "In Progress", "Completed", "Cancelled"},
    ("after_sales_tasks", "issue_type"): {"Technical", "Quality", "Delivery", "Other"},
    ("after_sales_tasks", "status"): {"Open", "In Progress", "Resolved", "Closed"},
}


def validate_standard(canonical: dict) -> None:
    entities, issues = canonical["entities"], canonical["issues"]
    _validate_actions_and_enums(entities, issues)
    _validate_unique_keys(entities, issues)
    _validate_references(entities, issues)
    validate_business_rules(entities, issues)


def _validate_actions_and_enums(entities: dict, issues: list[dict]) -> None:
    for kind, rows in entities.items():
        for row in rows:
            action = str(row.get("action") or "").upper()
            if action not in ACTIONS:
                add_issue(issues, "blocker", "invalid_action", row,
                          f"Action must be one of: {', '.join(sorted(ACTIONS))}", "action", action)
            else:
                row["action"] = action
            if action != "UPSERT":
                continue
            for (enum_kind, field), values in ENUMS.items():
                value = row.get(field)
                if kind == enum_kind and value not in (None, "") and value not in values:
                    add_issue(issues, "blocker", "invalid_enum", row,
                              f"Invalid {field}: {value}", field, value)


def _validate_unique_keys(entities: dict, issues: list[dict]) -> None:
    for rows in entities.values():
        seen: set[str] = set()
        for row in rows:
            key = row["external_key"]
            if key in seen:
                add_issue(issues, "blocker", "duplicate_external_key", row,
                          f"Duplicate external key: {key}")
            seen.add(key)


def _validate_references(entities: dict, issues: list[dict]) -> None:
    customers = {row["external_key"] for row in entities["customers"]}
    leads = {row["external_key"] for row in entities["leads"]}
    for kind in ("aliases", "contacts", "leads"):
        for row in entities[kind]:
            if row.get("action") != "UPSERT":
                continue
            if row.get("customer_key") not in customers:
                add_issue(issues, "blocker", "broken_reference", row,
                          "customer_key does not reference a customer in this workbook",
                          "customer_key", row.get("customer_key"))
    for kind in ("assignments", "activities", "pre_sales_tasks", "after_sales_tasks"):
        for row in entities[kind]:
            if row.get("action") != "UPSERT":
                continue
            if row.get("lead_key") not in leads:
                add_issue(issues, "blocker", "broken_reference", row,
                          "lead_key does not reference a lead in this workbook",
                          "lead_key", row.get("lead_key"))
