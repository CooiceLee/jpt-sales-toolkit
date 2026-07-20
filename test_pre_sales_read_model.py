"""Pre-sales workload counts and latest follow-up read-model regression."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.repositories import close_db
from backend.services import LeadService, ReviewService
from backend.tests.pre_sales_read_model_fixture import (
    build_fixture,
    seed_follow_ups,
)


def test_scoped_active_counts(ids: dict) -> None:
    service = ReviewService()
    expected = {
        ("leader", "leader"): 3,
        ("sales1", "sales"): 2,
        ("sales2", "sales"): 2,
        ("tech1", "tech"): 2,
        ("tech2", "tech"): 1,
    }
    for (actor_name, role), count in expected.items():
        dashboard = service.get_dashboard_data(ids[actor_name], role)
        assert dashboard["pre_sales_active_lead_count"] == count, (
            actor_name, dashboard["pre_sales_active_lead_count"]
        )


def test_latest_follow_up_visibility_and_shape(ids: dict) -> None:
    service = LeadService()
    leader = service.get(ids["lead1"], ids["leader"], "leader")
    sales = service.get(ids["lead1"], ids["sales1"], "sales")
    tech = service.get(ids["lead1"], ids["tech1"], "tech")

    assert leader["latest_follow_up_summary"] == "Leader-only update"
    assert sales["latest_follow_up_summary"] == "Internal update"
    assert tech["latest_follow_up_summary"] == "Public update"
    assert tech["latest_follow_up_at"] == "2026-07-01T09:00:00"
    assert tech["latest_follow_up"]["method"] == "Email"
    assert tech["latest_follow_up"]["next_action"] == "Confirm sample schedule"
    assert tech["latest_follow_up"]["occurred_at_raw"] == "7月上旬"
    assert "estimated_value" not in tech["latest_follow_up"]

    sales_list = service.list(ids["sales1"], "sales")
    tech_list = service.list(ids["tech1"], "tech")
    sales_row = next(item for item in sales_list if item["id"] == ids["lead1"])
    tech_row = next(item for item in tech_list if item["id"] == ids["lead1"])
    assert sales_row["latest_follow_up_summary"] == "Internal update"
    assert tech_row["latest_follow_up_summary"] == "Public update"


def test_list_batches_latest_follow_up(ids: dict) -> None:
    service = LeadService()
    statements: list[str] = []
    service.activity_repo.conn.set_trace_callback(statements.append)
    try:
        rows = service.list(ids["leader"], "leader")
    finally:
        service.activity_repo.conn.set_trace_callback(None)

    row = next(item for item in rows if item["id"] == ids["lead1"])
    assert row["latest_follow_up_summary"] == "Leader-only update"
    latest_queries = [
        statement for statement in statements
        if "WITH ranked_follow_ups AS" in statement
    ]
    assert len(latest_queries) == 1, "latest follow-ups must use one batch query"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_pre_sales_read_") as directory:
        ids = build_fixture(Path(directory))
        seed_follow_ups(ids)
        test_scoped_active_counts(ids)
        test_latest_follow_up_visibility_and_shape(ids)
        test_list_batches_latest_follow_up(ids)
        close_db()
    print("PASS: pre-sales active counts and batched latest follow-up read model")


if __name__ == "__main__":
    main()
