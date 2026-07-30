#!/usr/bin/env python3
"""Static and query-order contracts for the split review-map service."""

from __future__ import annotations

import inspect
from pathlib import Path

from backend.services.review_map_query import build_map_query
from backend.services.review_map_service import ReviewMapService


ROOT = Path(__file__).parent
SERVICES = ROOT / "backend" / "services"
MODULES = (
    "review_map_service.py",
    "review_map_query.py",
    "review_map_grouping.py",
    "review_map_projection.py",
)


def main() -> None:
    sources = {
        name: (SERVICES / name).read_text(encoding="utf-8") for name in MODULES
    }
    for name, source in sources.items():
        assert len(source.splitlines()) <= 125, f"map service module too large: {name}"

    facade = sources["review_map_service.py"]
    for contract in ("load_map_rows", "group_map_rows", "project_map_response"):
        assert contract in facade, f"facade is missing {contract}"
    parameters = list(inspect.signature(ReviewMapService.get_map_data).parameters)
    assert parameters == [
        "self", "actor_id", "actor_role", "sales_stage", "owner_id",
        "outcome", "service_status", "region",
    ]

    filters = {
        "owner_id": "owner-1",
        "sales_stage": "Following",
        "outcome": "open",
        "service_status": "Active",
        "region": "EU",
    }
    sql, params = build_map_query("actor-1", "sales", filters)
    assert params == [
        "actor-1", "actor-1", "actor-1", "actor-1",
        "owner-1", "Following", "Active",
    ]
    clauses = (
        "l.owner_id = ? OR EXISTS",
        "l.owner_id = ? OR la.user_id = ?",
        " AND l.owner_id = ?",
        "l.sales_stage = ?",
        "l.sales_stage NOT IN ('Won', 'Lost')",
        "l.service_status = ?",
        "ORDER BY c.display_name ASC, l.updated_at DESC",
    )
    positions = [sql.index(clause) for clause in clauses]
    assert positions == sorted(positions), "map SQL clause order changed"

    leader_sql, leader_params = build_map_query("leader-1", "leader", filters)
    assert leader_params == ["owner-1", "Following", "Active"]
    assert "1 as actor_can_edit" in leader_sql
    assert "la.user_id = ?" not in leader_sql
    assert "region" not in leader_params, "region must remain a post-query filter"
    print("PASS: review-map facade, module sizes and SQL parameter-order contracts")


if __name__ == "__main__":
    main()
