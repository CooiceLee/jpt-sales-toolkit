"""Binding-based create/update prediction."""

from ...repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from .bindings import external_keys


def predicted_counts(conn, dataset_id: str, entities: dict, excluded: set[str]) -> dict:
    result = {}
    for kind, items in entities.items():
        item_keys = [external_keys(item) for item in items]
        keys = list(dict.fromkeys(key for values in item_keys for key in values))
        existing_keys = set()
        if keys:
            marks = ",".join("?" for _ in keys)
            rows = conn.execute(
                f"""SELECT external_key FROM import_bindings WHERE organization_id = ?
                    AND dataset_id = ? AND entity_type = ? AND external_key IN ({marks})""",
                (DEFAULT_ORGANIZATION_ID, dataset_id, kind, *keys),
            ).fetchall()
            existing_keys = {row[0] for row in rows}
        updates = sum(bool(set(values) & existing_keys) for values in item_keys)
        result[kind] = {"create": len(items) - updates, "update": updates}
    result["excluded"] = len(excluded)
    return result
