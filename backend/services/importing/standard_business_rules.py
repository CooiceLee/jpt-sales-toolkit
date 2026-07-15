"""Customer, lead, and follow-up business checks for standard imports."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .keys import normalize_text
from .standard_validation_common import add_issue


def validate_business_rules(entities: dict, issues: list[dict]) -> None:
    _validate_customer_rules(entities, issues)
    _validate_lead_rules(entities, issues)
    _validate_activity_rules(entities, issues)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "是"}


def _validate_customer_rules(entities: dict, issues: list[dict]) -> None:
    aliases: dict[str, str] = {}
    for row in entities["aliases"]:
        if row.get("action") != "UPSERT":
            continue
        normalized = normalize_text(row.get("alias_name"))
        customer_key = row.get("customer_key")
        if normalized in aliases and aliases[normalized] != customer_key:
            add_issue(issues, "blocker", "alias_collision", row,
                      "The same normalized alias points to multiple customers", "alias_name")
        aliases[normalized] = customer_key
    primaries: Counter = Counter()
    for row in entities["contacts"]:
        if row.get("action") == "UPSERT" and _truthy(row.get("is_primary")):
            primaries[row.get("customer_key")] += 1
            if primaries[row.get("customer_key")] > 1:
                add_issue(issues, "blocker", "multiple_primary_contacts", row,
                          "A customer may have only one primary contact", "is_primary")


def _validate_lead_rules(entities: dict, issues: list[dict]) -> None:
    contacts = {row["external_key"]: row for row in entities["contacts"]}
    for row in entities["leads"]:
        if row.get("action") != "UPSERT":
            continue
        stage = row.get("sales_stage")
        if stage == "Lost" and not (row.get("lost_reason_code") or row.get("lost_reason_text")):
            add_issue(issues, "blocker", "lost_reason_required", row,
                      "Lost leads require a lost reason", "lost_reason_text")
        if stage != "Won" and row.get("fulfillment_status") not in (None, "", "Not Started"):
            add_issue(issues, "blocker", "stage_fulfillment_conflict", row,
                      "Only Won leads may have active fulfillment", "fulfillment_status")
        if row.get("deal_amount") not in (None, "") and not row.get("currency"):
            add_issue(issues, "blocker", "currency_required", row,
                      "currency is required when deal_amount is present", "currency")
        contact_key = row.get("primary_contact_key")
        if contact_key:
            contact = contacts.get(contact_key)
            if not contact or contact.get("customer_key") != row.get("customer_key"):
                add_issue(issues, "blocker", "primary_contact_mismatch", row,
                          "primary_contact_key must belong to the lead customer", "primary_contact_key")
        if not row.get("inquiry_date"):
            add_issue(issues, "warning", "missing_inquiry_date", row,
                      "Historical lead has no inquiry date", "inquiry_date")
        if row.get("service_status") not in (None, ""):
            add_issue(issues, "warning", "derived_field_supplied", row,
                      "service_status is derived from after-sales tasks", "service_status")


def _validate_activity_rules(entities: dict, issues: list[dict]) -> None:
    for row in entities["activities"]:
        if row.get("action") != "UPSERT":
            continue
        if row.get("activity_type") == "follow_up" and not (row.get("method") and row.get("status")):
            add_issue(issues, "blocker", "follow_up_fields_required", row,
                      "follow_up activities require method and status")
        if row.get("next_action_date") and not row.get("next_action"):
            add_issue(issues, "warning", "next_action_missing", row,
                      "next_action_date is present without next_action", "next_action")
