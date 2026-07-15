"""Soft-preserving domain and alias migration for customer merge."""

from __future__ import annotations

from ..repositories.base import generate_uuid
from ..repositories.customer_alias_repository import normalize_alias

def merge_domains(conn, source_id: str, target_id: str, now: str, actor_id: str) -> dict:
    rows = conn.execute("SELECT * FROM customer_domains WHERE customer_id = ?", (source_id,)).fetchall()
    target_primary = conn.execute(
        """SELECT 1 FROM customer_domains WHERE customer_id = ?
           AND archived_at IS NULL AND is_primary = 1 LIMIT 1""",
        (target_id,),
    ).fetchone() is not None
    result = {"moved": 0, "archived_duplicates": 0}
    for raw in rows:
        item = dict(raw)
        duplicate = conn.execute(
            """SELECT * FROM customer_domains WHERE customer_id = ? AND lower(domain) = lower(?)
               ORDER BY archived_at IS NULL DESC, created_at LIMIT 1""",
            (target_id, item["domain"]),
        ).fetchone()
        active = item.get("archived_at") is None
        if duplicate and active and duplicate["archived_at"] is not None:
            _retire_domain(conn, dict(duplicate), now, actor_id)
            duplicate = None
        if duplicate:
            if active and item.get("is_primary") and not duplicate["is_primary"] and not target_primary:
                conn.execute(
                    "UPDATE customer_domains SET is_primary = 1, updated_at = ?, updated_by = ? WHERE id = ?",
                    (now, actor_id, duplicate["id"]),
                )
                target_primary = True
            _retire_domain(conn, item, now, actor_id, target_id)
            result["archived_duplicates"] += 1
            continue
        primary = int(bool(item.get("is_primary")))
        if active and primary and target_primary:
            primary = 0
        conn.execute(
            """UPDATE customer_domains SET customer_id = ?, is_primary = ?,
               updated_at = ?, updated_by = ? WHERE id = ?""",
            (target_id, primary, now, actor_id, item["id"]),
        )
        if active and primary:
            target_primary = True
        result["moved"] += 1
    return result


def merge_aliases(
    conn, source: dict, target: dict, now: str, actor_id: str,
) -> dict:
    source_id, target_id = source["id"], target["id"]
    result = {"moved": 0, "archived_duplicates": 0, "source_name_added": False}
    target_name = normalize_alias(target.get("display_name"))
    source_name = str(source.get("display_name") or "").strip()
    if source_name and normalize_alias(source_name) != target_name:
        duplicate = _find_alias(conn, target_id, normalize_alias(source_name))
        if duplicate and duplicate["archived_at"] is not None:
            conn.execute(
                """UPDATE customer_aliases SET alias_name = ?, archived_at = NULL,
                   updated_at = ?, updated_by = ? WHERE id = ?""",
                (source_name, now, actor_id, duplicate["id"]),
            )
            result["source_name_added"] = True
            result["source_name_alias_id"] = duplicate["id"]
        elif not duplicate:
            alias_id = generate_uuid()
            conn.execute(
                """INSERT INTO customer_aliases
                   (id, customer_id, alias_name, normalized_alias, created_at, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (alias_id, target_id, source_name, normalize_alias(source_name), now, now, actor_id),
            )
            result["source_name_added"] = True
            result["source_name_alias_id"] = alias_id

    rows = conn.execute("SELECT * FROM customer_aliases WHERE customer_id = ?", (source_id,)).fetchall()
    for raw in rows:
        item = dict(raw)
        duplicate = _find_alias(conn, target_id, item["normalized_alias"])
        same_as_name = item["normalized_alias"] == target_name
        active = item.get("archived_at") is None
        if duplicate and active and duplicate["archived_at"] is not None:
            _retire_alias(conn, dict(duplicate), now, actor_id)
            duplicate = None
        if duplicate or same_as_name:
            _retire_alias(conn, item, now, actor_id, target_id)
            result["archived_duplicates"] += 1
            continue
        conn.execute(
            """UPDATE customer_aliases SET customer_id = ?, updated_at = ?, updated_by = ?
               WHERE id = ?""",
            (target_id, now, actor_id, item["id"]),
        )
        result["moved"] += 1
    return result


def _find_alias(conn, customer_id: str, normalized: str):
    return conn.execute(
        """SELECT * FROM customer_aliases WHERE customer_id = ? AND normalized_alias = ?
           ORDER BY archived_at IS NULL DESC, created_at LIMIT 1""",
        (customer_id, normalized),
    ).fetchone()


def _retire_domain(conn, item: dict, now: str, actor_id: str, customer_id: str = None) -> None:
    conn.execute(
        """UPDATE customer_domains SET customer_id = ?, domain = ?, archived_at = ?,
           is_primary = 0, updated_at = ?, updated_by = ? WHERE id = ?""",
        (customer_id or item["customer_id"], f"{item['domain']}#merged-{item['id']}",
         item.get("archived_at") or now, now, actor_id, item["id"]),
    )


def _retire_alias(conn, item: dict, now: str, actor_id: str, customer_id: str = None) -> None:
    conn.execute(
        """UPDATE customer_aliases SET customer_id = ?, normalized_alias = ?, archived_at = ?,
           updated_at = ?, updated_by = ? WHERE id = ?""",
        (customer_id or item["customer_id"], f"{item['normalized_alias']}#merged-{item['id']}",
         item.get("archived_at") or now, now, actor_id, item["id"]),
    )
