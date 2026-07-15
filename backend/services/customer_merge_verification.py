"""Customer merge postconditions, result contract, and atomic audit write."""

from __future__ import annotations

import json

from ..repositories.base import generate_uuid


def guard_source_identity(conn, preview: dict) -> None:
    source, target = preview["source_customer"], preview["target_customer"]
    names = [source.get("normalized_name")]
    names.extend(
        row.get("normalized_alias")
        for row in preview["source_relations"]["aliases"]
        if row.get("archived_at") is None
    )
    for normalized in {name for name in names if name}:
        customer = conn.execute(
            """SELECT id FROM customers WHERE normalized_name = ? AND archived_at IS NULL
               AND id NOT IN (?, ?) LIMIT 1""",
            (normalized, source["id"], target["id"]),
        ).fetchone()
        alias = conn.execute(
            """SELECT a.customer_id FROM customer_aliases a JOIN customers c ON c.id = a.customer_id
               WHERE a.normalized_alias = ? AND a.archived_at IS NULL AND c.archived_at IS NULL
               AND a.customer_id NOT IN (?, ?) LIMIT 1""",
            (normalized, source["id"], target["id"]),
        ).fetchone()
        if customer or alias:
            raise ValueError("Source identity belongs to another active customer")


def assert_postconditions(conn, source_id: str, target_id: str, preview: dict) -> None:
    tables = ("leads", "trip_plan_stops", "customer_contacts", "customer_domains", "customer_aliases")
    for table in tables:
        count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE customer_id = ?", (source_id,)
        ).fetchone()[0]
        if count:
            raise RuntimeError(f"Customer merge left {count} source references in {table}")
    lead_ids = [row["id"] for row in preview["source_relations"]["leads"]]
    if lead_ids:
        marks = ",".join("?" for _ in lead_ids)
        mismatch = conn.execute(
            f"SELECT COUNT(*) FROM trip_plan_stops WHERE lead_id IN ({marks}) AND customer_id != ?",
            (*lead_ids, target_id),
        ).fetchone()[0]
        if mismatch:
            raise RuntimeError("Trip stop and lead customer references diverged")


def build_result(preview, leads, stops, contacts, domains, aliases) -> dict:
    return {
        "source_customer_id": preview["source_customer"]["id"],
        "target_customer_id": preview["target_customer"]["id"],
        "moved_leads": leads,
        "moved_trip_plan_stops": stops,
        "moved_contacts": contacts["moved"],
        "archived_duplicate_contacts": contacts["archived_duplicates"],
        "moved_domains": domains["moved"],
        "skipped_duplicate_domains": domains["archived_duplicates"],
        "moved_aliases": aliases["moved"] + int(aliases["source_name_added"]),
        "source_name_alias_id": aliases.get("source_name_alias_id"),
        "skipped_aliases": aliases["archived_duplicates"],
        "target_updates": preview["field_updates"],
        "field_conflicts": preview["field_conflicts"],
        "contact_field_conflicts": contacts["conflicts"],
    }


def write_audit(conn, target_id: str, actor_id: str, preview: dict, result: dict, now: str) -> str:
    audit_id = generate_uuid()
    conn.execute(
        """INSERT INTO audit_logs (id, entity_type, entity_id, actor_id, event_type,
           before_json, after_json, created_at) VALUES (?, 'customer', ?, ?,
           'merge_customer', ?, ?, ?)""",
        (audit_id, target_id, actor_id, json.dumps(preview, ensure_ascii=False),
         json.dumps(result, ensure_ascii=False), now),
    )
    return audit_id
