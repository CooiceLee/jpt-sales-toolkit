"""
Customer repository - database operations for customers and related tables.
"""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, ConflictError, generate_uuid, now_iso


class CustomerRepository(BaseRepository):
    """Repository for customers table."""

    table_name = "customers"

    def create(self, data: dict, actor_id: str) -> str:
        """Create new customer. Returns customer ID."""
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
        self.conn.commit()
        return customer_id

    def update(
        self,
        customer_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
    ) -> dict:
        """Update customer with optimistic locking. Returns updated record."""
        current = self.get_by_id(customer_id)
        if not current:
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
        cursor = self.conn.execute(sql, params)

        if cursor.rowcount == 0:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": customer_id, "updated_at": current["updated_at"]},
            )

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
            sql += " AND (normalized_name LIKE ? OR display_name LIKE ?)"
            params.extend([f"%{search.lower()}%", f"%{search}%"])

        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    # Domain operations
    def add_domain(self, customer_id: str, domain: str, is_primary: bool = False) -> str:
        """Add domain to customer."""
        domain_id = generate_uuid()
        self.conn.execute(
            """
            INSERT INTO customer_domains (id, customer_id, domain, is_primary, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (domain_id, customer_id, domain.lower(), 1 if is_primary else 0, now_iso()),
        )
        self.conn.commit()
        return domain_id

    def get_domains(self, customer_id: str) -> list[dict]:
        """Get all domains for customer."""
        cursor = self.conn.execute(
            "SELECT * FROM customer_domains WHERE customer_id = ? ORDER BY is_primary DESC",
            (customer_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def find_by_domain(self, domain: str) -> Optional[str]:
        """Find customer ID by domain."""
        cursor = self.conn.execute(
            "SELECT customer_id FROM customer_domains WHERE domain = ?",
            (domain.lower(),),
        )
        row = cursor.fetchone()
        return row["customer_id"] if row else None

    # Contact operations
    def add_contact(self, customer_id: str, contact_data: dict) -> str:
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

    def update_contact(self, contact_id: str, data: dict) -> dict:
        """Update customer contact."""
        current = self.get_contact_by_id(contact_id)
        if not current:
            raise ValueError(f"Customer contact {contact_id} not found")

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
        self.conn.execute(
            f"UPDATE customer_contacts SET {sql} WHERE id = ? AND archived_at IS NULL",
            params,
        )
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
