from __future__ import annotations

from typing import Optional

from .review_map_grouping import group_map_rows
from .review_map_projection import project_map_response
from .review_map_query import load_map_rows

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
        filters = {
            "sales_stage": sales_stage,
            "owner_id": owner_id,
            "outcome": outcome,
            "service_status": service_status,
            "region": region,
        }
        rows = load_map_rows(
            self.core.customer_repo.conn, actor_id, actor_role, filters
        )
        grouped = group_map_rows(rows, self.core, region)
        return project_map_response(self.core, grouped, filters)
