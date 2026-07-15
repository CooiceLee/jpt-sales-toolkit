#!/usr/bin/env python3
"""Controlled XLSX import permissions, rollback, and idempotency regression."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import UserRepository, close_db, get_db, init_db
from backend.routers.deps import get_current_user
from backend.services.spreadsheet_import import SpreadsheetImportService
from backend.services.spreadsheet_import.errors import ImportBlockedError, SpreadsheetImportError


def canonical_for(content: bytes, blocked: bool = False) -> dict:
    ref = {"sheet": "商机", "row": 4, "record_key": "商机:0004"}
    return {
        "format": "JPT-XLSX-1.0-canonical", "dataset_id": "test-dataset",
        "source_hash": hashlib.sha256(content).hexdigest(),
        "source": {"filename": "test.xlsx", "kind": "test-sheet"},
        "entities": {
            "customers": [{"external_key": "CUS-1", "source_ref": ref,
                           "display_name": "Example GmbH", "country": "Germany",
                           "website": "https://before.test"}],
            "aliases": [{"external_key": "ALS-1", "source_ref": ref,
                         "customer_key": "CUS-1", "alias_name": "Example Europe"}],
            "contacts": [{"external_key": "CON-1", "source_ref": ref,
                          "customer_key": "CUS-1", "name": "Alice",
                          "email": "a@example.test", "is_primary": "TRUE"}],
            "leads": [{"external_key": "LEAD-1", "source_ref": ref,
                       "customer_key": "CUS-1", "primary_contact_key": "CON-1",
                       "title": "Laser Project", "owner_username_token": "old-sales",
                       "sales_stage": "Following", "fulfillment_status": "Not Started"}],
            "assignments": [{"external_key": "ASG-1", "source_ref": ref,
                             "lead_key": "LEAD-1", "member_username_token": "old-collab",
                             "assignment_type": "collaborator"}],
            "activities": [{"external_key": "ACT-1", "source_ref": ref,
                            "lead_key": "LEAD-1", "actor_username_token": "old-sales",
                            "activity_type": "follow_up", "content": "Called customer"}],
            "pre_sales_tasks": [{"external_key": "PRE-1", "source_ref": ref,
                                 "lead_key": "LEAD-1", "assignee_username_token": "old-tech",
                                 "request_description": "Check optics", "status": "Open"}],
            "after_sales_tasks": [{"external_key": "AFT-1", "source_ref": ref,
                                   "lead_key": "LEAD-1", "assignee_username_token": "old-tech",
                                   "issue_type": "Technical", "issue_description": "Alignment",
                                   "status": "Open"}],
        },
        "source_trace": [{"source_ref": ref, "row_hash": "row-hash"}],
        "issues": ([{"severity": "blocker", "code": "source_blocker", "source_ref": ref,
                     "entity_key": "LEAD-1", "message": "Needs correction"}] if blocked else
                   [{"severity": "warning", "code": "source_warning", "source_ref": ref,
                     "entity_key": "LEAD-1", "message": "Review imported note"}]) +
                  [{"severity": "warning", "code": "excluded_pollution",
                    "source_ref": {"sheet": "赢单", "row": 160,
                                   "record_key": "won:0160"},
                    "message": "Stray copied value was excluded"}],
        "member_name_tokens": [
            {"username_token": "old-sales", "raw_names": ["Legacy Sales"]},
            {"username_token": "old-collab", "raw_names": ["Legacy Collaborator"]},
            {"username_token": "old-tech", "raw_names": ["Legacy Tech"]},
        ],
        "summary": {"can_import": not blocked},
    }


def parser(content: bytes, _filename: str) -> dict:
    return canonical_for(content)


def default_value_canonical(content: bytes, report_omissions: bool = False) -> dict:
    result = canonical_for(content)
    entities = result["entities"]
    entities["aliases"], entities["contacts"], entities["assignments"] = [], [], []
    lead = entities["leads"][0]
    lead.update({"external_key": "LEAD-DEFAULT", "fulfillment_status": ""})
    for field in ("primary_contact_key", "sales_stage", "service_status"):
        lead.pop(field, None)
    activity = entities["activities"][0]
    activity.update({"external_key": "ACT-DEFAULT", "lead_key": "LEAD-DEFAULT",
                     "activity_type": "", "content": "", "occurred_at": ""})
    activity.pop("visibility", None)
    pre_task = entities["pre_sales_tasks"][0]
    pre_task.update({"external_key": "PRE-DEFAULT", "lead_key": "LEAD-DEFAULT",
                     "status": ""})
    after_task = entities["after_sales_tasks"][0]
    after_task.update({"external_key": "AFT-DEFAULT", "lead_key": "LEAD-DEFAULT",
                       "status": "", "issue_description": ""})
    after_task.pop("issue_type", None)
    result["issues"] = []
    if report_omissions:
        omitted = {
            "LEAD-DEFAULT": ("sales_stage",),
            "ACT-DEFAULT": ("activity_type", "occurred_at", "content", "visibility"),
            "PRE-DEFAULT": ("status",),
            "AFT-DEFAULT": ("issue_type", "status", "issue_description"),
        }
        for external_key, fields in omitted.items():
            for field in fields:
                result["issues"].append({
                    "severity": "blocker", "code": "missing_required_field",
                    "source_ref": lead["source_ref"], "entity_key": external_key,
                    "field": field, "message": f"Required field is empty: {field}",
                })
    return result


def action_parser(action: str):
    def parse(content: bytes, _filename: str) -> dict:
        result = canonical_for(content)
        for items in result["entities"].values():
            for index, item in enumerate(items):
                items[index] = {
                    "external_key": item["external_key"],
                    "source_ref": item["source_ref"], "action": action,
                }
        return result
    return parse


def setup(path: Path) -> tuple[dict, dict]:
    close_db(); init_db(path)
    users = UserRepository()
    ids = {
        "leader": users.create("leader", "x", "Leader", "leader"),
        "sales": users.create("sales", "x", "Sales", "sales"),
        "collab": users.create("collab", "x", "Collaborator", "sales"),
        "tech": users.create("tech", "x", "Tech", "tech"),
    }
    actor = {"id": ids["leader"], "role": "leader"}
    return ids, actor


def resolutions(ids: dict) -> dict:
    return {"member_mappings": {
        "old-sales": ids["sales"], "old-collab": ids["collab"], "old-tech": ids["tech"],
    }, "customer_mappings": {"CUS-1": "__CREATE__"}, "excluded_records": []}


def bound_id(conn, kind: str, external_key: str) -> str:
    row = conn.execute(
        """SELECT local_entity_id FROM import_bindings
           WHERE dataset_id = 'test-dataset' AND entity_type = ? AND external_key = ?""",
        (kind, external_key),
    ).fetchone()
    assert row, (kind, external_key)
    return row[0]


def assert_preflight_boundaries(conn, ids, actor):
    content = b"xlsx-fixture-a"
    service = SpreadsheetImportService(conn, parser)
    unknown = service.preflight(content, "test.xlsx", {}, actor)
    assert not unknown["can_commit"]
    assert {item["code"] for item in unknown["issues"]} >= {"unknown_member"}
    wrong = resolutions(ids)
    wrong["member_mappings"]["old-sales"] = ids["tech"]
    mismatch = service.preflight(content, "test.xlsx", wrong, actor)
    assert not mismatch["can_commit"]
    assert any(item["code"] == "role_mismatch" and item["field"] == "owner" for item in mismatch["issues"])
    excluded = service.preflight(
        content, "test.xlsx", {**resolutions(ids), "excluded_records": ["LEAD-1"]}, actor
    )
    assert excluded["can_commit"] and excluded["summary"]["entities"]["leads"] == 0
    assert all(excluded["summary"]["entities"][kind] == 0 for kind in (
        "assignments", "activities", "pre_sales_tasks", "after_sales_tasks"
    ))
    excluded_row = service.preflight(
        content, "test.xlsx", {"excluded_records": ["商机:0004"]}, actor
    )
    assert not excluded_row["can_commit"] and excluded_row["summary"]["total"] == 0
    assert any(item["code"] == "no_import_records" for item in excluded_row["issues"])
    try:
        service.preflight(content, "test.xlsx", {}, {"id": ids["sales"], "role": "sales"})
    except SpreadsheetImportError as exc:
        assert exc.code == "leader_required" and exc.status_code == 403
    else:
        raise AssertionError("Sales must not run spreadsheet preflight")


def assert_rollback_and_blocking(conn, ids, actor):
    content = b"xlsx-fixture-a"
    def fail(_conn, _result):
        raise RuntimeError("forced failure")
    service = SpreadsheetImportService(conn, parser, before_complete=fail)
    try:
        service.commit(content, "test.xlsx", resolutions(ids), hashlib.sha256(content).hexdigest(), actor)
    except RuntimeError as exc:
        assert "forced failure" in str(exc)
    else:
        raise AssertionError("forced failure must escape")
    for table in ("customers", "leads", "import_bindings", "import_batches",
                  "data_quality_issues", "member_import_aliases"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table

    lifecycle = SpreadsheetImportService(conn, action_parser("ARCHIVE"))
    lifecycle_report = lifecycle.preflight(content, "test.xlsx", resolutions(ids), actor)
    assert not lifecycle_report["can_commit"]
    assert any(item["code"] == "unknown_lifecycle_target" for item in lifecycle_report["issues"])

    blocked_parser = lambda value, _name: canonical_for(value, blocked=True)
    blocked = SpreadsheetImportService(conn, blocked_parser)
    try:
        blocked.commit(content, "test.xlsx", resolutions(ids), hashlib.sha256(content).hexdigest(), actor)
    except ImportBlockedError as exc:
        assert not exc.report["can_commit"]
    else:
        raise AssertionError("source blockers must stop import")
    assert conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 0


def assert_commit_idempotency(conn, ids, actor):
    content = b"xlsx-fixture-a"
    expected = hashlib.sha256(content).hexdigest()
    service = SpreadsheetImportService(conn, parser)
    first = service.commit(content, "test.xlsx", resolutions(ids), expected, actor)
    reused = service.preflight(content, "test.xlsx", {}, actor)
    assert reused["can_commit"]
    owner_mapping = next(item for item in reused["member_mappings"]
                         if item["source_name"] == "old-sales" and item["purpose"] == "owner")
    assert owner_mapping["status"] == "resolved"
    assert any(item["id"] == ids["sales"] for item in owner_mapping["candidates"])
    second = service.commit(content, "test.xlsx", resolutions(ids), expected, actor)
    assert first["counts"]["leads"]["created"] == 1
    assert second["counts"]["leads"]["updated"] == 1
    expected_rows = {"customers": 1, "customer_aliases": 1, "customer_contacts": 1,
                     "leads": 1, "lead_activities": 1, "pre_sales_tasks": 1,
                     "after_sales_tasks": 1, "import_bindings": 8, "import_batches": 2,
                     "data_quality_issues": 4}
    for table, count in expected_rows.items():
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == count, table
    assert conn.execute("SELECT owner_id FROM leads").fetchone()[0] == ids["sales"]
    assert conn.execute("SELECT COUNT(*) FROM leads WHERE owner_id = ?", (ids["tech"],)).fetchone()[0] == 0
    assert conn.execute("SELECT is_primary FROM customer_contacts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM member_import_aliases").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM data_quality_issues WHERE status = 'open'").fetchone()[0] == 1
    pollution = conn.execute(
        """SELECT status, resolution_note FROM data_quality_issues
           WHERE issue_code = 'excluded_pollution' ORDER BY created_at DESC LIMIT 1"""
    ).fetchone()
    assert pollution[0] == "resolved" and "discarded" in pollution[1]
    try:
        service.commit(b"changed", "test.xlsx", resolutions(ids), expected, actor)
    except SpreadsheetImportError as exc:
        assert exc.code == "source_hash_mismatch" and exc.status_code == 409
    else:
        raise AssertionError("changed workbook must require a new preflight")

    def forbidden_clear_parser(value, _filename):
        result = canonical_for(value)
        result["issues"] = []
        result["entities"]["leads"][0]["sales_stage"] = "__CLEAR__"
        result["entities"]["activities"][0]["content"] = "__CLEAR__"
        result["entities"]["pre_sales_tasks"][0]["status"] = "__CLEAR__"
        result["entities"]["after_sales_tasks"][0]["issue_description"] = "__CLEAR__"
        return result
    forbidden = SpreadsheetImportService(conn, forbidden_clear_parser).preflight(
        b"xlsx-forbidden-clear", "test.xlsx", {}, actor
    )
    assert not forbidden["can_commit"]
    rejected = {(item["entity_type"], item["field"]) for item in forbidden["issues"]
                if item["code"] == "cannot_clear_required_field"}
    assert rejected >= {("leads", "sales_stage"), ("activities", "content"),
                        ("pre_sales_tasks", "status"),
                        ("after_sales_tasks", "issue_description")}

    def clear_parser(value, _filename):
        result = canonical_for(value)
        result["entities"]["customers"][0]["website"] = "__CLEAR__"
        result["entities"]["contacts"][0]["is_primary"] = "__CLEAR__"
        result["entities"]["leads"][0]["primary_contact_key"] = "__CLEAR__"
        result["entities"]["activities"][0]["actor_username_token"] = "__CLEAR__"
        result["entities"]["pre_sales_tasks"][0]["assignee_username_token"] = "__CLEAR__"
        result["entities"]["after_sales_tasks"][0]["assignee_username_token"] = "__CLEAR__"
        return result
    clear_content = b"xlsx-clear"
    SpreadsheetImportService(conn, clear_parser).commit(
        clear_content, "test.xlsx", {}, hashlib.sha256(clear_content).hexdigest(), actor
    )
    assert conn.execute("SELECT website FROM customers").fetchone()[0] is None
    assert conn.execute("SELECT is_primary FROM customer_contacts").fetchone()[0] == 0
    assert conn.execute("SELECT primary_contact_id FROM leads").fetchone()[0] is None
    assert conn.execute("SELECT actor_id FROM lead_activities").fetchone()[0] is None
    assert conn.execute("SELECT assignee_id FROM pre_sales_tasks").fetchone()[0] is None
    assert conn.execute("SELECT assignee_id FROM after_sales_tasks").fetchone()[0] is None

    _assert_lifecycle(conn, actor, "ARCHIVE", True)
    _assert_lifecycle(conn, actor, "RESTORE", False)
    _assert_partial_upsert_defaults(conn, actor)


def _assert_partial_upsert_defaults(conn, actor):
    create_content = b"xlsx-default-create"
    create_service = SpreadsheetImportService(
        conn, lambda value, _name: default_value_canonical(value)
    )
    created = create_service.preflight(create_content, "test.xlsx", {}, actor)
    assert created["can_commit"], created["issues"]
    create_service.commit(
        create_content, "test.xlsx", {}, hashlib.sha256(create_content).hexdigest(), actor
    )
    lead_id = bound_id(conn, "leads", "LEAD-DEFAULT")
    activity_id = bound_id(conn, "activities", "ACT-DEFAULT")
    pre_id = bound_id(conn, "pre_sales_tasks", "PRE-DEFAULT")
    after_id = bound_id(conn, "after_sales_tasks", "AFT-DEFAULT")
    assert tuple(conn.execute(
        "SELECT sales_stage, fulfillment_status, service_status FROM leads WHERE id = ?",
        (lead_id,),
    ).fetchone()) == ("New", "Not Started", "None")
    activity = conn.execute(
        """SELECT action_type, visibility, is_formal_follow_up, summary, created_at
           FROM lead_activities WHERE id = ?""", (activity_id,),
    ).fetchone()
    assert tuple(activity[:4]) == ("comment", "all", 0, "Imported activity")
    assert activity[4]
    assert conn.execute("SELECT status FROM pre_sales_tasks WHERE id = ?", (pre_id,)).fetchone()[0] == "Open"
    assert tuple(conn.execute(
        "SELECT issue_type, status, issue_description FROM after_sales_tasks WHERE id = ?",
        (after_id,),
    ).fetchone()) == ("Other", "Open", "Imported after-sales issue")

    preserved_at = "2025-02-03T04:05:06+00:00"
    conn.execute(
        """UPDATE leads SET sales_stage = 'Quoted', fulfillment_status = 'In Progress',
           service_status = 'Closed' WHERE id = ?""", (lead_id,),
    )
    conn.execute("UPDATE pre_sales_tasks SET status = 'Completed' WHERE id = ?", (pre_id,))
    conn.execute(
        """UPDATE after_sales_tasks SET issue_type = 'Delivery', status = 'Closed',
           issue_description = 'Keep issue' WHERE id = ?""", (after_id,),
    )
    conn.execute(
        """UPDATE lead_activities SET action_type = 'system', visibility = 'owner_only',
           is_formal_follow_up = 1, summary = 'Keep activity', created_at = ? WHERE id = ?""",
        (preserved_at, activity_id),
    )
    conn.commit()

    update_content = b"xlsx-default-update"
    update_service = SpreadsheetImportService(
        conn, lambda value, _name: default_value_canonical(value, True)
    )
    updated = update_service.preflight(update_content, "test.xlsx", {}, actor)
    assert updated["can_commit"], updated["issues"]
    update_service.commit(
        update_content, "test.xlsx", {}, hashlib.sha256(update_content).hexdigest(), actor
    )
    assert tuple(conn.execute(
        "SELECT sales_stage, fulfillment_status, service_status FROM leads WHERE id = ?",
        (lead_id,),
    ).fetchone()) == ("Quoted", "In Progress", "Closed")
    assert tuple(conn.execute(
        """SELECT action_type, visibility, is_formal_follow_up, summary, created_at
           FROM lead_activities WHERE id = ?""", (activity_id,),
    ).fetchone()) == ("system", "owner_only", 1, "Keep activity", preserved_at)
    assert conn.execute("SELECT status FROM pre_sales_tasks WHERE id = ?", (pre_id,)).fetchone()[0] == "Completed"
    assert tuple(conn.execute(
        "SELECT issue_type, status, issue_description FROM after_sales_tasks WHERE id = ?",
        (after_id,),
    ).fetchone()) == ("Delivery", "Closed", "Keep issue")

    false_content = b"xlsx-explicit-false"
    def false_parser(value, _name):
        result = default_value_canonical(value)
        result["entities"]["activities"][0]["is_formal_follow_up"] = "FALSE"
        return result
    SpreadsheetImportService(conn, false_parser).commit(
        false_content, "test.xlsx", {}, hashlib.sha256(false_content).hexdigest(), actor
    )
    assert conn.execute(
        "SELECT is_formal_follow_up FROM lead_activities WHERE id = ?", (activity_id,)
    ).fetchone()[0] == 0


def _assert_lifecycle(conn, actor, action, should_be_archived):
    content = f"xlsx-{action.lower()}".encode()
    service = SpreadsheetImportService(conn, action_parser(action))
    report = service.preflight(content, "test.xlsx", {}, actor)
    assert report["can_commit"], report["issues"]
    service.commit(content, "test.xlsx", {}, hashlib.sha256(content).hexdigest(), actor)
    tables = {
        "customers": "customers", "aliases": "customer_aliases",
        "contacts": "customer_contacts", "leads": "leads",
        "assignments": "lead_assignments", "activities": "lead_activities",
        "pre_sales_tasks": "pre_sales_tasks", "after_sales_tasks": "after_sales_tasks",
    }
    for kind, table in tables.items():
        value = conn.execute(
            f"""SELECT t.archived_at FROM import_bindings b JOIN {table} t
                ON t.id = b.local_entity_id WHERE b.dataset_id = 'test-dataset'
                AND b.entity_type = ? LIMIT 1""", (kind,),
        ).fetchone()[0]
        assert (value is not None) == should_be_archived, (kind, value)


def assert_api_contract(ids):
    actor = {"value": {"id": ids["sales"], "role": "sales"}}
    async def current_user():
        return actor["value"]
    with TemporaryDirectory() as api_data:
        previous = os.environ.get("JPT_DATA_DIR")
        os.environ["JPT_DATA_DIR"] = api_data
        try:
            close_db()
            init_db(Path(api_data) / "database.sqlite")
            leader_id = UserRepository().create("api-leader", "x", "API Leader", "leader")
            app = create_app(); app.dependency_overrides[get_current_user] = current_user
            with TestClient(app) as client:
                denied = client.post(
                    "/api/data/spreadsheet/preflight",
                    files={"file": ("test.xlsx", BytesIO(b"invalid"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                )
                assert denied.status_code == 403
                old = client.post(
                    "/api/data/preflight",
                    files={"file": ("export.json", BytesIO(json.dumps({"version": "v2", "customers": {}, "leads": []}).encode()), "application/json")},
                )
                assert old.status_code == 200, old.text
                actor["value"] = {"id": leader_id, "role": "leader"}
                template_content = (
                    Path(__file__).parent / "frontend" / "templates"
                    / "JPT标准导入模板.xlsx"
                ).read_bytes()
                assert template_content.startswith(b"PK")
                empty_preflight = client.post(
                    "/api/data/spreadsheet/preflight",
                    files={"file": (
                        "JPT标准导入模板.xlsx", BytesIO(template_content),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )},
                )
                assert empty_preflight.status_code == 200, empty_preflight.text
                assert empty_preflight.json()["can_commit"] is False
                assert not any(
                    route.path == "/api/data/import-template" for route in app.routes
                ), "The Excel template must be distributed separately from the app"
                assert any(route.path == "/api/data/spreadsheet/import" for route in app.routes)
        finally:
            if previous is None:
                os.environ.pop("JPT_DATA_DIR", None)
            else:
                os.environ["JPT_DATA_DIR"] = previous
            close_db()


def main():
    with TemporaryDirectory() as tmp:
        ids, actor = setup(Path(tmp) / "import.sqlite")
        conn = get_db()
        assert_preflight_boundaries(conn, ids, actor)
        assert_rollback_and_blocking(conn, ids, actor)
        assert_commit_idempotency(conn, ids, actor)
        assert_api_contract(ids)
        close_db()
    print("PASS: spreadsheet preflight/import is Leader-only, atomic, and idempotent")


if __name__ == "__main__":
    main()
