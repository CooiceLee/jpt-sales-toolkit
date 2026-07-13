"""
Shared visibility checks for review, map, and trip workflows.
"""

from __future__ import annotations

from typing import Optional


class VisibilityService:
    """Centralize visible Lead/Customer/Trip checks."""

    def __init__(self, core):
        self.core = core

    def visible_lead_rows(self, actor_id: str, actor_role: str, filters: dict) -> list[dict]:
        sql = """
            SELECT DISTINCT
                l.id, l.display_id, l.title, l.sales_stage, l.service_status,
                l.owner_id, u.display_name AS owner_name,
                l.estimated_value, l.deal_amount, l.currency,
                l.product_category, l.application, l.next_followup_date,
                l.created_at, l.updated_at, l.lost_reason_code, l.lost_reason_text,
                c.id AS customer_id, c.display_name AS customer_name,
                c.country, c.city, c.region, c.lat, c.lng,
                c.geocode_source, c.geocode_confidence, c.geocode_locked
            FROM leads l
            JOIN customers c ON l.customer_id = c.id
            LEFT JOIN users u ON l.owner_id = u.id
            LEFT JOIN lead_assignments la
                ON l.id = la.lead_id AND la.archived_at IS NULL
            WHERE l.archived_at IS NULL
              AND c.archived_at IS NULL
        """
        params: list = []
        if actor_role != "leader":
            sql += " AND (l.owner_id = ? OR la.user_id = ?)"
            params.extend([actor_id, actor_id])

        if filters.get("owner_id"):
            sql += " AND l.owner_id = ?"
            params.append(filters["owner_id"])
        if filters.get("country"):
            sql += " AND (c.country = ? OR UPPER(c.country) = ?)"
            params.extend([filters["country"], str(filters["country"]).upper()])
        if filters.get("product_category"):
            sql += " AND l.product_category = ?"
            params.append(filters["product_category"])
        if filters.get("application"):
            sql += " AND l.application = ?"
            params.append(filters["application"])
        if filters.get("sales_stage"):
            sql += " AND l.sales_stage = ?"
            params.append(filters["sales_stage"])
        if filters.get("date_from"):
            sql += " AND date(l.created_at) >= date(?)"
            params.append(filters["date_from"])
        if filters.get("date_to"):
            sql += " AND date(l.created_at) <= date(?)"
            params.append(filters["date_to"])

        rows = [dict(row) for row in self.core.lead_repo.conn.execute(sql, params).fetchall()]
        region = filters.get("region")
        if region:
            rows = [
                row for row in rows
                if (row.get("region") or self.core._country_region(self.core._normalize_country(row.get("country")))) == region
            ]
        return rows

    def visible_lead_by_id(self, lead_id: str, actor_id: str, actor_role: str) -> Optional[dict]:
        rows = self.visible_lead_rows(actor_id, actor_role, {"sales_stage": None})
        for row in rows:
            if row["id"] == lead_id:
                return row
        return None

    def can_access_customer(self, customer_id: str, actor_id: str, actor_role: str) -> bool:
        if actor_role == "leader":
            row = self.core.lead_repo.conn.execute(
                "SELECT 1 FROM customers WHERE id = ? AND archived_at IS NULL",
                (customer_id,),
            ).fetchone()
            return row is not None
        sql = """
            SELECT 1
            FROM leads l
            LEFT JOIN lead_assignments la
                ON l.id = la.lead_id AND la.archived_at IS NULL
            WHERE l.customer_id = ?
              AND l.archived_at IS NULL
              AND (l.owner_id = ? OR la.user_id = ?)
            LIMIT 1
        """
        row = self.core.lead_repo.conn.execute(sql, (customer_id, actor_id, actor_id)).fetchone()
        return row is not None

    def can_access_plan(self, plan: dict, actor_id: str, actor_role: str) -> bool:
        return actor_role == "leader" or plan.get("owner_id") == actor_id or plan.get("created_by") == actor_id
