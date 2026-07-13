"""Pre-sales CRUD and task visibility regression coverage."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from backend.config import init_settings
from backend.repositories import close_db, init_db, LeadRepository, UserRepository
from backend.repositories.base import ConflictError
from backend.services import (
    AfterSalesTaskService,
    CustomerService,
    PreSalesTaskService,
)


def build_fixture(temp_dir: Path) -> dict:
    close_db()
    settings = init_settings(Path.cwd())
    settings.db_path = temp_dir / "sampling.sqlite"
    init_db(settings.db_path)

    users = UserRepository()
    ids = {
        "leader": users.create("leader", "x", "Leader", "leader"),
        "sales1": users.create("sales1", "x", "Sales One", "sales"),
        "sales2": users.create("sales2", "x", "Sales Two", "sales"),
        "tech1": users.create("tech1", "x", "Tech One", "tech"),
        "tech2": users.create("tech2", "x", "Tech Two", "tech"),
    }
    customers = CustomerService()
    customer1 = customers.create({"display_name": "Customer One"}, ids["leader"])
    customer2 = customers.create({"display_name": "Customer Two"}, ids["leader"])
    leads = LeadRepository()
    ids["lead1"] = leads.create({
        "customer_id": customer1["id"], "owner_id": ids["sales1"],
        "title": "Sample One", "sales_stage": "Following",
    }, ids["leader"])
    ids["lead2"] = leads.create({
        "customer_id": customer2["id"], "owner_id": ids["sales2"],
        "title": "Sample Two", "sales_stage": "Following",
    }, ids["leader"])

    pre_sales = PreSalesTaskService()
    ids["task1"] = pre_sales.create(ids["lead1"], {
        "assignee_id": ids["tech1"],
        "request_json": json.dumps({"sample_params": "10W blue sample"}),
    }, ids["sales1"])["id"]
    ids["task2"] = pre_sales.create(ids["lead2"], {
        "assignee_id": ids["tech2"],
        "request_json": json.dumps({"sample_params": "20W green sample"}),
    }, ids["sales2"])["id"]

    after_sales = AfterSalesTaskService()
    after_sales.create(ids["lead1"], {
        "assignee_id": ids["tech1"], "issue_type": "Technical",
        "issue_description": "Issue one",
    }, ids["sales1"])
    after_sales.create(ids["lead2"], {
        "assignee_id": ids["tech2"], "issue_type": "Quality",
        "issue_description": "Issue two",
    }, ids["sales2"])
    return ids


def actor(ids: dict, name: str, role: str) -> dict:
    return {"id": ids[name], "role": role}


def test_visibility(ids: dict) -> None:
    pre_sales = PreSalesTaskService()
    after_sales = AfterSalesTaskService()
    leader = actor(ids, "leader", "leader")
    sales1 = actor(ids, "sales1", "sales")
    tech1 = actor(ids, "tech1", "tech")
    assert len(pre_sales.list(leader)) == 2
    assert [task["id"] for task in pre_sales.list(sales1)] == [ids["task1"]]
    assert [task["id"] for task in pre_sales.list(tech1)] == [ids["task1"]]
    assert len(after_sales.list(leader)) == 2
    assert len(after_sales.list(sales1)) == 1
    assert len(after_sales.list(tech1)) == 1


def test_crud_and_conflict(ids: dict) -> None:
    service = PreSalesTaskService()
    original = service.task_repo.get_by_id(ids["task1"])
    updated = service.update(ids["task1"], {
        "status": "Completed",
        "result_json": json.dumps({"sample_result": "Success"}),
        "due_date": None,
    }, ids["sales1"], original["row_version"])
    assert updated["status"] == "Completed"
    assert updated["due_date"] is None
    try:
        service.update(ids["task1"], {"status": "Open"}, ids["sales1"], original["row_version"])
        raise AssertionError("stale row_version was accepted")
    except ConflictError:
        pass

    assert service.archive(ids["task1"], ids["sales1"])
    leader = actor(ids, "leader", "leader")
    assert service.list(leader, {"lead_id": ids["lead1"]}) == []
    archived = service.list(leader, {"lead_id": ids["lead1"], "include_archived": True})
    assert len(archived) == 1 and archived[0]["archived_at"]
    assert service.restore(ids["task1"], ids["sales1"])
    assert len(service.list(leader, {"lead_id": ids["lead1"]})) == 1


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_sampling_") as directory:
        ids = build_fixture(Path(directory))
        test_visibility(ids)
        test_crud_and_conflict(ids)
        close_db()
    print("PASS: pre-sales CRUD, visibility, archive/restore and conflict checks")


if __name__ == "__main__":
    main()
