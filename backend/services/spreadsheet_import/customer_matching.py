"""Deterministic existing-customer decisions for preflight."""

from __future__ import annotations

from ...repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from ..customer_service import normalize_name

CREATE = "__CREATE__"


def resolve_customers(conn, canonical: dict, manual: dict[str, str], excluded: set[str]):
    dataset_id = canonical["dataset_id"]
    decisions, resolved = [], {}
    for item in (canonical.get("entities") or {}).get("customers") or []:
        key = str(item.get("external_key") or "")
        if key in excluded or _record_key(item) in excluded:
            continue
        choice = manual.get(key)
        candidates = _candidates(conn, item)
        binding = _binding(conn, dataset_id, key)
        if binding:
            result = _decision(item, "matched", binding, candidates, "binding")
        elif choice == CREATE:
            result = _decision(item, "create", None, candidates, "manual")
        elif choice:
            customer = _active_customer(conn, choice)
            result = _decision(
                item, "matched" if customer else "blocker",
                choice if customer else None, candidates, "manual",
                None if customer else "Selected customer does not exist or is archived",
            )
        elif len(candidates) == 1:
            result = _decision(item, "matched", candidates[0]["id"], candidates, "exact")
        elif len(candidates) > 1:
            result = _decision(item, "blocker", None, candidates, None,
                               "Customer name or alias matches multiple active customers")
        else:
            result = _decision(item, "create", None, [], "new")
        decisions.append(result)
        if result["status"] in {"matched", "create"}:
            resolved[key] = result["customer_id"] or CREATE
    return decisions, resolved


def _binding(conn, dataset_id: str, key: str):
    row = conn.execute(
        """SELECT b.local_entity_id FROM import_bindings b
           JOIN customers c ON c.id = b.local_entity_id
           WHERE b.organization_id = ? AND b.dataset_id = ?
             AND b.entity_type = 'customers' AND b.external_key = ?""",
        (DEFAULT_ORGANIZATION_ID, dataset_id, key),
    ).fetchone()
    return row[0] if row else None


def _candidates(conn, item: dict) -> list[dict]:
    normalized = normalize_name(item.get("display_name") or "")
    if not normalized:
        return []
    rows = conn.execute(
        """SELECT DISTINCT c.id, c.display_name,
                  CASE WHEN c.normalized_name = ? THEN 'name' ELSE 'alias' END AS matched_by
           FROM customers c
           LEFT JOIN customer_aliases a ON a.customer_id = c.id AND a.archived_at IS NULL
           WHERE c.archived_at IS NULL
             AND (c.normalized_name = ? OR a.normalized_alias = ?)
           ORDER BY c.display_name""",
        (normalized, normalized, normalized),
    ).fetchall()
    return [dict(row) for row in rows]


def _active_customer(conn, customer_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM customers WHERE id = ? AND archived_at IS NULL", (customer_id,)
    ).fetchone() is not None


def _decision(item, status, customer_id, candidates, matched_by, message=None) -> dict:
    return {
        "external_key": item.get("external_key"),
        "display_name": item.get("display_name"),
        "status": status, "customer_id": customer_id,
        "matched_by": matched_by, "candidates": candidates, "message": message,
    }


def _record_key(item: dict) -> str:
    return str((item.get("source_ref") or {}).get("record_key") or "")
