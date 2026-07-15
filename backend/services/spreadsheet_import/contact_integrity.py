"""Ensure primary contacts remain inside the resolved lead customer."""

from .customer_matching import CREATE
from .persistence_common import CLEAR_TOKEN


def contact_integrity_issues(entities: dict, customer_targets: dict) -> list[dict]:
    contacts = {item.get("external_key"): item for item in entities["contacts"]}
    result = []
    for lead in entities["leads"]:
        contact_key = lead.get("primary_contact_key")
        if not contact_key or contact_key == CLEAR_TOKEN or contact_key not in contacts:
            continue
        lead_customer = lead.get("customer_key")
        contact_customer = contacts[contact_key].get("customer_key")
        lead_target = customer_targets.get(lead_customer)
        contact_target = customer_targets.get(contact_customer)
        same_target = lead_customer == contact_customer or (
            lead_target not in (None, CREATE) and lead_target == contact_target
        )
        if same_target:
            continue
        ref = lead.get("source_ref") or {}
        result.append({
            "severity": "error", "code": "primary_contact_customer_mismatch",
            "entity_type": "leads", "external_key": lead.get("external_key"),
            "field": "primary_contact_key",
            "message": "Primary contact belongs to a different resolved customer",
            "source_ref": ref, "source_record_key": ref.get("record_key"),
        })
    return result
