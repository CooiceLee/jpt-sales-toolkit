"""Transaction-local SQL helpers; none of these functions commit."""

from __future__ import annotations

from contextlib import contextmanager
from ...repositories.base import now_iso

CLEAR_TOKEN = "__CLEAR__"
CLEAR = object()


@contextmanager
def atomic(conn):
    name = "spreadsheet_import"
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
        conn.execute(f"RELEASE SAVEPOINT {name}")
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
        conn.execute(f"RELEASE SAVEPOINT {name}")
        raise


def upsert(conn, table: str, row_id: str, values: dict) -> str:
    current = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone()
    clean = {
        key: (None if value is CLEAR else value)
        for key, value in values.items() if value is not None
    }
    if current:
        if clean:
            assignments = ", ".join(f"{key} = ?" for key in clean)
            conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*clean.values(), row_id))
    else:
        payload = {"id": row_id, **clean}
        columns = ", ".join(payload)
        marks = ", ".join("?" for _ in payload)
        conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(payload.values()))
    return row_id


def action_for(item: dict) -> str:
    return str(item.get("action") or "UPSERT").strip().upper()


def apply_archive_action(conn, table: str, row_id: str, action: str, actor_id: str) -> bool:
    if action not in {"ARCHIVE", "RESTORE"}:
        return False
    value = now_iso() if action == "ARCHIVE" else None
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    updates = {"archived_at": value}
    if "updated_at" in columns:
        updates["updated_at"] = now_iso()
    if "updated_by" in columns:
        updates["updated_by"] = actor_id
    assignments = [f"{key} = ?" for key in updates]
    if "row_version" in columns:
        assignments.append("row_version = row_version + 1")
    state_predicate = (
        "archived_at IS NULL"
        if action == "ARCHIVE"
        else "archived_at IS NOT NULL"
    )
    conn.execute(
        f"UPDATE {table} SET {', '.join(assignments)} "
        f"WHERE id = ? AND {state_predicate}",
        (*updates.values(), row_id),
    )
    return True


def selected_fields(item: dict, allowed: set[str]) -> dict:
    """Preserve blanks, but convert the explicit clear marker to SQL NULL."""
    result = {}
    for key in allowed:
        if key not in item or item[key] in (None, ""):
            continue
        result[key] = CLEAR if item[key] == CLEAR_TOKEN else item[key]
    return result


def selected_value(item: dict, key: str):
    if key not in item or item[key] in (None, ""):
        return None
    return CLEAR if item[key] == CLEAR_TOKEN else item[key]
