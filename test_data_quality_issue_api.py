#!/usr/bin/env python3
"""HTTP permission and lifecycle contract for imported quality issues."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import close_db
from backend.routers.deps import get_current_user
from backend.tests.data_quality_issue_fixture import actor, build_fixture


ACTIVE_OWNER = {
    "customer", "contact", "alias", "lead", "assignment", "activity",
    "pre_assigned", "pre_other", "after_assigned",
}


def listed_keys(client: TestClient, ids: dict, params: dict | None = None) -> set[str]:
    response = client.get("/api/data/quality-issues", params=params or {})
    assert response.status_code == 200, response.text
    by_id = {value: key for key, value in ids["issues"].items()}
    return {by_id[item["id"]] for item in response.json()["items"]}


def patch(client: TestClient, issue_id: str, status: str, expected: int, **extra) -> dict:
    response = client.patch(
        f"/api/data/quality-issues/{issue_id}",
        json={"status": status, "resolution_note": "test", **extra},
    )
    assert response.status_code == expected, response.text
    return response.json()


def assert_role_lists(client: TestClient, ids: dict, state: dict) -> None:
    expectations = {
        "leader": set(ids["issues"]), "sales_owner": ACTIVE_OWNER,
        "sales_collab": ACTIVE_OWNER, "sales_watcher": set(),
        "sales_other": {"other_lead"},
        "tech_assigned": {"pre_assigned", "after_assigned"},
        "tech_other": {"pre_other"},
    }
    for name, expected in expectations.items():
        state["actor"] = actor(ids, name)
        assert listed_keys(client, ids) == expected, name


def assert_api_lifecycle(client: TestClient, ids: dict, state: dict) -> None:
    issues = ids["issues"]
    state["actor"] = actor(ids, "sales_owner")
    assert patch(client, issues["lead"], "resolved", 200)["status"] == "resolved"
    assert listed_keys(client, ids, {"status": "resolved"}) == {"lead"}
    assert patch(client, issues["lead"], "open", 200)["resolved_by"] is None
    patch(client, issues["lead"], "ignored", 403)
    patch(client, issues["other_lead"], "resolved", 403)
    patch(client, issues["archived_contact"], "resolved", 403)
    patch(client, issues["customer_archived_lead"], "resolved", 403)
    state["actor"] = actor(ids, "tech_assigned")
    assert patch(client, issues["pre_assigned"], "resolved", 200)["status"] == "resolved"
    assert patch(client, issues["pre_assigned"], "open", 200)["status"] == "open"
    patch(client, issues["lead"], "resolved", 403)
    patch(client, issues["pre_assigned"], "ignored", 403)
    state["actor"] = actor(ids, "leader")
    assert patch(client, issues["unbound"], "ignored", 200)["status"] == "ignored"
    assert patch(client, issues["archived_lead"], "resolved", 200)["status"] == "resolved"
    patch(client, "missing", "resolved", 404)
    patch(client, issues["lead"], "invalid", 422)
    patch(client, issues["lead"], "open", 422, unexpected=True)


def main() -> None:
    previous = os.environ.get("JPT_DATA_DIR")
    with TemporaryDirectory(prefix="jpt_quality_api_") as tmp:
        os.environ["JPT_DATA_DIR"] = tmp
        ids = build_fixture(Path(tmp))
        state = {"actor": actor(ids, "leader")}

        async def current_user() -> dict:
            return state["actor"]

        app = create_app()
        app.dependency_overrides[get_current_user] = current_user
        with TestClient(app) as client:
            assert_role_lists(client, ids, state)
            assert_api_lifecycle(client, ids, state)
        close_db()
    if previous is None:
        os.environ.pop("JPT_DATA_DIR", None)
    else:
        os.environ["JPT_DATA_DIR"] = previous
    print("PASS: quality-issue API role boundaries and status workflow")


if __name__ == "__main__":
    main()
