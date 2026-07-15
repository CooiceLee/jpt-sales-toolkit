"""Transactional customer-contact writer."""

from ...repositories.base import generate_uuid, now_iso
from ..customer_service import normalize_name
from .bindings import bind, binding_id
from .persistence_common import CLEAR, action_for, apply_archive_action, selected_fields, upsert
from .value_normalization import boolean_value

CONTACT_FIELDS = {"name", "position", "email", "phone", "whatsapp", "is_primary"}


def write_contacts(conn, canonical, context, actor_id, batch_id, ids, counts):
    dataset_id, source_hash = canonical["dataset_id"], canonical["source_hash"]
    for item in context["entities"]["contacts"]:
        action = action_for(item)
        bound_id = binding_id(conn, dataset_id, "contacts", item["external_key"])
        if action in {"ARCHIVE", "RESTORE"}:
            if not bound_id or not _exists(conn, bound_id):
                raise ValueError(f"Cannot {action.lower()} unknown contact {item['external_key']}")
            apply_archive_action(conn, "customer_contacts", bound_id, action, actor_id)
            bind(conn, dataset_id, "contacts", item["external_key"], bound_id, batch_id, source_hash)
            ids["contacts"][item["external_key"]] = bound_id
            counts["contacts"]["updated"] += 1
            continue
        customer_id = ids["customers"][item["customer_key"]]
        contact_id = bound_id
        contact_id = contact_id or _find_contact(conn, customer_id, item) or generate_uuid()
        existed = _exists(conn, contact_id)
        if not apply_archive_action(conn, "customer_contacts", contact_id, action, actor_id):
            _upsert_contact(conn, contact_id, customer_id, item, existed)
        bind(conn, dataset_id, "contacts", item["external_key"], contact_id, batch_id, source_hash)
        ids["contacts"][item["external_key"]] = contact_id
        counts["contacts"]["updated" if existed else "created"] += 1


def _upsert_contact(conn, contact_id, customer_id, item, existed):
    now = now_iso()
    values = selected_fields(item, CONTACT_FIELDS)
    if "is_primary" in values:
        values["is_primary"] = boolean_value(values["is_primary"])
        if values["is_primary"]:
            conn.execute(
                """UPDATE customer_contacts SET is_primary = 0, updated_at = ?
                   WHERE customer_id = ? AND id != ? AND archived_at IS NULL""",
                (now, customer_id, contact_id),
            )
    if values.get("email") and values.get("email") is not CLEAR:
        values["email"] = str(values["email"]).lower()
    values.update({"customer_id": customer_id, "updated_at": now})
    if not existed:
        values.update({"created_at": now, "archived_at": None})
    upsert(conn, "customer_contacts", contact_id, values)


def _find_contact(conn, customer_id: str, item: dict):
    email = str(item.get("email") or "").strip().lower()
    if email:
        row = conn.execute(
            "SELECT id FROM customer_contacts WHERE customer_id = ? AND email = ?", (customer_id, email)
        ).fetchone()
        if row:
            return row[0]
    name = normalize_name(item.get("name") or "")
    rows = conn.execute(
        "SELECT id, name FROM customer_contacts WHERE customer_id = ?", (customer_id,)
    ).fetchall()
    matches = [row["id"] for row in rows if normalize_name(row["name"]) == name]
    return matches[0] if len(matches) == 1 else None


def _exists(conn, row_id):
    return conn.execute(
        "SELECT 1 FROM customer_contacts WHERE id = ?", (row_id,)
    ).fetchone() is not None
