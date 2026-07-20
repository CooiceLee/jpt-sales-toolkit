"""Import-binding persistence and transaction-local display IDs."""

from datetime import datetime

from ...repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from ...repositories.base import generate_uuid, now_iso


def external_keys(item: dict) -> tuple[str, ...]:
    values = [item.get("external_key"), *(item.get("_binding_external_keys") or [])]
    return tuple(dict.fromkeys(str(value) for value in values if value))


def binding_id(conn, dataset_id: str, kind: str, key: str):
    row = conn.execute(
        """SELECT local_entity_id FROM import_bindings
           WHERE organization_id = ? AND dataset_id = ?
             AND entity_type = ? AND external_key = ?""",
        (DEFAULT_ORGANIZATION_ID, dataset_id, kind, key),
    ).fetchone()
    return row[0] if row else None


def bound_entity_keys(conn, dataset_id: str, entities: dict) -> set[tuple[str, str]]:
    scoped = {(kind, key) for kind, items in entities.items()
              for item in items for key in external_keys(item)}
    rows = conn.execute(
        """SELECT entity_type, external_key FROM import_bindings
           WHERE organization_id = ? AND dataset_id = ?""",
        (DEFAULT_ORGANIZATION_ID, dataset_id),
    ).fetchall()
    return {(row[0], row[1]) for row in rows if (row[0], row[1]) in scoped}


def bind(conn, dataset_id: str, kind: str, key: str, local_id: str,
         batch_id: str, source_hash: str) -> None:
    now = now_iso()
    conn.execute(
        """INSERT INTO import_bindings (
               id, organization_id, dataset_id, entity_type, external_key,
               local_entity_id, source_hash, first_batch_id, last_batch_id, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(organization_id, dataset_id, entity_type, external_key) DO UPDATE SET
               local_entity_id = excluded.local_entity_id,
               source_hash = excluded.source_hash,
               last_batch_id = excluded.last_batch_id,
               updated_at = excluded.updated_at""",
        (generate_uuid(), DEFAULT_ORGANIZATION_ID, dataset_id, kind, key, local_id,
         source_hash, batch_id, batch_id, now, now),
    )


def next_display_id(conn) -> str:
    period = datetime.utcnow().strftime("%y%m")
    row = conn.execute(
        "SELECT next_value FROM display_sequences WHERE period_ym = ?", (period,)
    ).fetchone()
    number = row[0] if row else 1
    if row:
        conn.execute(
            "UPDATE display_sequences SET next_value = ? WHERE period_ym = ?",
            (number + 1, period),
        )
    else:
        conn.execute(
            "INSERT INTO display_sequences(period_ym, next_value) VALUES (?, 2)", (period,)
        )
    return f"JPT-{period}-{number:04d}"
