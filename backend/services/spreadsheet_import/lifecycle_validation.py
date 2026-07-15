"""Validate archive/restore targets before opening the write transaction."""

from ...repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from .customer_matching import CREATE


def lifecycle_issues(conn, dataset_id: str, entities: dict, customer_targets: dict) -> list[dict]:
    result = []
    for kind, items in entities.items():
        for item in items:
            action = str(item.get("action") or "UPSERT").upper()
            if action not in {"ARCHIVE", "RESTORE"}:
                continue
            if kind == "customers" and customer_targets.get(item.get("external_key")) != CREATE:
                continue
            if _has_binding(conn, dataset_id, kind, item.get("external_key")):
                continue
            result.append(_issue(kind, item, action))
    return result


def _has_binding(conn, dataset_id: str, kind: str, key: str) -> bool:
    return conn.execute(
        """SELECT 1 FROM import_bindings WHERE organization_id = ? AND dataset_id = ?
           AND entity_type = ? AND external_key = ?""",
        (DEFAULT_ORGANIZATION_ID, dataset_id, kind, key),
    ).fetchone() is not None


def _issue(kind: str, item: dict, action: str) -> dict:
    ref = item.get("source_ref") or {}
    return {
        "severity": "error", "code": "unknown_lifecycle_target", "entity_type": kind,
        "external_key": item.get("external_key"), "field": "action",
        "message": f"{action} requires a prior import binding or explicit existing customer mapping",
        "source_ref": ref, "source_record_key": ref.get("record_key"),
    }
