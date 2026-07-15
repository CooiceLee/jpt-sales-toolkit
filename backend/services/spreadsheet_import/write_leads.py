"""Transactional opportunity and assignment writers."""

from __future__ import annotations

from ...repositories.base import generate_uuid, now_iso
from .bindings import bind, binding_id, next_display_id
from .member_matching import resolution_name
from .persistence_common import (
    CLEAR, CLEAR_TOKEN, action_for, apply_archive_action, selected_fields, upsert,
)
from .persistence_json import merged_json
from .write_assignments import write_assignments

LEAD_FIELDS = {
    "legacy_inquiry_id", "title", "source_channel", "original_email", "sales_stage",
    "fulfillment_status", "service_status", "quality_grade", "urgency", "estimated_value",
    "product_category", "product_series", "power_range", "wavelength", "application",
    "material", "quantity_text", "currency", "deal_amount", "quotation_id",
    "quotation_date", "po_number", "po_date", "next_followup_date", "inquiry_date",
    "lost_reason_code", "lost_reason_text",
}


def write_lead_entities(conn, canonical: dict, context: dict, actor_id: str,
                        batch_id: str, ids: dict) -> tuple[dict, dict[str, dict]]:
    dataset_id, source_hash = canonical["dataset_id"], canonical["source_hash"]
    ids.update({"leads": {}, "assignments": {}})
    counts = {kind: {"created": 0, "updated": 0} for kind in ("leads", "assignments")}
    for item in context["entities"]["leads"]:
        key = item["external_key"]
        lead_id = binding_id(conn, dataset_id, "leads", key) or _legacy_match(conn, item) or generate_uuid()
        current = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        existed = current is not None
        action = action_for(item)
        if action in {"ARCHIVE", "RESTORE"} and not existed:
            raise ValueError(f"Cannot {action.lower()} unknown lead {key}")
        if not apply_archive_action(conn, "leads", lead_id, action, actor_id):
            _upsert_lead(conn, lead_id, item, current, context, actor_id, ids)
        bind(conn, dataset_id, "leads", key, lead_id, batch_id, source_hash)
        ids["leads"][key] = lead_id
        counts["leads"]["updated" if existed else "created"] += 1
    write_assignments(conn, canonical, context, actor_id, batch_id, ids, counts)
    return ids, counts


def _upsert_lead(conn, lead_id, item, current, context, actor_id, ids):
    token = resolution_name(item, "owner")
    owner_id = context["member_ids"][(token, "owner")]
    now = now_iso()
    values = selected_fields(item, LEAD_FIELDS)
    values.update({
        "customer_id": ids["customers"][item["customer_key"]],
        "owner_id": owner_id, "updated_at": now, "updated_by": actor_id,
    })
    contact_key = item.get("primary_contact_key")
    if contact_key == CLEAR_TOKEN:
        values["primary_contact_id"] = CLEAR
    elif contact_key:
        values["primary_contact_id"] = ids["contacts"].get(contact_key)
    extras = {key: value for key, value in item.items()
              if key not in LEAD_FIELDS | {"external_key", "source_ref", "source_refs", "action",
                                           "customer_key", "primary_contact_key",
                                           "owner_username_token", "owner_name_raw"}}
    values["extra_json"] = merged_json(current["extra_json"] if current else None, extras)
    if current:
        values["row_version"] = current["row_version"] + 1
    else:
        values.setdefault("sales_stage", "New")
        values.setdefault("fulfillment_status", "Not Started")
        values.setdefault("service_status", "None")
        values.update({
            "display_id": next_display_id(conn), "created_at": now,
            "created_by": actor_id, "row_version": 1, "archived_at": None,
        })
    upsert(conn, "leads", lead_id, values)
    _owner_assignment(conn, lead_id, owner_id, actor_id)


def _owner_assignment(conn, lead_id: str, owner_id: str, actor_id: str) -> None:
    conn.execute(
        """UPDATE lead_assignments SET archived_at = ?
           WHERE lead_id = ? AND assignment_type = 'owner' AND user_id != ? AND archived_at IS NULL""",
        (now_iso(), lead_id, owner_id),
    )
    row = conn.execute(
        """SELECT id FROM lead_assignments
           WHERE lead_id = ? AND user_id = ? AND assignment_type = 'owner'""",
        (lead_id, owner_id),
    ).fetchone()
    if row:
        conn.execute("UPDATE lead_assignments SET archived_at = NULL WHERE id = ?", (row[0],))
    else:
        upsert(conn, "lead_assignments", generate_uuid(), {
            "lead_id": lead_id, "user_id": owner_id, "assignment_type": "owner",
            "created_at": now_iso(), "created_by": actor_id, "archived_at": None,
        })


def _legacy_match(conn, item: dict):
    legacy_id = item.get("legacy_inquiry_id")
    if not legacy_id:
        return None
    row = conn.execute("SELECT id FROM leads WHERE legacy_inquiry_id = ?", (legacy_id,)).fetchone()
    return row[0] if row else None
