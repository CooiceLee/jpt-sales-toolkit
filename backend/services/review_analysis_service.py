from __future__ import annotations

from datetime import date
from typing import Optional

class ReviewAnalysisService:
    """Extracted ReviewService component."""

    def __init__(self, core):
        self.core = core

    def get_analysis_data(
        self,
        actor_id: str,
        actor_role: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        owner_id: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None,
        product_category: Optional[str] = None,
        application: Optional[str] = None,
        sales_stage: Optional[str] = None,
    ) -> dict:
        """Return read-only business review metrics for the current user scope."""
        filters = {
            "date_from": date_from,
            "date_to": date_to,
            "owner_id": owner_id,
            "region": region,
            "country": country,
            "product_category": product_category,
            "application": application,
            "sales_stage": sales_stage,
        }
        leads = self.core._visible_lead_rows(actor_id, actor_role, filters)
        activity_stats = self.core._activity_stats([lead["id"] for lead in leads])

        today = date.today()
        for lead in leads:
            stats = activity_stats.get(lead["id"], {})
            lead["follow_up_count"] = int(stats.get("follow_up_count") or 0)
            lead["activity_count"] = int(stats.get("activity_count") or 0)
            lead["last_activity_at"] = stats.get("last_activity_at")
            anchor = lead.get("last_activity_at") or lead.get("updated_at") or lead.get("created_at")
            lead["days_since_activity"] = self.core._days_since(anchor, today)
            lead["region"] = lead.get("region") or self.core._country_region(self.core._normalize_country(lead.get("country")))

        open_leads = [lead for lead in leads if lead["sales_stage"] not in {"Won", "Lost"}]
        won_leads = [lead for lead in leads if lead["sales_stage"] == "Won"]
        lost_leads = [lead for lead in leads if lead["sales_stage"] == "Lost"]
        quoted_or_closed = [
            lead for lead in leads if lead["sales_stage"] in {"Quoted", "Won", "Lost"}
        ]
        overdue_leads = [
            lead for lead in open_leads
            if lead.get("next_followup_date") and str(lead["next_followup_date"]) < today.isoformat()
        ]
        stale_leads = [
            lead for lead in open_leads
            if (lead.get("days_since_activity") or 0) >= 30
        ]

        pipeline_value = sum(self.core._num(lead.get("estimated_value")) for lead in open_leads)
        won_value = sum(self.core._num(lead.get("deal_amount")) for lead in won_leads)

        summary = {
            "total_leads": len(leads),
            "open_leads": len(open_leads),
            "won_leads": len(won_leads),
            "lost_leads": len(lost_leads),
            "pipeline_value": pipeline_value,
            "won_value": won_value,
            "average_won_value": won_value / len(won_leads) if won_leads else 0,
            "quote_rate": len(quoted_or_closed) / len(leads) if leads else 0,
            "win_rate": len(won_leads) / (len(won_leads) + len(lost_leads)) if (won_leads or lost_leads) else 0,
            "overdue_followups": len(overdue_leads),
            "stale_open_leads": len(stale_leads),
            "average_followups": (
                sum(lead["follow_up_count"] for lead in leads) / len(leads)
                if leads else 0
            ),
        }

        return {
            "filters": filters,
            "summary": summary,
            "brief": self.core._analysis_brief(summary),
            "stage_breakdown": self.core._stage_breakdown(leads),
            "owner_breakdown": self.core._group_performance(leads, "owner_name", "Unassigned"),
            "region_breakdown": self.core._group_performance(leads, "region", "Unassigned"),
            "product_breakdown": self.core._group_performance(leads, "product_category", "Unspecified"),
            "application_breakdown": self.core._group_performance(leads, "application", "Unspecified"),
            "lost_reasons": self.core._lost_reason_breakdown(lost_leads),
            "risk_leads": self.core._risk_leads(open_leads, limit=12),
            "high_value_open_leads": self.core._high_value_open_leads(open_leads, limit=12),
        }

    def get_dashboard_data(
        self,
        actor_id: str,
        actor_role: str,
    ) -> dict:
        """Get dashboard KPIs and summary data."""
        # Build base query filter
        if actor_role == "leader":
            where_clause = "archived_at IS NULL"
            params = ()
        else:
            where_clause = "archived_at IS NULL AND owner_id = ?"
            params = (actor_id,)

        conn = self.core.lead_repo.conn

        # Total leads
        total = conn.execute(
            f"SELECT COUNT(*) FROM leads WHERE {where_clause}",
            params,
        ).fetchone()[0]

        # By stage
        stage_counts = {}
        for stage in ["New", "Assigned", "Following", "Quoted", "Won", "Lost"]:
            count = conn.execute(
                f"SELECT COUNT(*) FROM leads WHERE {where_clause} AND sales_stage = ?",
                (*params, stage),
            ).fetchone()[0]
            stage_counts[stage] = count

        # Pipeline value (non-Won/Lost)
        pipeline = conn.execute(
            f"""
            SELECT COALESCE(SUM(estimated_value), 0) FROM leads
            WHERE {where_clause} AND sales_stage NOT IN ('Won', 'Lost')
            """,
            params,
        ).fetchone()[0]

        # Won value
        won_value = conn.execute(
            f"""
            SELECT COALESCE(SUM(deal_amount), 0) FROM leads
            WHERE {where_clause} AND sales_stage = 'Won'
            """,
            params,
        ).fetchone()[0]

        # Recent leads (last 7 days)
        recent = conn.execute(
            f"""
            SELECT COUNT(*) FROM leads
            WHERE {where_clause}
            AND created_at >= datetime('now', '-7 days')
            """,
            params,
        ).fetchone()[0]

        # Overdue follow-ups
        overdue = conn.execute(
            f"""
            SELECT COUNT(*) FROM leads
            WHERE {where_clause}
            AND next_followup_date < date('now')
            AND sales_stage NOT IN ('Won', 'Lost')
            """,
            params,
        ).fetchone()[0]

        # Leads with active after-sales/service issues
        service_open_count = conn.execute(
            f"""
            SELECT COUNT(*) FROM leads
            WHERE {where_clause}
            AND service_status IN ('Open', 'In Progress')
            """,
            params,
        ).fetchone()[0]

        pre_sales_active_lead_count = (
            self.core.pre_sales_read_repo.count_active_leads(actor_id, actor_role)
        )

        # By region
        region_counts = {}
        cursor = conn.execute(
            f"""
            SELECT c.region, COUNT(l.id)
            FROM leads l
            JOIN customers c ON l.customer_id = c.id
            WHERE l.archived_at IS NULL
            {"AND l.owner_id = ?" if actor_role != "leader" else ""}
            GROUP BY c.region
            """,
            (actor_id,) if actor_role != "leader" else (),
        )
        for row in cursor.fetchall():
            if row[0]:
                region_counts[row[0]] = row[1]

        return {
            "total_leads": total,
            "stage_counts": stage_counts,
            "pipeline_value": float(pipeline),
            "won_value": float(won_value),
            "recent_7_days": recent,
            "overdue_followups": overdue,
            "pre_sales_active_lead_count": pre_sales_active_lead_count,
            "service_open_count": service_open_count,
            "by_region": region_counts,
        }
