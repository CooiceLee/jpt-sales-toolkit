"""
Customer repository - database operations for customers and related tables.
"""

from __future__ import annotations

from typing import Optional

from ..coordinate_validation import validated_coordinate_payload
from .base import BaseRepository, ConflictError, generate_uuid, now_iso


class CustomerRepository(BaseRepository):
    """Repository for customers table."""

    table_name = "customers"

    def create(
        self,
        data: dict,
        actor_id: str,
        *,
        commit: bool = True,
    ) -> str:
        """Create new customer. Returns customer ID."""
        data = validated_coordinate_payload(data)
        customer_id = generate_uuid()
        now = now_iso()

        insert_data = {
            "id": customer_id,
            "created_at": now,
            "created_by": actor_id,
            "updated_at": now,
            "updated_by": actor_id,
            "row_version": 1,
            **data,
        }

        sql, params = self._build_insert(insert_data)
        self.conn.execute(sql, params)
        if commit:
            self.conn.commit()
        return customer_id

    def update(
        self,
        customer_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
        *,
        commit: bool = True,
    ) -> dict:
        """Update customer with optimistic locking. Returns updated record."""
        data = validated_coordinate_payload(data)
        current = self.get_by_id(customer_id)
        if not current or current.get("archived_at"):
            raise ValueError(f"Customer {customer_id} not found")

        if current["row_version"] != row_version:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": customer_id, "updated_at": current["updated_at"]},
            )

        update_data = {
            **data,
            "updated_at": now_iso(),
            "updated_by": actor_id,
            "row_version": row_version + 1,
        }

        sql, params = self._build_update(customer_id, update_data, row_version)
        sql += " AND archived_at IS NULL"
        cursor = self.conn.execute(sql, params)

        if cursor.rowcount == 0:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": customer_id, "updated_at": current["updated_at"]},
            )

        if commit:
            self.conn.commit()
        return self.get_by_id(customer_id)

    def archive(self, customer_id: str, actor_id: str) -> bool:
        """Archive customer (soft delete)."""
        cursor = self.conn.execute(
            """
            UPDATE customers
            SET archived_at = ?, updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ? AND archived_at IS NULL
            """,
            (now_iso(), now_iso(), actor_id, customer_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def list_active(
        self,
        limit: int = 100,
        offset: int = 0,
        country: Optional[str] = None,
        region: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        """List active customers with optional filters."""
        sql = "SELECT * FROM customers WHERE archived_at IS NULL"
        params: list = []

        if country:
            sql += " AND country = ?"
            params.append(country)

        if region:
            sql += " AND region = ?"
            params.append(region)

        if search:
            alias_active = "AND ca.archived_at IS NULL" if self._has_column("customer_aliases", "archived_at") else ""
            normalized_search = search.lower().replace(",", "").replace(".", "")
            sql += f""" AND (normalized_name LIKE ? OR display_name LIKE ? OR EXISTS (
                SELECT 1 FROM customer_aliases ca
                WHERE ca.customer_id = customers.id {alias_active}
                  AND ca.normalized_alias LIKE ?
            ))"""
            params.extend([f"%{normalized_search}%", f"%{search}%", f"%{normalized_search}%"])

        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def list_merge_candidate_records(self) -> list[dict]:
        """Return the small identity projection needed for merge-candidate ranking."""
        rows = self.conn.execute(
            """SELECT id, display_name, country, city, region, row_version, updated_at
               FROM customers WHERE archived_at IS NULL ORDER BY display_name"""
        ).fetchall()
        records = {row["id"]: {**dict(row), "aliases": []} for row in rows}
        if not records:
            return []
        alias_active = (
            "AND a.archived_at IS NULL"
            if self._has_column("customer_aliases", "archived_at")
            else ""
        )
        aliases = self.conn.execute(
            f"""SELECT a.customer_id, a.alias_name FROM customer_aliases a
                JOIN customers c ON c.id = a.customer_id AND c.archived_at IS NULL
                WHERE 1 = 1 {alias_active} ORDER BY a.alias_name"""
        ).fetchall()
        for alias in aliases:
            if alias["customer_id"] in records:
                records[alias["customer_id"]]["aliases"].append(alias["alias_name"])
        return list(records.values())

    # Domain operations
    def add_domain(self, customer_id: str, domain: str, is_primary: bool = False) -> str:
        """Add domain to customer."""
        domain_id = generate_uuid()
        now = now_iso()
        if self._has_column("customer_domains", "archived_at"):
            existing = self.conn.execute(
                "SELECT id, archived_at FROM customer_domains WHERE customer_id = ? AND domain = ?",
                (customer_id, domain.lower()),
            ).fetchone()
            if existing and existing["archived_at"]:
                domain_id = existing["id"]
                self.conn.execute(
                    """UPDATE customer_domains SET archived_at = NULL, is_primary = ?,
                       updated_at = ?, updated_by = NULL WHERE id = ?""",
                    (1 if is_primary else 0, now, domain_id),
                )
            else:
                self.conn.execute(
                    """INSERT INTO customer_domains
                       (id, customer_id, domain, is_primary, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (domain_id, customer_id, domain.lower(), 1 if is_primary else 0, now, now),
                )
        else:
            self.conn.execute(
                """INSERT INTO customer_domains (id, customer_id, domain, is_primary, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (domain_id, customer_id, domain.lower(), 1 if is_primary else 0, now),
            )
        self.conn.commit()
        return domain_id

    def get_domains(self, customer_id: str) -> list[dict]:
        """Get all domains for customer."""
        active = " AND archived_at IS NULL" if self._has_column("customer_domains", "archived_at") else ""
        cursor = self.conn.execute(
            f"SELECT * FROM customer_domains WHERE customer_id = ?{active} ORDER BY is_primary DESC",
            (customer_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def find_by_domain(self, domain: str) -> Optional[str]:
        """Find customer ID by domain."""
        active = "AND d.archived_at IS NULL" if self._has_column("customer_domains", "archived_at") else ""
        cursor = self.conn.execute(
            f"""SELECT d.customer_id FROM customer_domains d
                JOIN customers c ON c.id = d.customer_id AND c.archived_at IS NULL
                WHERE lower(d.domain) = ? {active} LIMIT 1""",
            (domain.lower(),),
        )
        row = cursor.fetchone()
        return row["customer_id"] if row else None

    # Contact operations
    def add_contact(
        self,
        customer_id: str,
        contact_data: dict,
        *,
        commit: bool = True,
    ) -> str:
        """Add contact to customer."""
        contact_id = generate_uuid()
        now = now_iso()
        if contact_data.get("email"):
            contact_data["email"] = contact_data["email"].lower()

        if contact_data.get("is_primary"):
            self.conn.execute(
                "UPDATE customer_contacts SET is_primary = 0 WHERE customer_id = ? AND archived_at IS NULL",
                (customer_id,),
            )

        data = {
            "id": contact_id,
            "customer_id": customer_id,
            "created_at": now,
            "updated_at": now,
            **contact_data,
        }
        sql, params = self._build_insert(data)
        # Adjust table name for this insert
        sql = sql.replace(self.table_name, "customer_contacts")
        self.conn.execute(sql, params)
        if commit:
            self.conn.commit()
        return contact_id

    def get_contacts(self, customer_id: str) -> list[dict]:
        """Get all contacts for customer."""
        cursor = self.conn.execute(
            """
            SELECT * FROM customer_contacts
            WHERE customer_id = ? AND archived_at IS NULL
            ORDER BY is_primary DESC, created_at ASC
            """,
            (customer_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_contact_by_id(self, contact_id: str) -> Optional[dict]:
        """Get active contact by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM customer_contacts WHERE id = ? AND archived_at IS NULL",
            (contact_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_contact(
        self,
        contact_id: str,
        data: dict,
        *,
        expected_updated_at: Optional[str] = None,
        commit: bool = True,
    ) -> dict:
        """Update customer contact."""
        current = self.get_contact_by_id(contact_id)
        if not current:
            raise ValueError(f"Customer contact {contact_id} not found")
        if expected_updated_at is not None and current["updated_at"] != expected_updated_at:
            raise ConflictError(
                current_version=current["updated_at"],
                your_version=expected_updated_at,
                current_data={"id": contact_id, "updated_at": current["updated_at"]},
            )

        if data.get("email"):
            data["email"] = data["email"].lower()

        if data.get("is_primary"):
            self.conn.execute(
                """
                UPDATE customer_contacts
                SET is_primary = 0
                WHERE customer_id = ? AND id != ? AND archived_at IS NULL
                """,
                (current["customer_id"], contact_id),
            )

        update_data = {
            **data,
            "updated_at": now_iso(),
        }
        sql = ", ".join(f"{k} = ?" for k in update_data.keys())
        params = list(update_data.values()) + [contact_id]
        where = "id = ? AND archived_at IS NULL"
        if expected_updated_at is not None:
            where += " AND updated_at = ?"
            params.append(expected_updated_at)
        cursor = self.conn.execute(
            f"UPDATE customer_contacts SET {sql} WHERE {where}",
            params,
        )
        if cursor.rowcount == 0:
            latest = self.get_contact_by_id(contact_id) or current
            raise ConflictError(
                current_version=latest["updated_at"],
                your_version=expected_updated_at,
                current_data={"id": contact_id, "updated_at": latest["updated_at"]},
            )
        if commit:
            self.conn.commit()
        return self.get_contact_by_id(contact_id)

    def archive_contact(self, contact_id: str) -> bool:
        """Soft archive customer contact."""
        cursor = self.conn.execute(
            """
            UPDATE customer_contacts
            SET archived_at = ?, updated_at = ?
            WHERE id = ? AND archived_at IS NULL
            """,
            (now_iso(), now_iso(), contact_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def find_by_email(self, email: str) -> Optional[str]:
        """Find customer ID by contact email."""
        cursor = self.conn.execute(
            "SELECT customer_id FROM customer_contacts WHERE email = ? AND archived_at IS NULL",
            (email.lower(),),
        )
        row = cursor.fetchone()
        return row["customer_id"] if row else None

    def find_by_normalized_name(self, normalized_name: str) -> Optional[str]:
        """Find customer ID by normalized name."""
        cursor = self.conn.execute(
            "SELECT id FROM customers WHERE normalized_name = ? AND archived_at IS NULL",
            (normalized_name,),
        )
        row = cursor.fetchone()
        return row["id"] if row else None

    def _has_column(self, table_name: str, column_name: str) -> bool:
        rows = self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(row[1] == column_name for row in rows)
