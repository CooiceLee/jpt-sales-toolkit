"""Temporary-database fixture for pre-sales read-model coverage."""

from __future__ import annotations

import json
from pathlib import Path

from backend.config import init_settings
from backend.repositories import (
    ActivityRepository,
    CustomerRepository,
    LeadRepository,
    PreSalesTaskRepository,
    UserRepository,
    close_db,
    init_db,
)


def build_fixture(directory: Path) -> dict:
    close_db()
    settings = init_settings(Path.cwd())
    settings.db_path = directory / "pre-sales-read-model.sqlite"
    init_db(settings.db_path)

    users = UserRepository()
    ids = {
        "leader": users.create("leader.read", "x", "Leader", "leader"),
        "sales1": users.create("sales1.read", "x", "Sales One", "sales"),
        "sales2": users.create("sales2.read", "x", "Sales Two", "sales"),
        "tech1": users.create("tech1.read", "x", "Tech One", "tech"),
        "tech2": users.create("tech2.read", "x", "Tech Two", "tech"),
    }
    customers, leads = CustomerRepository(), LeadRepository()
    for number in range(1, 7):
        customer_id = customers.create(
            {
                "display_name": f"Customer {number}",
                "normalized_name": f"customer {number}",
            },
            ids["leader"],
        )
        owner_id = ids["sales1"] if number in {1, 4, 5} else ids["sales2"]
        ids[f"lead{number}"] = leads.create(
            {
                "customer_id": customer_id,
                "owner_id": owner_id,
                "title": f"Lead {number}",
                "sales_stage": "Following",
            },
            ids["leader"],
        )
    leads.add_assignment(
        ids["lead2"], ids["sales1"], "collaborator", ids["leader"]
    )
    leads.conn.commit()

    tasks = PreSalesTaskRepository()
    tasks.create(ids["lead1"], {"assignee_id": ids["tech1"]}, ids["leader"])
    tasks.create(ids["lead1"], {
        "assignee_id": ids["tech1"], "status": "In Progress",
    }, ids["leader"])
    tasks.create(ids["lead2"], {
        "assignee_id": ids["tech1"], "status": "In Progress",
    }, ids["leader"])
    tasks.create(ids["lead3"], {"assignee_id": ids["tech2"]}, ids["leader"])
    tasks.create(ids["lead4"], {
        "assignee_id": ids["tech1"], "status": "Completed",
    }, ids["leader"])
    archived = tasks.create(
        ids["lead5"], {"assignee_id": ids["tech1"]}, ids["leader"]
    )
    tasks.archive(archived, ids["leader"])
    tasks.create(ids["lead6"], {"assignee_id": ids["tech1"]}, ids["leader"])
    leads.archive(ids["lead6"], ids["leader"])
    return ids


def seed_follow_ups(ids: dict) -> None:
    activities = ActivityRepository()
    public_payload = {
        "method": "Email",
        "content": "Public update",
        "status": "completed",
        "next_action": "Confirm sample schedule",
        "next_action_date": "2026-07-20",
        "occurred_at_raw": "7月上旬",
        "estimated_value": 999999,
    }
    rows = (
        ("Public update", public_payload, "all", True, "2026-07-01T09:00:00"),
        ("Internal update", {"content": "Internal update"}, "internal", True,
         "2026-07-02T09:00:00"),
        ("Leader-only update", {"content": "Leader-only update"}, "owner_only", True,
         "2026-07-03T09:00:00"),
        ("Not formal", {"content": "Not formal"}, "all", False,
         "2026-07-04T09:00:00"),
        ("Archived update", {"content": "Archived update"}, "all", True,
         "2026-07-05T09:00:00"),
    )
    archived_id = None
    for summary, payload, visibility, formal, created_at in rows:
        activity_id = activities.create(
            ids["lead1"], ids["sales1"], "follow_up", summary,
            json.dumps(payload), visibility, formal, created_at=created_at,
        )
        if summary == "Archived update":
            archived_id = activity_id
    activities.archive(archived_id)
