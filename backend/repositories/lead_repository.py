"""
Lead repository - database operations for leads and assignments.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .base import BaseRepository, ConflictError, generate_uuid, now_iso


class LeadRepository(BaseRepository):
    """Repository for leads table."""

    table_name = "leads"

    def generate_display_id(self) -> str:
        """Generate display_id in JPT-{YYMM}-{NNNN} format."""
        period_ym = datetime.utcnow().strftime("%y%m")

        row = self.conn.execute(
            "SELECT next_value FROM display_sequences WHERE period_ym = ?",
            (period_ym,),
        ).fetchone()

        if row:
            next_val = row[0]
            self.conn.execute(
                "UPDATE display_sequences SET next_value = ? WHERE period_ym = ?",
                (next_val + 1, period_ym),
            )
        else:
            next_val = 1
            self.conn.execute(
                "INSERT INTO display_sequences (period_ym, next_value) VALUES (?, ?)",
                (period_ym, 2),
            )

        return f"JPT-{period_ym}-{next_val:04d}"

    def create(self, data: dict, actor_id: str) -> str:
        """Create new lead. Returns lead ID."""
        self._validate_commercial_assignment(data.get("owner_id"), "owner")
        lead_id = generate_uuid()
        display_id = self.generate_display_id()
        now = now_iso()

        insert_data = {
            "id": lead_id,
            "display_id": display_id,
            "created_at": now,
            "created_by": actor_id,
            "updated_at": now,
            "updated_by": actor_id,
            "row_version": 1,
            **data,
        }

        sql, params = self._build_insert(insert_data)
        self.conn.execute(sql, params)

        # Create owner assignment
        owner_id = data.get("owner_id")
        if owner_id:
            self.add_assignment(lead_id, owner_id, "owner", actor_id)

        self.conn.commit()
        return lead_id

    def update(
        self,
        lead_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
    ) -> dict:
        """Update lead with optimistic locking. Returns updated record."""
        current = self.get_by_id(lead_id)
        if not current:
            raise ValueError(f"Lead {lead_id} not found")

        if "owner_id" in data:
            self._validate_commercial_assignment(data["owner_id"], "owner")

        if current["row_version"] != row_version:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": lead_id, "updated_at": current["updated_at"]},
            )

        # If owner_id changed, update assignment too
        if "owner_id" in data and data["owner_id"] != current["owner_id"]:
            self._update_owner_assignment(lead_id, data["owner_id"], actor_id)

        update_data = {
            **data,
            "updated_at": now_iso(),
            "updated_by": actor_id,
            "row_version": row_version + 1,
        }

        sql, params = self._build_update(lead_id, update_data, row_version)
        cursor = self.conn.execute(sql, params)

        if cursor.rowcount == 0:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": lead_id, "updated_at": current["updated_at"]},
            )

        self.conn.commit()
        return self.get_by_id(lead_id)

    def archive(self, lead_id: str, actor_id: str) -> bool:
        """Archive lead (soft delete)."""
        cursor = self.conn.execute(
            """
            UPDATE leads
            SET archived_at = ?, updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ? AND archived_at IS NULL
            """,
            (now_iso(), now_iso(), actor_id, lead_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        owner_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        sales_stage: Optional[str] = None,
        tech_id: Optional[str] = None,
        include_archived: bool = False,
        search: Optional[str] = None,
        business_region_aliases: Optional[tuple[str, ...]] = None,
    ) -> list[dict]:
        """List leads with optional filters."""
        sql = """
            SELECT DISTINCT l.*
            FROM leads l
            JOIN customers c ON l.customer_id = c.id
            LEFT JOIN customer_contacts cc
                ON cc.customer_id = c.id AND cc.archived_at IS NULL
            LEFT JOIN users owner ON l.owner_id = owner.id
            WHERE 1=1
        """
        params: list = []

        if not include_archived:
            sql += " AND l.archived_at IS NULL AND c.archived_at IS NULL"

        if owner_id:
            sql += " AND l.owner_id = ?"
            params.append(owner_id)

        if customer_id:
            sql += " AND l.customer_id = ?"
            params.append(customer_id)

        if sales_stage:
            sql += " AND l.sales_stage = ?"
            params.append(sales_stage)

        if tech_id:
            sql += """
                AND (
                    EXISTS (
                        SELECT 1 FROM pre_sales_tasks pst
                        WHERE pst.lead_id = l.id
                          AND pst.assignee_id = ?
                          AND pst.archived_at IS NULL
                    )
                    OR EXISTS (
                        SELECT 1 FROM after_sales_tasks ast
                        WHERE ast.lead_id = l.id
                          AND ast.assignee_id = ?
                          AND ast.archived_at IS NULL
                    )
                )
            """
            params.extend([tech_id, tech_id])

        if business_region_aliases:
            placeholders = ", ".join("?" for _ in business_region_aliases)
            sql += (
                " AND LOWER(TRIM(COALESCE(owner.region, ''))) "
                f"IN ({placeholders})"
            )
            params.extend(business_region_aliases)

        if search:
            sql += """ AND (
                l.title LIKE ?
                OR l.display_id LIKE ?
                OR l.legacy_inquiry_id LIKE ?
                OR l.product_category LIKE ?
                OR l.application LIKE ?
                OR c.display_name LIKE ?
                OR c.normalized_name LIKE ?
                OR c.country LIKE ?
                OR c.city LIKE ?
                OR c.address LIKE ?
                OR cc.name LIKE ?
                OR cc.email LIKE ?
                OR cc.phone LIKE ?
                OR owner.display_name LIKE ?
            )"""
            pattern = f"%{search}%"
            params.extend([pattern] * 14)

        sql += " ORDER BY l.updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_by_display_id(self, display_id: str) -> Optional[dict]:
        """Get lead by display_id."""
        cursor = self.conn.execute(
            "SELECT * FROM leads WHERE display_id = ?",
            (display_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_by_legacy_id(self, legacy_id: str) -> Optional[dict]:
        """Get lead by legacy_inquiry_id."""
        cursor = self.conn.execute(
            "SELECT * FROM leads WHERE legacy_inquiry_id = ?",
            (legacy_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    # Assignment operations
    def add_assignment(
        self,
        lead_id: str,
        user_id: str,
        assignment_type: str,
        actor_id: str,
    ) -> str:
        """Add assignment to lead."""
        self._validate_commercial_assignment(user_id, assignment_type)
        existing = self.conn.execute(
            """
            SELECT id FROM lead_assignments
            WHERE lead_id = ? AND user_id = ? AND assignment_type = ?
            """,
            (lead_id, user_id, assignment_type),
        ).fetchone()
        if existing:
            self.conn.execute(
                """
                UPDATE lead_assignments
                SET archived_at = NULL, created_at = ?, created_by = ?
                WHERE id = ?
                """,
                (now_iso(), actor_id, existing["id"]),
            )
            return existing["id"]

        assignment_id = generate_uuid()
        self.conn.execute(
            """
            INSERT INTO lead_assignments (id, lead_id, user_id, assignment_type, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (assignment_id, lead_id, user_id, assignment_type, now_iso(), actor_id),
        )
        return assignment_id

    def _validate_commercial_assignment(self, user_id: Optional[str], assignment_type: str) -> None:
        """Defense in depth for importers and other repository callers."""
        if not user_id or assignment_type not in {"owner", "collaborator"}:
            return
        member = self.conn.execute(
            "SELECT role, is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not member or not member["is_active"]:
            raise ValueError("Lead assignee must be an active member")
        if member["role"] == "tech":
            raise ValueError("Technical users cannot be lead owners or collaborators")

    def get_assignment_by_id(self, assignment_id: str) -> Optional[dict]:
        """Get active assignment by ID."""
        row = self.conn.execute(
            """
            SELECT * FROM lead_assignments
            WHERE id = ? AND archived_at IS NULL
            """,
            (assignment_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_assignments(self, lead_id: str) -> list[dict]:
        """Get all active assignments for lead."""
        cursor = self.conn.execute(
            """
            SELECT la.*, u.display_name as user_name, u.role as user_role
            FROM lead_assignments la
            JOIN users u ON la.user_id = u.id
            WHERE la.lead_id = ? AND la.archived_at IS NULL
            ORDER BY
                CASE la.assignment_type
                    WHEN 'owner' THEN 1
                    WHEN 'collaborator' THEN 2
                    WHEN 'watcher' THEN 3
                END
            """,
            (lead_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def remove_assignment(self, lead_id: str, user_id: str, assignment_type: str) -> bool:
        """Archive an assignment."""
        cursor = self.conn.execute(
            """
            UPDATE lead_assignments
            SET archived_at = ?
            WHERE lead_id = ? AND user_id = ? AND assignment_type = ? AND archived_at IS NULL
            """,
            (now_iso(), lead_id, user_id, assignment_type),
        )
        return cursor.rowcount > 0

    def archive_assignment(self, lead_id: str, assignment_id: str, actor_id: str) -> bool:
        """Archive an assignment by ID."""
        cursor = self.conn.execute(
            """
            UPDATE lead_assignments
            SET archived_at = ?
            WHERE id = ? AND lead_id = ? AND archived_at IS NULL
            """,
            (now_iso(), assignment_id, lead_id),
        )
        return cursor.rowcount > 0

    def _update_owner_assignment(self, lead_id: str, new_owner_id: str, actor_id: str) -> None:
        """Update owner assignment (archive old, create new)."""
        # Archive old owner assignment
        self.conn.execute(
            """
            UPDATE lead_assignments
            SET archived_at = ?
            WHERE lead_id = ? AND assignment_type = 'owner' AND archived_at IS NULL
            """,
            (now_iso(), lead_id),
        )
        # Create new owner assignment
        self.add_assignment(lead_id, new_owner_id, "owner", actor_id)

    def get_leads_for_user(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
        sales_stage: Optional[str] = None,
        owner_id: Optional[str] = None,
        tech_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        search: Optional[str] = None,
        business_region_aliases: Optional[tuple[str, ...]] = None,
    ) -> list[dict]:
        """Get leads where user is owner, collaborator, or watcher."""
        sql = """
            SELECT DISTINCT l.*
            FROM leads l
            JOIN customers c ON l.customer_id = c.id
            LEFT JOIN lead_assignments la ON l.id = la.lead_id AND la.archived_at IS NULL
            LEFT JOIN customer_contacts cc
                ON cc.customer_id = c.id AND cc.archived_at IS NULL
            LEFT JOIN users owner ON l.owner_id = owner.id
            WHERE l.archived_at IS NULL
              AND c.archived_at IS NULL
              AND (l.owner_id = ? OR la.user_id = ?)
        """
        params = [user_id, user_id]

        # Add optional filters
        if sales_stage:
            sql += " AND l.sales_stage = ?"
            params.append(sales_stage)

        if customer_id:
            sql += " AND l.customer_id = ?"
            params.append(customer_id)

        if owner_id:
            sql += " AND l.owner_id = ?"
            params.append(owner_id)

        if tech_id:
            sql += """
                AND (
                    EXISTS (
                        SELECT 1 FROM pre_sales_tasks pst
                        WHERE pst.lead_id = l.id
                          AND pst.assignee_id = ?
                          AND pst.archived_at IS NULL
                    )
                    OR EXISTS (
                        SELECT 1 FROM after_sales_tasks ast
                        WHERE ast.lead_id = l.id
                          AND ast.assignee_id = ?
                          AND ast.archived_at IS NULL
                    )
                )
            """
            params.extend([tech_id, tech_id])

        if business_region_aliases:
            placeholders = ", ".join("?" for _ in business_region_aliases)
            sql += (
                " AND LOWER(TRIM(COALESCE(owner.region, ''))) "
                f"IN ({placeholders})"
            )
            params.extend(business_region_aliases)

        if search:
            sql += """ AND (
                l.display_id LIKE ? OR
                l.title LIKE ? OR
                l.product_category LIKE ? OR
                l.application LIKE ? OR
                c.display_name LIKE ? OR
                c.normalized_name LIKE ? OR
                c.country LIKE ? OR
                c.city LIKE ? OR
                c.address LIKE ? OR
                cc.name LIKE ? OR
                cc.email LIKE ? OR
                cc.phone LIKE ? OR
                owner.display_name LIKE ?
            )"""
            search_pattern = f"%{search}%"
            params.extend([search_pattern] * 13)

        sql += " ORDER BY l.updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
