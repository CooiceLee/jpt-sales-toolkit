"""Binding-based create/update prediction."""

from ...repositories.authorization_schema import DEFAULT_ORGANIZATION_ID


def predicted_counts(conn, dataset_id: str, entities: dict, excluded: set[str]) -> dict:
    result = {}
    for kind, items in entities.items():
        keys = [item.get("external_key") for item in items]
        existing = 0
        if keys:
            marks = ",".join("?" for _ in keys)
            existing = conn.execute(
                f"""SELECT COUNT(*) FROM import_bindings WHERE organization_id = ?
                    AND dataset_id = ? AND entity_type = ? AND external_key IN ({marks})""",
                (DEFAULT_ORGANIZATION_ID, dataset_id, kind, *keys),
            ).fetchone()[0]
        result[kind] = {"create": len(keys) - existing, "update": existing}
    result["excluded"] = len(excluded)
    return result
