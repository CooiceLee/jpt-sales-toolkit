"""Transactional customer, alias, and contact writers."""

from __future__ import annotations

from ...repositories.base import generate_uuid, now_iso
from ..customer_service import normalize_name
from .bindings import bind, binding_id
from .customer_matching import CREATE
from .persistence_common import (
    CLEAR_TOKEN, action_for, apply_archive_action, selected_fields, upsert,
)
from .persistence_json import merged_json
from .write_aliases import write_aliases
from .write_contacts import write_contacts
from .value_normalization import boolean_value

CUSTOMER_FIELDS = {
    "display_name", "website", "industry", "customer_type", "company_size", "language",
    "country", "city", "postal_code", "address", "region", "lat", "lng",
    "normalized_address", "geocode_source", "geocode_confidence", "geocode_locked",
    "company_description",
}


def write_customer_entities(conn, canonical: dict, context: dict, actor_id: str,
                            batch_id: str) -> tuple[dict, dict[str, dict]]:
    dataset_id, source_hash = canonical["dataset_id"], canonical["source_hash"]
    ids = {"customers": {}, "aliases": {}, "contacts": {}}
    counts = {kind: {"created": 0, "updated": 0} for kind in ids}
    for item in context["entities"]["customers"]:
        key = item["external_key"]
        target = binding_id(conn, dataset_id, "customers", key)
        target = target or context["customer_targets"][key]
        customer_id = generate_uuid() if target == CREATE else target
        existed = _exists(conn, "customers", customer_id)
        action = action_for(item)
        if action in {"ARCHIVE", "RESTORE"} and not existed:
            raise ValueError(f"Cannot {action.lower()} unknown customer {key}")
        if not apply_archive_action(conn, "customers", customer_id, action, actor_id):
            _upsert_customer(conn, customer_id, item, actor_id)
        bind(conn, dataset_id, "customers", key, customer_id, batch_id, source_hash)
        ids["customers"][key] = customer_id
        counts["customers"]["updated" if existed else "created"] += 1
    write_aliases(conn, canonical, context, actor_id, batch_id, ids, counts)
    write_contacts(conn, canonical, context, actor_id, batch_id, ids, counts)
    return ids, counts


def _upsert_customer(conn, customer_id: str, item: dict, actor_id: str) -> None:
    now = now_iso()
    current = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    values = selected_fields(item, CUSTOMER_FIELDS)
    if "geocode_locked" in values:
        values["geocode_locked"] = boolean_value(values["geocode_locked"])
    if item.get("display_name") and item.get("display_name") != CLEAR_TOKEN:
        values["normalized_name"] = normalize_name(item["display_name"])
    extras = {key: value for key, value in item.items()
              if key not in CUSTOMER_FIELDS | {"external_key", "source_ref", "source_refs", "action"}}
    values.update({
        "updated_at": now, "updated_by": actor_id,
        "extra_json": merged_json(current["extra_json"] if current else None, extras),
    })
    if current:
        values["row_version"] = current["row_version"] + 1
    else:
        values.update({"created_at": now, "created_by": actor_id, "row_version": 1})
    upsert(conn, "customers", customer_id, values)


def _exists(conn, table, row_id):
    return conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone() is not None
