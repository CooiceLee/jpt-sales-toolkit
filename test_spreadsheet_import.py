#!/usr/bin/env python3
"""Controlled XLSX import permissions, rollback, and idempotency regression."""

from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import hashlib
import inspect
import json
import os
import sqlite3
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import UserRepository, close_db, get_db, init_db
from backend.repositories.base import request_db_connection
from backend.routers.authorization_dependencies import get_authorization_provider
from backend.routers.deps import get_auth_service, get_current_user
from backend.services.spreadsheet_import import SpreadsheetImportService
from backend.services.spreadsheet_import.errors import ImportBlockedError, SpreadsheetImportError
from backend.services.spreadsheet_import.member_mapping_keys import member_mapping_key
from backend.services.spreadsheet_import.resolutions import parse_resolutions


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


def purpose_split_canonical(content: bytes) -> dict:
    result = canonical_for(content)
    result["dataset_id"] = "purpose-split-dataset"
    result["entities"]["leads"][0]["owner_username_token"] = "shared-person"
    for kind in ("pre_sales_tasks", "after_sales_tasks"):
        result["entities"][kind][0]["assignee_username_token"] = "shared-person"
    result["member_name_tokens"] = [
        item for item in result["member_name_tokens"]
        if item["username_token"] != "old-tech"
    ] + [{"username_token": "shared-person", "raw_names": ["Milena"]}]
    return result


def purpose_split_resolutions(ids: dict) -> dict:
    return {
        "member_mappings": {
            "old-sales": ids["sales"], "old-collab": ids["collab"],
            "shared-person": ids["sales"],
            member_mapping_key("shared-person", "task_assignee"): ids["tech"],
        },
        "customer_mappings": {"CUS-1": "__CREATE__"}, "excluded_records": [],
    }


def grouped_pre_sales_canonical(content: bytes) -> dict:
    result = canonical_for(content)
    result["dataset_id"] = "grouped-pre-sales-dataset"
    result["issues"] = []
    result["entities"]["assignments"] = []
    result["entities"]["activities"] = []
    result["entities"]["after_sales_tasks"] = []
    common = {
        "source_ref": result["entities"]["leads"][0]["source_ref"],
        "task_group_key": "PTG-SAME-SOURCE-ROW", "lead_key": "LEAD-1",
        "status": "In Progress", "request_description": "Alloy weld depth test",
        "request_date": "2026-05-01", "request_date_raw": "2026年5月1日",
        "due_date": "2026-06-01", "due_date_raw": "2026年6月1日前",
        "customer_decision_maker": "Dr. Chen", "quantity_text": "3 samples",
        "competitor": "Competitor A", "key_points": "Measure penetration depth",
        "concerns": "Protective gas stability", "progress_text": "Sample request submitted",
        "next_action": "Engineer to accept samples",
    }
    result["entities"]["pre_sales_tasks"] = [
        {**common, "external_key": "PRE-NEIL",
         "assignee_username_token": "legacy-neil", "assignee_name_raw": "Neil"},
        {**common, "external_key": "PRE-AYDEN",
         "assignee_username_token": "legacy-ayden", "assignee_name_raw": "Ayden"},
    ]
    result["member_name_tokens"] = [
        {"username_token": "old-sales", "raw_names": ["Legacy Sales"]},
        {"username_token": "legacy-neil", "raw_names": ["Neil"]},
        {"username_token": "legacy-ayden", "raw_names": ["Ayden"]},
    ]
    return result


def grouped_pre_sales_resolutions(ids: dict, second_tech_id: str) -> dict:
    return {
        "member_mappings": {
            "old-sales": ids["sales"], "legacy-neil": ids["tech"],
            "legacy-ayden": second_tech_id,
        },
        "customer_mappings": {"CUS-1": "__CREATE__"}, "excluded_records": [],
    }


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


def assert_purpose_specific_mappings(conn, ids, actor):
    content = b"xlsx-purpose-split"
    selected = purpose_split_resolutions(ids)
    service = SpreadsheetImportService(conn, lambda value, _name: purpose_split_canonical(value))
    report = service.preflight(content, "purpose.xlsx", selected, actor)
    shared = [item for item in report["member_mappings"]
              if item["source_name"] == "shared-person"]
    assert report["can_commit"], report["issues"]
    assert {item["mapping_key"] for item in shared} == {
        member_mapping_key("shared-person", "owner"),
        member_mapping_key("shared-person", "task_assignee"),
    }
    assert {item["purpose"]: item["user_id"] for item in shared} == {
        "owner": ids["sales"], "task_assignee": ids["tech"],
    }
    parsed = parse_resolutions({"member_mappings": [{
        "mapping_key": member_mapping_key("shared-person", "task_assignee"),
        "user_id": ids["tech"],
    }]})
    assert parsed["member_mappings"] == {
        member_mapping_key("shared-person", "task_assignee"): ids["tech"]
    }
    service.commit(content, "purpose.xlsx", selected, report["source_hash"], actor)
    assert conn.execute("SELECT owner_id FROM leads").fetchone()[0] == ids["sales"]
    assert conn.execute("SELECT assignee_id FROM pre_sales_tasks").fetchone()[0] == ids["tech"]
    assert conn.execute("SELECT assignee_id FROM after_sales_tasks").fetchone()[0] == ids["tech"]
    assert conn.execute(
        "SELECT COUNT(*) FROM member_import_aliases WHERE lower(source_name) IN ('shared-person', 'milena')"
    ).fetchone()[0] == 0


def assert_pre_sales_group_dedup(path: Path):
    ids, actor = setup(path)
    conn = get_db()
    content = b"xlsx-grouped-pre-sales"
    service = SpreadsheetImportService(
        conn, lambda value, _name: grouped_pre_sales_canonical(value)
    )
    selected = grouped_pre_sales_resolutions(ids, ids["tech"])
    report = service.preflight(content, "grouped.xlsx", selected, actor)
    assert report["can_commit"], report["issues"]
    assert report["summary"]["entities"]["pre_sales_tasks"] == 1
    assert report["predicted"]["pre_sales_tasks"] == {"create": 1, "update": 0}
    first = service.commit(content, "grouped.xlsx", selected, report["source_hash"], actor)
    assert first["counts"]["pre_sales_tasks"] == {"created": 1, "updated": 0}
    task = conn.execute(
        """SELECT id, request_json, result_json FROM pre_sales_tasks
           WHERE archived_at IS NULL"""
    ).fetchone()
    request, result = json.loads(task["request_json"]), json.loads(task["result_json"])
    assert request == {
        "competitor": "Competitor A", "concerns": "Protective gas stability",
        "customer_decision_maker": "Dr. Chen", "due_date_raw": "2026年6月1日前",
        "key_points": "Measure penetration depth", "quantity_text": "3 samples",
        "request_date": "2026-05-01", "request_date_raw": "2026年5月1日",
        "request_description": "Alloy weld depth test",
    }
    assert result == {
        "next_action": "Engineer to accept samples",
        "progress_text": "Sample request submitted",
    }
    bindings = conn.execute(
        """SELECT external_key, local_entity_id FROM import_bindings
           WHERE dataset_id = ? AND entity_type = 'pre_sales_tasks'
           ORDER BY external_key""",
        ("grouped-pre-sales-dataset",),
    ).fetchall()
    assert {row["external_key"] for row in bindings} == {"PRE-AYDEN", "PRE-NEIL"}
    assert {row["local_entity_id"] for row in bindings} == {task["id"]}

    repeated = service.commit(content, "grouped.xlsx", selected, report["source_hash"], actor)
    assert repeated["counts"]["pre_sales_tasks"] == {"created": 0, "updated": 1}
    assert conn.execute(
        "SELECT COUNT(*) FROM pre_sales_tasks WHERE archived_at IS NULL"
    ).fetchone()[0] == 1

    duplicate_id = "legacy-duplicate-pre-sales-task"
    conn.execute(
        """INSERT INTO pre_sales_tasks (
               id, lead_id, assignee_id, status, request_json, result_json, due_date,
               archived_at, created_at, created_by, updated_at, updated_by, row_version
           )
           SELECT ?, lead_id, assignee_id, status, request_json, result_json, due_date,
                  NULL, created_at, created_by, updated_at, updated_by, row_version
           FROM pre_sales_tasks WHERE id = ?""",
        (duplicate_id, task["id"]),
    )
    conn.execute(
        """UPDATE import_bindings SET local_entity_id = ?
           WHERE dataset_id = ? AND entity_type = 'pre_sales_tasks'
             AND external_key = 'PRE-AYDEN'""",
        (duplicate_id, "grouped-pre-sales-dataset"),
    )
    equivalent_request = json.loads(task["request_json"])
    conn.execute(
        "UPDATE pre_sales_tasks SET request_json = ? WHERE id = ?",
        (json.dumps(dict(reversed(list(equivalent_request.items())))), duplicate_id),
    )
    conn.commit()
    service.commit(content, "grouped.xlsx", selected, report["source_hash"], actor)
    assert conn.execute(
        "SELECT COUNT(*) FROM pre_sales_tasks WHERE archived_at IS NULL"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT archived_at FROM pre_sales_tasks WHERE id = ?", (duplicate_id,)
    ).fetchone()[0]
    rebound = conn.execute(
        """SELECT DISTINCT local_entity_id FROM import_bindings
           WHERE dataset_id = ? AND entity_type = 'pre_sales_tasks'
             AND external_key IN ('PRE-NEIL', 'PRE-AYDEN')""",
        ("grouped-pre-sales-dataset",),
    ).fetchall()
    assert [row[0] for row in rebound] == [task["id"]]
    assert conn.execute(
        """SELECT COUNT(*) FROM audit_logs
           WHERE entity_id = ? AND event_type = 'deduplicate_import'""",
        (duplicate_id,),
    ).fetchone()[0] == 1
    close_db()

    ids, actor = setup(path.with_name("different-tech.sqlite"))
    conn = get_db()
    second_tech = UserRepository().create("tech-2", "x", "Tech Two", "tech")
    selected = grouped_pre_sales_resolutions(ids, second_tech)
    report = service = SpreadsheetImportService(
        conn, lambda value, _name: grouped_pre_sales_canonical(value)
    ).preflight(content, "grouped.xlsx", selected, actor)
    assert report["can_commit"] and report["summary"]["entities"]["pre_sales_tasks"] == 2
    committed = SpreadsheetImportService(
        conn, lambda value, _name: grouped_pre_sales_canonical(value)
    ).commit(content, "grouped.xlsx", selected, report["source_hash"], actor)
    assert committed["counts"]["pre_sales_tasks"] == {"created": 2, "updated": 0}
    assignees = conn.execute(
        """SELECT DISTINCT assignee_id FROM pre_sales_tasks
           WHERE archived_at IS NULL"""
    ).fetchall()
    assert {row[0] for row in assignees} == {ids["tech"], second_tech}
    close_db()


def assert_pre_sales_group_conflict_guard(path: Path):
    ids, actor = setup(path)
    conn = get_db()
    content = b"xlsx-grouped-pre-sales-conflict"
    selected = grouped_pre_sales_resolutions(ids, ids["tech"])
    service = SpreadsheetImportService(
        conn, lambda value, _name: grouped_pre_sales_canonical(value)
    )
    report = service.preflight(content, "grouped.xlsx", selected, actor)
    service.commit(content, "grouped.xlsx", selected, report["source_hash"], actor)
    task = conn.execute(
        "SELECT * FROM pre_sales_tasks WHERE archived_at IS NULL"
    ).fetchone()
    duplicate_id = "manual-duplicate-pre-sales-task"
    conn.execute(
        """INSERT INTO pre_sales_tasks (
               id, lead_id, assignee_id, client_request_id, status,
               request_json, result_json, due_date, archived_at,
               created_at, created_by, updated_at, updated_by, row_version
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)""",
        (
            duplicate_id, task["lead_id"], task["assignee_id"],
            task["client_request_id"], task["status"], task["request_json"],
            json.dumps({"manual_note": "CRITICAL MANUAL EDIT ONLY ON DUPLICATE"}),
            task["due_date"], task["created_at"], task["created_by"],
            task["updated_at"], task["updated_by"], task["row_version"],
        ),
    )
    conn.execute(
        """UPDATE import_bindings SET local_entity_id = ?
           WHERE dataset_id = ? AND entity_type = 'pre_sales_tasks'
             AND external_key = 'PRE-AYDEN'""",
        (duplicate_id, "grouped-pre-sales-dataset"),
    )
    conn.commit()
    baseline_versions = {
        row["id"]: row["row_version"]
        for row in conn.execute(
            "SELECT id, row_version FROM pre_sales_tasks ORDER BY id"
        ).fetchall()
    }
    baseline_batches = conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]

    blocked = service.preflight(content, "grouped.xlsx", selected, actor)
    conflict = next(
        item for item in blocked["issues"]
        if item["code"] == "pre_sales_duplicate_conflict"
    )
    assert not blocked["can_commit"] and conflict["field"] == "result_json"
    try:
        service.commit(content, "grouped.xlsx", selected, blocked["source_hash"], actor)
        raise AssertionError("Conflicting duplicate task import should be blocked")
    except ImportBlockedError:
        pass
    assert conn.execute(
        "SELECT COUNT(*) FROM pre_sales_tasks WHERE archived_at IS NULL"
    ).fetchone()[0] == 2
    assert {
        row["id"]: row["row_version"]
        for row in conn.execute(
            "SELECT id, row_version FROM pre_sales_tasks ORDER BY id"
        ).fetchall()
    } == baseline_versions
    assert conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == baseline_batches

    conn.execute(
        "UPDATE pre_sales_tasks SET result_json = ? WHERE id = ?",
        (task["result_json"], duplicate_id),
    )
    conn.execute(
        """INSERT INTO lead_activities (
               id, lead_id, actor_id, action_type, visibility,
               is_formal_follow_up, summary, payload_json, created_at
           ) VALUES (?, ?, ?, 'task_update', 'all', 0, ?, ?, ?)""",
        (
            "manual-duplicate-task-update", task["lead_id"], actor["id"],
            "Manual duplicate edit history",
            json.dumps({"task_type": "pre_sales", "task_id": duplicate_id}),
            task["updated_at"],
        ),
    )
    conn.commit()
    history_blocked = service.preflight(content, "grouped.xlsx", selected, actor)
    history_conflict = next(
        item for item in history_blocked["issues"]
        if item["code"] == "pre_sales_duplicate_conflict"
    )
    assert "task_update_history" in history_conflict["field"]
    assert not history_blocked["can_commit"]
    assert conn.execute(
        "SELECT archived_at FROM lead_activities WHERE id = 'manual-duplicate-task-update'"
    ).fetchone()[0] is None
    close_db()


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
            connection_closures = []

            @contextmanager
            def tracked_request_connection():
                conn = None
                try:
                    with request_db_connection() as conn:
                        yield conn
                finally:
                    try:
                        conn.execute("SELECT 1")
                    except sqlite3.ProgrammingError as exc:
                        connection_closures.append("closed" in str(exc).lower())
                    else:
                        connection_closures.append(False)

            with TestClient(app) as client, patch(
                "backend.routers.spreadsheet_import.request_db_connection",
                tracked_request_connection,
            ):
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
                blocked_import = client.post(
                    "/api/data/spreadsheet/import",
                    files={"file": (
                        "JPT标准导入模板.xlsx", BytesIO(template_content),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )},
                    data={
                        "resolutions": "{}",
                        "expected_source_hash": empty_preflight.json()["source_hash"],
                    },
                )
                assert blocked_import.status_code == 422, blocked_import.text
                assert connection_closures == [True, True], (
                    "Spreadsheet endpoint leaked a request connection",
                    connection_closures,
                )
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


def assert_dependency_thread_contract():
    assert inspect.iscoroutinefunction(get_auth_service)
    assert inspect.iscoroutinefunction(get_authorization_provider)


def main():
    with TemporaryDirectory() as tmp:
        ids, actor = setup(Path(tmp) / "import.sqlite")
        conn = get_db()
        assert_preflight_boundaries(conn, ids, actor)
        assert_rollback_and_blocking(conn, ids, actor)
        assert_commit_idempotency(conn, ids, actor)
        assert_api_contract(ids)
        assert_dependency_thread_contract()
        close_db()
        ids, actor = setup(Path(tmp) / "purpose-specific.sqlite")
        assert_purpose_specific_mappings(get_db(), ids, actor)
        close_db()
        assert_pre_sales_group_dedup(Path(tmp) / "grouped-pre-sales.sqlite")
        assert_pre_sales_group_conflict_guard(Path(tmp) / "grouped-pre-sales-conflict.sqlite")
    print("PASS: spreadsheet preflight/import is Leader-only, atomic, and idempotent")


if __name__ == "__main__":
    main()
