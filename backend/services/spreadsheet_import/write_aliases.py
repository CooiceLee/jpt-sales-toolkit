"""Transactional customer-alias writer."""

from ...repositories.base import generate_uuid, now_iso
from ..customer_service import normalize_name
from .bindings import bind, binding_id
from .persistence_common import action_for, apply_archive_action, upsert


def write_aliases(conn, canonical, context, actor_id, batch_id, ids, counts):
    dataset_id, source_hash = canonical["dataset_id"], canonical["source_hash"]
    for item in context["entities"]["aliases"]:
        action = action_for(item)
        bound_id = binding_id(conn, dataset_id, "aliases", item["external_key"])
        if action in {"ARCHIVE", "RESTORE"}:
            if not bound_id or not _exists(conn, "customer_aliases", bound_id):
                raise ValueError(f"Cannot {action.lower()} unknown alias {item['external_key']}")
            apply_archive_action(conn, "customer_aliases", bound_id, action, actor_id)
            bind(conn, dataset_id, "aliases", item["external_key"], bound_id, batch_id, source_hash)
            ids["aliases"][item["external_key"]] = bound_id
            counts["aliases"]["updated"] += 1
            continue
        customer_id = ids["customers"][item["customer_key"]]
        normalized = normalize_name(item.get("alias_name") or "")
        row = conn.execute(
            "SELECT id, customer_id FROM customer_aliases WHERE normalized_alias = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if row and row["customer_id"] != customer_id:
            raise ValueError(f"Alias {item.get('alias_name')!r} belongs to another customer")
        alias_id = bound_id
        alias_id = alias_id or (row["id"] if row else generate_uuid())
        existed = _exists(conn, "customer_aliases", alias_id)
        if not apply_archive_action(conn, "customer_aliases", alias_id, action, actor_id):
            now = now_iso()
            upsert(conn, "customer_aliases", alias_id, {
                "customer_id": customer_id, "alias_name": item.get("alias_name"),
                "normalized_alias": normalized, "created_at": now,
                "updated_at": now, "updated_by": actor_id, "archived_at": None,
            })
        bind(conn, dataset_id, "aliases", item["external_key"], alias_id, batch_id, source_hash)
        ids["aliases"][item["external_key"]] = alias_id
        counts["aliases"]["updated" if existed else "created"] += 1


def _exists(conn, table, row_id):
    return conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone() is not None
