"""Detect cross-customer alias collisions before commit."""

from ..customer_service import normalize_name
from .customer_matching import CREATE


def alias_issues(conn, entities: dict, customer_targets: dict) -> list[dict]:
    result = []
    for item in entities["aliases"]:
        if str(item.get("action") or "UPSERT").upper() != "UPSERT":
            continue
        target = customer_targets.get(item.get("customer_key"))
        normalized = normalize_name(item.get("alias_name") or "")
        row = conn.execute(
            "SELECT customer_id FROM customer_aliases WHERE normalized_alias = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if row and (target == CREATE or row["customer_id"] != target):
            ref = item.get("source_ref") or {}
            result.append({
                "severity": "error", "code": "customer_alias_conflict",
                "entity_type": "aliases", "external_key": item.get("external_key"),
                "field": "alias_name", "message": "Alias belongs to another customer",
                "source_ref": ref, "source_record_key": ref.get("record_key"),
            })
    return result
