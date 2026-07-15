"""Persistence helpers for customer aliases."""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, generate_uuid, now_iso


def normalize_alias(value: str) -> str:
    return str(value or "").lower().strip().replace(",", "").replace(".", "")


class CustomerAliasRepository(BaseRepository):
    table_name = "customer_aliases"

    def _columns(self) -> set[str]:
        return {row[1] for row in self.conn.execute("PRAGMA table_info(customer_aliases)")}

    def require_lifecycle(self) -> None:
        required = {"archived_at", "updated_at", "updated_by"}
        if not required.issubset(self._columns()):
            raise RuntimeError("Customer alias lifecycle migration is required")

    def list_for_customer(self, customer_id: str, include_archived: bool = False) -> list[dict]:
        lifecycle = "archived_at" in self._columns()
        where = "customer_id = ?"
        if lifecycle and not include_archived:
            where += " AND archived_at IS NULL"
        rows = self.conn.execute(
            f"SELECT * FROM customer_aliases WHERE {where} ORDER BY alias_name", (customer_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_for_customer(self, customer_id: str, alias_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM customer_aliases WHERE id = ? AND customer_id = ?",
            (alias_id, customer_id),
        ).fetchone()
        return dict(row) if row else None

    def find_active_customer(self, normalized_alias: str) -> Optional[str]:
        lifecycle = "archived_at" in self._columns()
        active = "AND a.archived_at IS NULL" if lifecycle else ""
        row = self.conn.execute(
            f"""
            SELECT a.customer_id FROM customer_aliases a
            JOIN customers c ON c.id = a.customer_id AND c.archived_at IS NULL
            WHERE a.normalized_alias = ? {active} LIMIT 1
            """,
            (normalized_alias,),
        ).fetchone()
        return row["customer_id"] if row else None

    def create(self, customer_id: str, alias_name: str, actor_id: str) -> dict:
        self.require_lifecycle()
        normalized = normalize_alias(alias_name)
        existing = self.conn.execute(
            "SELECT * FROM customer_aliases WHERE customer_id = ? AND normalized_alias = ?",
            (customer_id, normalized),
        ).fetchone()
        now = now_iso()
        if existing and existing["archived_at"] is None:
            raise ValueError("Customer alias already exists")
        if existing:
            alias_id = existing["id"]
            self.conn.execute(
                """UPDATE customer_aliases SET alias_name = ?, archived_at = NULL,
                   updated_at = ?, updated_by = ? WHERE id = ?""",
                (alias_name, now, actor_id, alias_id),
            )
        else:
            alias_id = generate_uuid()
            self.conn.execute(
                """INSERT INTO customer_aliases
                   (id, customer_id, alias_name, normalized_alias, created_at, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (alias_id, customer_id, alias_name, normalized, now, now, actor_id),
            )
        self.conn.commit()
        return self.get_for_customer(customer_id, alias_id)

    def update(self, customer_id: str, alias_id: str, alias_name: str, actor_id: str) -> dict:
        self.require_lifecycle()
        current = self.get_for_customer(customer_id, alias_id)
        if not current or current.get("archived_at"):
            raise ValueError("Active customer alias not found")
        self.conn.execute(
            """UPDATE customer_aliases SET alias_name = ?, normalized_alias = ?,
               updated_at = ?, updated_by = ? WHERE id = ?""",
            (alias_name, normalize_alias(alias_name), now_iso(), actor_id, alias_id),
        )
        self.conn.commit()
        return self.get_for_customer(customer_id, alias_id)

    def set_archived(self, customer_id: str, alias_id: str, actor_id: str, archived: bool) -> dict:
        self.require_lifecycle()
        current = self.get_for_customer(customer_id, alias_id)
        if not current:
            raise ValueError("Customer alias not found")
        archived_at = now_iso() if archived else None
        self.conn.execute(
            "UPDATE customer_aliases SET archived_at = ?, updated_at = ?, updated_by = ? WHERE id = ?",
            (archived_at, now_iso(), actor_id, alias_id),
        )
        self.conn.commit()
        return self.get_for_customer(customer_id, alias_id)
