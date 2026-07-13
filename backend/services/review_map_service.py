from __future__ import annotations

from collections import defaultdict
from typing import Optional

class ReviewMapService:
    """Extracted ReviewService component."""

    def __init__(self, core):
        self.core = core

    def get_map_data(
        self,
        actor_id: str,
        actor_role: str,
        sales_stage: Optional[str] = None,
        owner_id: Optional[str] = None,
        outcome: Optional[str] = None,
        service_status: Optional[str] = None,
        region: Optional[str] = None,
    ) -> dict:
        """Get customer locations for map display and trip-planning review."""
        conn = self.core.customer_repo.conn

        sql = """
            SELECT DISTINCT
                l.id as lead_id,
                l.display_id,
                l.title,
                l.sales_stage,
                l.service_status,
                l.owner_id,
                l.estimated_value,
                l.deal_amount,
                l.currency,
                l.product_category,
                l.application,
                l.next_followup_date,
                l.updated_at as lead_updated_at,
                u.display_name as owner_name,
                c.id as customer_id,
                c.display_name,
                c.country,
                c.city,
                c.address,
                c.normalized_address,
                c.lat,
                c.lng,
                c.region,
                c.geocode_source,
                c.geocode_confidence,
                c.geocode_locked
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
            sql += """
                AND (l.owner_id = ? OR la.user_id = ?)
            """
            params.extend([actor_id, actor_id])

        if owner_id:
            sql += " AND l.owner_id = ?"
            params.append(owner_id)

        if sales_stage:
            sql += " AND l.sales_stage = ?"
            params.append(sales_stage)

        if outcome == "won":
            sql += " AND l.sales_stage = 'Won'"
        elif outcome == "lost":
            sql += " AND l.sales_stage = 'Lost'"
        elif outcome == "open":
            sql += " AND l.sales_stage NOT IN ('Won', 'Lost')"

        if service_status:
            sql += " AND l.service_status = ?"
            params.append(service_status)

        sql += " ORDER BY c.display_name ASC, l.updated_at DESC"

        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]

        grouped: dict[str, dict] = {}
        for row in rows:
            country_code = self.core._normalize_country(row.get("country"))
            derived_region = row.get("region") or self.core._country_region(country_code)
            if region and derived_region != region:
                continue

            customer_id = row["customer_id"]
            group = grouped.setdefault(
                customer_id,
                {
                    "customer_id": customer_id,
                    "customer_name": row["display_name"],
                    "country": row.get("country"),
                    "country_code": country_code,
                    "country_name": self.core._country_name(country_code),
                    "city": row.get("city"),
                    "address": row.get("address"),
                    "normalized_address": row.get("normalized_address"),
                    "region": derived_region,
                    "raw_lat": row.get("lat"),
                    "raw_lng": row.get("lng"),
                    "geocode_source": row.get("geocode_source"),
                    "geocode_confidence": row.get("geocode_confidence"),
                    "geocode_locked": bool(row.get("geocode_locked")),
                    "leads": [],
                    "owners": {},
                    "stages": set(),
                    "total_won": 0.0,
                },
            )

            lead = {
                "id": row["lead_id"],
                "display_id": row["display_id"],
                "title": row["title"],
                "sales_stage": row["sales_stage"],
                "service_status": row["service_status"],
                "owner_id": row["owner_id"],
                "owner_name": row.get("owner_name"),
                "estimated_value": float(row["estimated_value"]) if row.get("estimated_value") else 0,
                "deal_amount": float(row["deal_amount"]) if row.get("deal_amount") else 0,
                "currency": row.get("currency"),
                "product_category": row.get("product_category"),
                "application": row.get("application"),
                "next_followup_date": row.get("next_followup_date"),
                "updated_at": row["lead_updated_at"],
            }
            group["leads"].append(lead)
            group["stages"].add(row["sales_stage"])
            if row.get("owner_id"):
                group["owners"][row["owner_id"]] = row.get("owner_name") or row["owner_id"]
            if row["sales_stage"] == "Won" and row.get("deal_amount"):
                group["total_won"] += float(row["deal_amount"])

        points = []
        missing_locations = []
        fallback_offsets: dict[str, int] = {}

        for group in grouped.values():
            lat = group.pop("raw_lat")
            lng = group.pop("raw_lng")
            country_code = group["country_code"]

            coordinate_quality = "exact"
            needs_geocode = False

            if lat is not None and lng is not None:
                is_verified = (
                    bool(group.get("geocode_locked"))
                    or group.get("geocode_source") == "manual"
                    or group.get("geocode_confidence") == "high"
                )
                if not is_verified:
                    coordinate_quality = "auto_approximate"
                    needs_geocode = True
            else:
                fallback = self.core._country_center(country_code)
                if fallback:
                    offset_index = fallback_offsets.get(country_code, 0)
                    fallback_offsets[country_code] = offset_index + 1
                    lat = fallback["lat"] + (offset_index % 5) * 0.18
                    lng = fallback["lng"] + (offset_index // 5) * 0.18
                    coordinate_quality = "country_fallback"
                    needs_geocode = True
                else:
                    missing_locations.append(self.core._map_missing_location(group))
                    continue

            leads = group["leads"]
            latest_lead = max(leads, key=lambda lead: lead.get("updated_at") or "")
            point = {
                **group,
                "id": group["customer_id"],
                "name": group["customer_name"],
                "lat": lat,
                "lng": lng,
                "coordinate_quality": coordinate_quality,
                "needs_geocode": needs_geocode,
                "lead_count": len(leads),
                "latest_stage": latest_lead["sales_stage"],
                "latest_lead_id": latest_lead["id"],
                "latest_lead_display_id": latest_lead["display_id"],
                "owners": list(group["owners"].values()),
                "stages": sorted(group["stages"]),
                "won_count": sum(1 for lead in leads if lead["sales_stage"] == "Won"),
                "lost_count": sum(1 for lead in leads if lead["sales_stage"] == "Lost"),
                "open_count": sum(1 for lead in leads if lead["sales_stage"] not in {"Won", "Lost"}),
            }
            points.append(point)

        return {
            "filters": {
                "sales_stage": sales_stage,
                "owner_id": owner_id,
                "outcome": outcome,
                "service_status": service_status,
                "region": region,
            },
            "summary": {
                "customers": len(grouped),
                "points": len(points),
                "exact_points": sum(1 for point in points if point["coordinate_quality"] == "exact"),
                "approximate_points": sum(1 for point in points if point["needs_geocode"]),
                "missing_locations": len(missing_locations),
                "leads": sum(point["lead_count"] for point in points) + sum(item["lead_count"] for item in missing_locations),
                "won_customers": sum(1 for point in points if point["won_count"] > 0),
                "open_customers": sum(1 for point in points if point["open_count"] > 0),
                "lost_customers": sum(1 for point in points if point["lost_count"] > 0),
            },
            "points": points,
            "missing_locations": missing_locations,
        }
