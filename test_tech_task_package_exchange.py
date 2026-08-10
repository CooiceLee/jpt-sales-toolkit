"""Offline Tech task-package round-trip, authorization and atomicity contract.

This regression intentionally uses two independent data directories.  It proves
that a Leader can hand a narrow task package to a Tech installation and merge
only the permitted task results back into the original Leader installation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import UserCredentialRepository, UserRepository, close_db
from backend.repositories.base import get_db


PASSWORD = "TechPackage2026!"
LEGACY_HASH = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()
ACCOUNT_SPECS = {
    "leader": ("leader-tech-package", "Leader Package", "leader"),
    "leader_b": ("leader-b-tech-package", "Leader B Package", "leader"),
    "sales": ("sales-tech-package", "Sales Package", "sales"),
    "tech_a": ("tech-a-package", "Tech A Package", "tech"),
    "tech_b": ("tech-b-package", "Tech B Package", "tech"),
}
FORBIDDEN_PACKAGE_KEYS = {
    "activities",
    "attachments",
    "contacts",
    "currency",
    "deal_amount",
    "estimated_value",
    "lost_reason_code",
    "lost_reason_text",
    "original_email",
    "po_date",
    "po_number",
    "primary_contact_id",
    "customer_decision_maker",
    "quotation_date",
    "quotation_id",
}
SENSITIVE_SENTINELS = {
    "private-tech-package@example.com",
    "PRIVATE-QUOTE-2026",
    "PRIVATE-PO-2026",
    "PRIVATE-COMMERCIAL-NOTE",
    "PRIVATE-DECISION-MAKER",
}


def expect(response, status_code: int, label: str):
    assert response.status_code == status_code, (
        f"{label}: expected HTTP {status_code}, got {response.status_code}; "
        f"body={response.text[:800]}"
    )
    return response


@contextmanager
def installation(data_dir: Path):
    """Open one isolated installation without sharing a SQLite connection."""
    close_db()
    with patch.dict("os.environ", {"JPT_DATA_DIR": str(data_dir)}):
        try:
            with TestClient(create_app()) as client:
                yield client
        finally:
            close_db()


def seed_accounts() -> dict[str, str]:
    """Seed stable cross-installation identities and local login credentials."""
    users = UserRepository()
    credentials = UserCredentialRepository()
    ids = {}
    for key, (username, display_name, role) in ACCOUNT_SPECS.items():
        user_id = f"test-tech-package-{key.replace('_', '-')}"
        users.upsert_directory_member({
            "id": user_id,
            "username": username,
            "display_name": display_name,
            "role": role,
            "region": "EU",
            "is_active": True,
        }, LEGACY_HASH)
        if not credentials.get_by_user_id(user_id):
            credentials.create({
                "user_id": user_id,
                "password_hash": LEGACY_HASH,
                "password_scheme": "legacy_sha256",
                "must_change_password": False,
            })
        ids[key] = user_id
    return ids


def login(client: TestClient, key: str) -> dict[str, str]:
    username = ACCOUNT_SPECS[key][0]
    response = expect(client.post("/api/auth/login", json={
        "username": username,
        "password": PASSWORD,
    }), 200, f"login {key}")
    return {"Authorization": f"Bearer {response.json()['token']}"}


def login_all(client: TestClient) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    ids = seed_accounts()
    return ids, {key: login(client, key) for key in ACCOUNT_SPECS}


def _create_lead(
    client: TestClient,
    headers: dict[str, str],
    owner_id: str,
    label: str,
) -> dict:
    customer = expect(client.post("/api/customers", headers=headers, json={
        "display_name": f"{label} Laser GmbH",
        "country": "Germany",
        "city": "Munich",
        "address": f"{label} technical site",
        "website": f"https://{label.lower()}.example.com",
    }), 200, f"create {label} customer").json()
    expect(client.post(
        f"/api/customers/{customer['id']}/contacts",
        headers=headers,
        json={
            "name": f"{label} Private Contact",
            "email": "private-tech-package@example.com",
            "phone": "+49-89-555-0199",
            "is_primary": True,
        },
    ), 200, f"create {label} private contact")
    lead = expect(client.post("/api/leads", headers=headers, json={
        "customer_id": customer["id"],
        "owner_id": owner_id,
        "title": f"{label} technical project",
        "sales_stage": "Following",
        "product_category": "Laser source",
        "application": "Precision welding",
        "original_email": "PRIVATE-COMMERCIAL-NOTE",
    }), 200, f"create {label} lead").json()
    return expect(client.patch(
        f"/api/leads/{lead['id']}",
        headers=headers,
        json={
            "estimated_value": 987654,
            "deal_amount": 876543,
            "currency": "USD",
            "quotation_id": "PRIVATE-QUOTE-2026",
            "po_number": "PRIVATE-PO-2026",
            "lost_reason_text": "PRIVATE-COMMERCIAL-NOTE",
            "row_version": lead["row_version"],
        },
    ), 200, f"seed {label} private commercial fields").json()


def seed_tasks(client: TestClient, ids: dict, headers: dict, *, extra_pre: bool = False) -> dict:
    """Create one sample task, one service task and optionally a second sample task."""
    leader = headers["leader"]
    pre_lead = _create_lead(client, leader, ids["sales"], "Sampling")
    after_lead = _create_lead(client, leader, ids["sales"], "Service")
    pre = expect(client.post(
        f"/api/leads/{pre_lead['id']}/pre-sales-tasks",
        headers=leader,
        json={
            "assignee_id": ids["tech_a"],
            "request_json": json.dumps({
                "sample_parameters": "10W blue pulse",
                "customer_decision_maker": "PRIVATE-DECISION-MAKER",
            }),
            "due_date": "2026-08-20",
        },
    ), 200, "create sample task").json()
    after = expect(client.post(
        f"/api/leads/{after_lead['id']}/after-sales-tasks",
        headers=leader,
        json={
            "assignee_id": ids["tech_a"],
            "issue_type": "Technical",
            "issue_description": "Intermittent pulse stability at production speed",
            "due_date": "2026-08-21",
        },
    ), 200, "create service task").json()
    result = {"pre": pre, "after": after, "pre_lead": pre_lead, "after_lead": after_lead}
    if extra_pre:
        lead = _create_lead(client, leader, ids["sales"], "StaleSampling")
        result["stale_pre"] = expect(client.post(
            f"/api/leads/{lead['id']}/pre-sales-tasks",
            headers=leader,
            json={
                "assignee_id": ids["tech_a"],
                "request_json": json.dumps({"sample_parameters": "20W green pulse"}),
                "due_date": "2026-08-22",
            },
        ), 200, "create stale-version sample task").json()
    return result


def _upload(client: TestClient, path: str, package: dict, headers: dict, filename: str):
    body = json.dumps(package, ensure_ascii=False).encode("utf-8")
    return client.post(path, headers=headers, files={
        "file": (filename, body, "application/json"),
    })


def refresh_digest(package: dict) -> dict:
    """Recalculate the public package checksum after an intentional test mutation."""
    unsigned = {key: value for key, value in package.items() if key != "payload_sha256"}
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    package["payload_sha256"] = hashlib.sha256(encoded).hexdigest()
    return package


def export_assignments(client: TestClient, headers: dict, recipient_id: str) -> dict:
    response = expect(client.post(
        "/api/data/tech-tasks/assignments/export",
        headers=headers,
        json={"recipient_user_id": recipient_id},
    ), 200, "export Tech assignment package")
    package = response.json()
    assert package["package_type"] == "tech_task_assignment"
    assert package["package_version"] == "1.0"
    assert package["direction"] == "leader_to_tech"
    assert package["recipient_user_id"] == recipient_id
    assert package.get("package_id") and package.get("organization_id")
    assert isinstance(package.get("tasks"), list)
    for task in package["tasks"]:
        assert {
            "source_task_id",
            "source_lead_id",
            "base_row_version",
            "task_type",
        } <= set(task), f"incomplete assignment item: {task}"
    return package


def export_results(client: TestClient, headers: dict) -> dict:
    response = expect(client.post(
        "/api/data/tech-tasks/results/export", headers=headers, json={},
    ), 200, "export Tech result package")
    package = response.json()
    assert package["package_type"] == "tech_task_results"
    assert package["package_version"] == "1.0"
    assert package["direction"] == "tech_to_leader"
    assert package.get("package_id") and isinstance(package.get("tasks"), list)
    return package


def _iter_named_values(value, names: set[str]):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names:
                yield item
            yield from _iter_named_values(item, names)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_named_values(item, names)


def assert_clean_preflight(response, label: str) -> dict:
    payload = expect(response, 200, label).json()
    assert payload.get("can_import", True) is not False, payload
    blocker_names = {
        "blocker_count", "blockers", "conflict_count", "conflicts",
        "error_count", "errors",
    }
    for value in _iter_named_values(payload, blocker_names):
        if isinstance(value, (list, dict, str)):
            assert not value, f"{label} unexpectedly blocked: {payload}"
        elif isinstance(value, (int, float)):
            assert value == 0, f"{label} unexpectedly blocked: {payload}"
    return payload


def assert_blocked(response, label: str) -> None:
    if response.status_code >= 400:
        return
    payload = response.json()
    if payload.get("can_import") is False:
        return
    blocker_names = {
        "blocker_count", "blockers", "conflict_count", "conflicts",
        "error_count", "errors", "rejected_count", "rejected_tasks",
    }
    values = list(_iter_named_values(payload, blocker_names))
    assert any(
        bool(value) if isinstance(value, (list, dict, str)) else value > 0
        for value in values
    ), f"{label} returned a misleading clean success: {payload}"


def _recursive_keys(value) -> set[str]:
    if isinstance(value, dict):
        result = set(value)
        for item in value.values():
            result.update(_recursive_keys(item))
        return result
    if isinstance(value, list):
        result = set()
        for item in value:
            result.update(_recursive_keys(item))
        return result
    return set()


def assert_assignment_minimization(package: dict) -> None:
    leaked_keys = FORBIDDEN_PACKAGE_KEYS & _recursive_keys(package)
    assert not leaked_keys, f"assignment package leaked sensitive keys: {sorted(leaked_keys)}"
    serialized = json.dumps(package, ensure_ascii=False)
    leaked_values = {value for value in SENSITIVE_SENTINELS if value in serialized}
    assert not leaked_values, f"assignment package leaked sensitive values: {sorted(leaked_values)}"


def list_tasks(client: TestClient, headers: dict) -> tuple[list[dict], list[dict]]:
    pre = expect(client.get("/api/pre-sales-tasks", headers=headers), 200, "list sample tasks").json()
    after = expect(client.get("/api/after-sales-tasks", headers=headers), 200, "list service tasks").json()
    return pre, after


def source_task_id(task: dict) -> str:
    return task.get("sync_source_task_id") or task.get("source_task_id") or task["id"]


def update_imported_results(client: TestClient, headers: dict) -> dict[str, dict]:
    pre_tasks, after_tasks = list_tasks(client, headers)
    updated = {}
    for index, task in enumerate(pre_tasks, start=1):
        payload = {
            "status": "Completed",
            "result_json": json.dumps({
                "sample_result": "Passed",
                "supplemental_notes": f"Stable output #{index}",
            }),
            "row_version": task["row_version"],
        }
        updated[source_task_id(task)] = expect(client.patch(
            f"/api/pre-sales-tasks/{task['id']}", headers=headers, json=payload,
        ), 200, "Tech updates imported sample result").json()
    for task in after_tasks:
        payload = {
            "status": "Resolved",
            "solution": "Recalibrated timing and verified cooling flow",
            "customer_satisfaction": "Satisfied",
            "lessons_learned": "Record inlet temperature before calibration",
            "remarks": "Remote verification completed",
            "row_version": task["row_version"],
        }
        updated[source_task_id(task)] = expect(client.patch(
            f"/api/after-sales-tasks/{task['id']}", headers=headers, json=payload,
        ), 200, "Tech updates imported service result").json()
    return updated


def update_first_sample_result(
    client: TestClient, headers: dict, result_text: str
) -> dict:
    pre_tasks, _ = list_tasks(client, headers)
    task = pre_tasks[0]
    return expect(client.patch(
        f"/api/pre-sales-tasks/{task['id']}", headers=headers,
        json={
            "status": "Completed",
            "result_json": json.dumps({"sample_result": result_text}),
            "row_version": task["row_version"],
        },
    ), 200, f"Tech updates sample result to {result_text}").json()


def task_by_id(tasks: list[dict], task_id: str) -> dict:
    return next(item for item in tasks if item["id"] == task_id)


def exchange_binding(source_task_id: str) -> dict:
    row = get_db().execute(
        "SELECT * FROM tech_task_exchange_bindings WHERE source_task_id = ?",
        (source_task_id,),
    ).fetchone()
    assert row, f"missing exchange binding for {source_task_id}"
    return dict(row)


def bound_local_task(binding: dict) -> dict:
    table = "pre_sales_tasks" if binding["task_type"] == "pre_sales" else "after_sales_tasks"
    row = get_db().execute(
        f"SELECT * FROM {table} WHERE id = ?", (binding["local_task_id"],)
    ).fetchone()
    assert row, f"missing local task {binding['local_task_id']}"
    return dict(row)


def assert_roundtrip(root: Path) -> None:
    leader_dir, tech_dir = root / "leader", root / "tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        get_db().execute(
            "UPDATE pre_sales_tasks SET result_json = ? WHERE id = ?",
            (json.dumps({
                "sample_result": "Existing result",
                "legacy_unknown": "KEEP-ME",
            }), source["pre"]["id"]),
        )
        get_db().commit()
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])
        assert len(assignment["tasks"]) == 2
        assert_assignment_minimization(assignment)

    with installation(tech_dir) as client:
        target_ids, headers = login_all(client)
        assert target_ids == ids
        assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", assignment,
            headers["tech_a"], "leader-to-tech.jpttask",
        ), "preflight assignment package")
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "leader-to-tech.jpttask",
        ), 200, "import assignment package")
        first_pre, first_after = list_tasks(client, headers["tech_a"])
        assert len(first_pre) == 1 and len(first_after) == 1

        # Replaying the exact package must not create duplicate replicas.
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "leader-to-tech.jpttask",
        ), 200, "replay assignment package")
        repeated_pre, repeated_after = list_tasks(client, headers["tech_a"])
        assert [item["id"] for item in repeated_pre] == [item["id"] for item in first_pre]
        assert [item["id"] for item in repeated_after] == [item["id"] for item in first_after]

        update_imported_results(client, headers["tech_a"])
        results = export_results(client, headers["tech_a"])
        assert len(results["tasks"]) == 2

    with installation(leader_dir) as client:
        _, headers = login_all(client)
        forbidden_results = deepcopy(results)
        forbidden_results["tasks"][0]["changes"]["assignee_id"] = ids["tech_b"]
        refresh_digest(forbidden_results)
        assert_blocked(_upload(
            client, "/api/data/tech-tasks/results/preflight", forbidden_results,
            headers["leader"], "forbidden-result-fields.jptresult",
        ), "Tech result cannot reassign a source task")
        assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/results/preflight", results,
            headers["leader"], "tech-to-leader.jptresult",
        ), "preflight result package")
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", results,
            headers["leader"], "tech-to-leader.jptresult",
        ), 200, "import result package")
        pre_tasks, after_tasks = list_tasks(client, headers["leader"])
        stored_pre = task_by_id(pre_tasks, source["pre"]["id"])
        stored_after = task_by_id(after_tasks, source["after"]["id"])
        assert stored_pre["status"] == "Completed"
        assert json.loads(stored_pre["result_json"])["sample_result"] == "Passed"
        assert json.loads(stored_pre["result_json"])["legacy_unknown"] == "KEEP-ME"
        assert json.loads(stored_pre["request_json"])["sample_parameters"] == "10W blue pulse"
        assert stored_pre["assignee_id"] == ids["tech_a"]
        assert stored_pre["due_date"] == "2026-08-20"
        assert stored_after["status"] == "Resolved"
        assert stored_after["solution"] == "Recalibrated timing and verified cooling flow"
        assert stored_after["customer_satisfaction"] == "Satisfied"
        assert stored_after["issue_description"] == (
            "Intermittent pulse stability at production speed"
        )
        assert stored_after["assignee_id"] == ids["tech_a"]
        assert stored_after["due_date"] == "2026-08-21"
        private_lead = expect(client.get(
            f"/api/leads/{source['pre_lead']['id']}", headers=headers["leader"],
        ), 200, "read source lead after Tech result import").json()
        assert private_lead["estimated_value"] == 987654
        assert private_lead["quotation_id"] == "PRIVATE-QUOTE-2026"
        assert private_lead["po_number"] == "PRIVATE-PO-2026"
        versions = (stored_pre["row_version"], stored_after["row_version"])

        # A receipt makes an identical result package an idempotent no-op.
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", results,
            headers["leader"], "tech-to-leader.jptresult",
        ), 200, "replay result package")
        pre_tasks, after_tasks = list_tasks(client, headers["leader"])
        assert (
            task_by_id(pre_tasks, source["pre"]["id"])["row_version"],
            task_by_id(after_tasks, source["after"]["id"])["row_version"],
        ) == versions


def assert_security_and_atomicity(root: Path) -> None:
    leader_dir, tech_dir = root / "leader", root / "tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers, extra_pre=True)
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])
        assert len(assignment["tasks"]) == 3
        assert_assignment_minimization(assignment)

        expect(client.post(
            "/api/data/tech-tasks/assignments/export",
            headers=headers["tech_a"], json={"recipient_user_id": ids["tech_a"]},
        ), 403, "Tech cannot export assignments")
        assert client.post(
            "/api/data/tech-tasks/assignments/export",
            headers=headers["leader"], json={"recipient_user_id": ids["sales"]},
        ).status_code in {400, 403, 422}
        expect(client.post(
            "/api/data/tech-tasks/results/export", headers=headers["leader"], json={},
        ), 403, "Leader cannot impersonate Tech result export")
        assert_blocked(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", assignment,
            headers["tech_a"], "same-installation.jpttask",
        ), "source installation cannot preflight its own assignment package")
        assert_blocked(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "same-installation.jpttask",
        ), "source installation cannot import its own assignment package")

    with installation(tech_dir) as client:
        _, headers = login_all(client)
        assert_blocked(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", assignment,
            headers["tech_b"], "wrong-recipient.jpttask",
        ), "wrong Tech recipient preflight")
        assert_blocked(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_b"], "wrong-recipient.jpttask",
        ), "wrong Tech recipient import")
        assert list_tasks(client, headers["tech_b"]) == ([], [])

        expect(client.post(
            "/api/data/export", headers=headers["tech_a"], json={"lead_ids": None},
        ), 403, "Tech generic export remains forbidden")
        expect(client.post(
            "/api/data/import", headers=headers["tech_a"],
            files={"file": ("generic.json", b"{}", "application/json")},
        ), 403, "Tech generic import remains forbidden")

        tampered = deepcopy(assignment)
        tampered["tasks"][0]["estimated_value"] = 99999999
        refresh_digest(tampered)
        assert_blocked(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", tampered,
            headers["tech_a"], "tampered-sensitive.jpttask",
        ), "sensitive-field tampering preflight")
        assert list_tasks(client, headers["tech_a"]) == ([], [])

        malformed_cases = []
        malformed_identity = deepcopy(assignment)
        malformed_identity["tasks"][0]["source_task_id"] = {"not": "a string"}
        malformed_cases.append(("malformed-identity", malformed_identity))
        malformed_context = deepcopy(assignment)
        malformed_context["tasks"][0]["customer_context"]["display_name"] = ["nested"]
        malformed_cases.append(("malformed-context", malformed_context))
        malformed_timestamp = deepcopy(assignment)
        malformed_timestamp["created_at"] = ["not", "a", "timestamp"]
        malformed_cases.append(("malformed-timestamp", malformed_timestamp))
        for label, malformed in malformed_cases:
            refresh_digest(malformed)
            assert_blocked(_upload(
                client, "/api/data/tech-tasks/assignments/preflight", malformed,
                headers["tech_a"], f"{label}.jpttask",
            ), f"{label} preflight")
            assert_blocked(_upload(
                client, "/api/data/tech-tasks/assignments/import", malformed,
                headers["tech_a"], f"{label}.jpttask",
            ), f"{label} import")
        assert list_tasks(client, headers["tech_a"]) == ([], [])

        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "leader-to-tech.jpttask",
        ), 200, "import assignment for conflict test")
        update_imported_results(client, headers["tech_a"])
        results = export_results(client, headers["tech_a"])
        assert len(results["tasks"]) == 3

    with installation(leader_dir) as client:
        _, headers = login_all(client)
        pre_tasks, after_tasks = list_tasks(client, headers["leader"])
        valid_before = task_by_id(pre_tasks, source["pre"]["id"])
        stale = task_by_id(pre_tasks, source["stale_pre"]["id"])
        reassigned = task_by_id(after_tasks, source["after"]["id"])

        # One stale task and one reassigned task make a mixed result package
        # invalid.  The still-valid first task must not be partially applied.
        due_only = expect(client.patch(
            f"/api/pre-sales-tasks/{stale['id']}", headers=headers["leader"], json={
                "due_date": "2026-09-01", "row_version": stale["row_version"],
            },
        ), 200, "advance source task row_version without overlapping Tech fields").json()
        assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/results/preflight", results,
            headers["leader"], "stale-version.jptresult",
        ), "non-overlapping Leader due-date and Tech result changes")
        expect(client.patch(
            f"/api/pre-sales-tasks/{stale['id']}", headers=headers["leader"], json={
                "status": "In Progress",
                "result_json": json.dumps({"sample_result": "Leader rejected"}),
                "row_version": due_only["row_version"],
            },
        ), 200, "create an overlapping Leader result conflict")
        assert_blocked(_upload(
            client, "/api/data/tech-tasks/results/preflight", results,
            headers["leader"], "overlapping-result-conflict.jptresult",
        ), "overlapping Leader and Tech result changes")
        expect(client.patch(
            f"/api/after-sales-tasks/{reassigned['id']}", headers=headers["leader"], json={
                "assignee_id": ids["tech_b"], "row_version": reassigned["row_version"],
            },
        ), 200, "reassign source task before result import")

        assert_blocked(_upload(
            client, "/api/data/tech-tasks/results/preflight", results,
            headers["leader"], "mixed-conflict.jptresult",
        ), "stale and reassigned result preflight")
        assert_blocked(_upload(
            client, "/api/data/tech-tasks/results/import", results,
            headers["leader"], "mixed-conflict.jptresult",
        ), "atomic mixed result import")

        pre_tasks, after_tasks = list_tasks(client, headers["leader"])
        valid_after = task_by_id(pre_tasks, source["pre"]["id"])
        stale_after = task_by_id(pre_tasks, source["stale_pre"]["id"])
        reassigned_after = task_by_id(after_tasks, source["after"]["id"])
        assert valid_after["row_version"] == valid_before["row_version"]
        assert valid_after.get("result_json") == valid_before.get("result_json")
        assert json.loads(stale_after["result_json"])["sample_result"] == "Leader rejected"
        assert stale_after["status"] == "In Progress"
        assert reassigned_after.get("solution") in {None, ""}
        assert reassigned_after["assignee_id"] == ids["tech_b"]


def assert_assignment_snapshot_monotonicity(root: Path) -> None:
    leader_dir, tech_dir = root / "leader", root / "tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        stale = export_assignments(client, headers["leader"], ids["tech_a"])
        initial = export_assignments(client, headers["leader"], ids["tech_a"])
        expect(client.patch(
            f"/api/after-sales-tasks/{source['after']['id']}",
            headers=headers["leader"],
            json={"due_date": "2026-09-30", "row_version": source["after"]["row_version"]},
        ), 200, "advance assignment task baseline")
        expect(client.post(
            f"/api/pre-sales-tasks/{source['pre']['id']}/archive",
            headers=headers["leader"],
        ), 200, "withdraw task in newer complete snapshot")
        latest = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(tech_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", initial,
            headers["tech_a"], "initial-snapshot.jpttask",
        ), 200, "import initial complete snapshot")
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", latest,
            headers["tech_a"], "latest-snapshot.jpttask",
        ), 200, "import newer complete snapshot")
        inactive_before = exchange_binding(source["pre"]["id"])
        archived_before = bound_local_task(inactive_before)
        after_before = bound_local_task(exchange_binding(source["after"]["id"]))
        assert inactive_before["is_active"] == 0 and archived_before["archived_at"]
        assert after_before["due_date"] == "2026-09-30"

        preflight = expect(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", stale,
            headers["tech_a"], "stale-snapshot.jpttask",
        ), 200, "preflight stale complete snapshot").json()
        assert preflight["can_import"] is False, preflight
        codes = {issue["code"] for issue in preflight["issues"]}
        assert "stale_assignment_snapshot" in codes, preflight
        assert "stale_task_baseline" in codes, preflight
        response = _upload(
            client, "/api/data/tech-tasks/assignments/import", stale,
            headers["tech_a"], "stale-snapshot.jpttask",
        )
        assert response.status_code >= 400, response.text
        inactive_after = exchange_binding(source["pre"]["id"])
        archived_after = bound_local_task(inactive_after)
        after_after = bound_local_task(exchange_binding(source["after"]["id"]))
        assert inactive_after["is_active"] == 0 and archived_after["archived_at"]
        assert after_after["due_date"] == "2026-09-30"


def assert_cross_leader_snapshot_monotonicity(root: Path) -> None:
    leader_dir, tech_dir = root / "leader", root / "tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        older = export_assignments(client, headers["leader_b"], ids["tech_a"])
        customer_id = source["pre_lead"]["customer_id"]
        customer = expect(client.get(
            f"/api/customers/{customer_id}", headers=headers["leader"],
        ), 200, "read customer before cross-Leader refresh").json()
        expect(client.patch(
            f"/api/customers/{customer_id}", headers=headers["leader"],
            json={"country": "France", "row_version": customer["row_version"]},
        ), 200, "update customer before newer Leader snapshot")
        newer = export_assignments(client, headers["leader"], ids["tech_a"])
        assert newer["created_at"] > older["created_at"]

    with installation(tech_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", newer,
            headers["tech_a"], "newer-leader-a.jpttask",
        ), 200, "import newer snapshot from Leader A")
        local_customer_id = exchange_binding(source["pre"]["id"])["local_customer_id"]
        local_customer = get_db().execute(
            "SELECT country FROM customers WHERE id = ?", (local_customer_id,),
        ).fetchone()
        assert local_customer["country"] == "France"

        preflight = expect(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", older,
            headers["tech_a"], "older-leader-b.jpttask",
        ), 200, "preflight older snapshot from Leader B").json()
        assert preflight["can_import"] is False, preflight
        assert any(
            issue["code"] == "stale_assignment_snapshot"
            for issue in preflight["issues"]
        ), preflight
        response = _upload(
            client, "/api/data/tech-tasks/assignments/import", older,
            headers["tech_a"], "older-leader-b.jpttask",
        )
        assert response.status_code >= 400, response.text
        local_customer = get_db().execute(
            "SELECT country FROM customers WHERE id = ?", (local_customer_id,),
        ).fetchone()
        assert local_customer["country"] == "France"


def assert_legacy_clone_adoption(root: Path) -> None:
    leader_dir, tech_dir = root / "leader", root / "tech-clone"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        get_db().execute(
            "UPDATE pre_sales_tasks SET result_json = ? WHERE id = ?",
            (json.dumps({
                "sample_result": "Existing result",
                "legacy_unknown": "KEEP-ME",
            }), source["pre"]["id"]),
        )
        get_db().commit()

    shutil.copytree(leader_dir, tech_dir)

    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(tech_dir) as client:
        _, headers = login_all(client)
        before_pre, before_after = list_tasks(client, headers["tech_a"])
        assert len(before_pre) == 1 and len(before_after) == 1
        source_ids = {source["pre"]["id"], source["after"]["id"]}
        assert {item["id"] for item in before_pre + before_after} == source_ids

        preflight = assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", assignment,
            headers["tech_a"], "legacy-clone.jpttask",
        ), "preflight assignment on legacy cloned installation")
        adopted = {
            issue.get("task_id") for issue in preflight["issues"]
            if issue["code"] == "existing_source_records_adopted"
        }
        assert adopted == source_ids, preflight
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "legacy-clone.jpttask",
        ), 200, "adopt assignment on legacy cloned installation")

        after_pre, after_after = list_tasks(client, headers["tech_a"])
        assert len(after_pre) == 1 and len(after_after) == 1
        assert {item["id"] for item in after_pre + after_after} == source_ids
        stored_result = json.loads(after_pre[0]["result_json"])
        assert stored_result["sample_result"] == "Existing result"
        assert stored_result["legacy_unknown"] == "KEEP-ME"
        for source_id in source_ids:
            binding = exchange_binding(source_id)
            assert binding["local_task_id"] == source_id
            assert binding["local_lead_id"] == binding["source_lead_id"]
            assert binding["local_customer_id"] == binding["source_customer_id"]


def assert_stale_clone_is_blocked(root: Path) -> None:
    leader_dir, tech_dir = root / "leader", root / "stale-tech-clone"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)

    shutil.copytree(leader_dir, tech_dir)

    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        expect(client.patch(
            f"/api/pre-sales-tasks/{source['pre']['id']}",
            headers=headers["leader"],
            json={
                "status": "Completed",
                "result_json": json.dumps({"sample_result": "LEADER-NEW"}),
                "row_version": source["pre"]["row_version"],
            },
        ), 200, "Leader advances task after database clone")
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(tech_dir) as client:
        _, headers = login_all(client)
        preflight = expect(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", assignment,
            headers["tech_a"], "stale-legacy-clone.jpttask",
        ), 200, "preflight stale cloned task identity").json()
        assert preflight["can_import"] is False, preflight
        assert any(
            issue["code"] == "source_identity_collision"
            for issue in preflight["issues"]
        ), preflight
        response = _upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "stale-legacy-clone.jpttask",
        )
        assert response.status_code >= 400, response.text
        local_pre, _ = list_tasks(client, headers["tech_a"])
        assert local_pre[0]["status"] == "Open"
        assert not local_pre[0].get("result_json")

    with installation(leader_dir) as client:
        _, headers = login_all(client)
        source_pre, _ = list_tasks(client, headers["leader"])
        stored = task_by_id(source_pre, source["pre"]["id"])
        assert stored["status"] == "Completed"
        assert json.loads(stored["result_json"])["sample_result"] == "LEADER-NEW"


def assert_continuous_result_delivery(root: Path) -> None:
    leader_dir, tech_dir = root / "sequential-leader", root / "sequential-tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "continuous-assignment.jpttask",
        ), 200, "import assignment for continuous results")
        update_first_sample_result(client, headers["tech_a"], "first")
        first = export_results(client, headers["tech_a"])
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", first,
            headers["leader"], "first.jptresult",
        ), 200, "import first Tech result")
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        update_first_sample_result(client, headers["tech_a"], "second")
        second = export_results(client, headers["tech_a"])
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/results/preflight", second,
            headers["leader"], "second.jptresult",
        ), "preflight continuous second Tech result")
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", second,
            headers["leader"], "second.jptresult",
        ), 200, "import continuous second Tech result")
        pre_tasks, _ = list_tasks(client, headers["leader"])
        stored = task_by_id(pre_tasks, source["pre"]["id"])
        assert json.loads(stored["result_json"])["sample_result"] == "second"

    leader_dir, tech_dir = root / "conflict-leader", root / "conflict-tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "conflict-assignment.jpttask",
        ), 200, "import assignment for continuous conflict")
        update_first_sample_result(client, headers["tech_a"], "first")
        first = export_results(client, headers["tech_a"])
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", first,
            headers["leader"], "conflict-first.jptresult",
        ), 200, "import first result before Leader conflict")
        pre_tasks, _ = list_tasks(client, headers["leader"])
        current = task_by_id(pre_tasks, source["pre"]["id"])
        expect(client.patch(
            f"/api/pre-sales-tasks/{current['id']}", headers=headers["leader"],
            json={
                "result_json": json.dumps({"sample_result": "Leader override"}),
                "row_version": current["row_version"],
            },
        ), 200, "Leader changes same result field after R1")
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        update_first_sample_result(client, headers["tech_a"], "second")
        second = export_results(client, headers["tech_a"])
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        preflight = expect(_upload(
            client, "/api/data/tech-tasks/results/preflight", second,
            headers["leader"], "conflict-second.jptresult",
        ), 200, "preflight Leader versus continuous Tech conflict").json()
        assert preflight["can_import"] is False, preflight
        assert any(
            issue["code"] == "source_task_changed" for issue in preflight["issues"]
        ), preflight
        response = _upload(
            client, "/api/data/tech-tasks/results/import", second,
            headers["leader"], "conflict-second.jptresult",
        )
        assert response.status_code >= 400, response.text
        pre_tasks, _ = list_tasks(client, headers["leader"])
        stored = task_by_id(pre_tasks, source["pre"]["id"])
        assert json.loads(stored["result_json"])["sample_result"] == "Leader override"

    leader_dir, tech_dir = root / "ordering-leader", root / "ordering-tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "ordering-assignment.jpttask",
        ), 200, "import assignment for result ordering")
        update_first_sample_result(client, headers["tech_a"], "first")
        first = export_results(client, headers["tech_a"])
        update_first_sample_result(client, headers["tech_a"], "second")
        second = export_results(client, headers["tech_a"])
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", second,
            headers["leader"], "ordering-second.jptresult",
        ), 200, "import newer Tech result first")
        stale = expect(_upload(
            client, "/api/data/tech-tasks/results/preflight", first,
            headers["leader"], "ordering-first.jptresult",
        ), 200, "preflight older Tech result after newer result").json()
        assert stale["can_import"] is False, stale
        assert any(
            issue["code"] == "stale_result_package" for issue in stale["issues"]
        ), stale
        response = _upload(
            client, "/api/data/tech-tasks/results/import", first,
            headers["leader"], "ordering-first.jptresult",
        )
        assert response.status_code >= 400, response.text
        pre_tasks, _ = list_tasks(client, headers["leader"])
        stored = task_by_id(pre_tasks, source["pre"]["id"])
        assert json.loads(stored["result_json"])["sample_result"] == "second"


def assert_assignment_snapshot_reconciliation(root: Path) -> None:
    clean_leader, clean_tech = root / "clean-leader", root / "clean-tech"
    with installation(clean_leader) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        initial = export_assignments(client, headers["leader"], ids["tech_a"])
        identity_refresh = export_assignments(client, headers["leader"], ids["tech_a"])
        expect(client.post(
            f"/api/pre-sales-tasks/{source['pre']['id']}/archive",
            headers=headers["leader"],
        ), 200, "withdraw clean source assignment")
        withdrawn = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(clean_tech) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", initial,
            headers["tech_a"], "snapshot-initial.jpttask",
        ), 200, "import initial snapshot")
        binding = exchange_binding(source["pre"]["id"])
        conn = get_db()
        conn.execute(
            "UPDATE pre_sales_tasks SET assignee_id = ? WHERE id = ?",
            (ids["tech_b"], binding["local_task_id"]),
        )
        conn.commit()
        mismatch = expect(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", identity_refresh,
            headers["tech_a"], "identity-refresh.jpttask",
        ), 200, "preflight local assignee mismatch").json()
        assert mismatch["can_import"] is False, mismatch
        assert any(
            issue["code"] == "local_task_assignee_mismatch"
            for issue in mismatch["issues"]
        ), mismatch
        conn.execute(
            "UPDATE pre_sales_tasks SET assignee_id = ? WHERE id = ?",
            (ids["tech_a"], binding["local_task_id"]),
        )
        conn.commit()

        preflight = assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", withdrawn,
            headers["tech_a"], "clean-withdrawal.jpttask",
        ), "preflight clean assignment withdrawal")
        assert any(
            issue["code"] == "assignment_withdrawn"
            and issue["severity"] == "warning"
            for issue in preflight["issues"]
        ), preflight
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", withdrawn,
            headers["tech_a"], "clean-withdrawal.jpttask",
        ), 200, "import clean assignment withdrawal")
        inactive = exchange_binding(source["pre"]["id"])
        archived = bound_local_task(inactive)
        assert inactive["is_active"] == 0, inactive
        assert archived["archived_at"], archived

    conflict_leader, conflict_tech = root / "conflict-leader", root / "conflict-tech"
    with installation(conflict_leader) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        initial = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(conflict_tech) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", initial,
            headers["tech_a"], "conflict-initial.jpttask",
        ), 200, "import conflict snapshot")
        pre_tasks, _ = list_tasks(client, headers["tech_a"])
        local_pre = pre_tasks[0]
        exported_update = expect(client.patch(
            f"/api/pre-sales-tasks/{local_pre['id']}", headers=headers["tech_a"],
            json={
                "status": "Completed",
                "result_json": json.dumps({"sample_result": "First exported Tech result"}),
                "row_version": local_pre["row_version"],
            },
        ), 200, "create first Tech result").json()
        exported = export_results(client, headers["tech_a"])
        assert len(exported["tasks"]) == 1
        expect(client.patch(
            f"/api/pre-sales-tasks/{local_pre['id']}", headers=headers["tech_a"],
            json={
                "result_json": json.dumps({"sample_result": "Changed after export"}),
                "row_version": exported_update["row_version"],
            },
        ), 200, "create Tech result change after export")

    with installation(conflict_leader) as client:
        ids, headers = login_all(client)
        expect(client.post(
            f"/api/pre-sales-tasks/{source['pre']['id']}/archive",
            headers=headers["leader"],
        ), 200, "withdraw assignment with pending result")
        withdrawn = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(conflict_tech) as client:
        _, headers = login_all(client)
        preflight = expect(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", withdrawn,
            headers["tech_a"], "conflicting-withdrawal.jpttask",
        ), 200, "preflight conflicting assignment withdrawal").json()
        assert preflight["can_import"] is False, preflight
        assert any(
            issue["code"] == "withdrawal_has_unsent_changes"
            and issue["severity"] == "conflict"
            for issue in preflight["issues"]
        ), preflight
        response = _upload(
            client, "/api/data/tech-tasks/assignments/import", withdrawn,
            headers["tech_a"], "conflicting-withdrawal.jpttask",
        )
        assert response.status_code >= 400, response.text
        active = exchange_binding(source["pre"]["id"])
        local_task = bound_local_task(active)
        assert active["is_active"] == 1, active
        assert not local_task["archived_at"], local_task

    exported_leader, exported_tech = root / "exported-leader", root / "exported-tech"
    with installation(exported_leader) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        initial = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(exported_tech) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", initial,
            headers["tech_a"], "exported-initial.jpttask",
        ), 200, "import snapshot for exported-result withdrawal")
        pre_tasks, _ = list_tasks(client, headers["tech_a"])
        local_pre = pre_tasks[0]
        updated = expect(client.patch(
            f"/api/pre-sales-tasks/{local_pre['id']}", headers=headers["tech_a"],
            json={
                "status": "Completed",
                "result_json": json.dumps({"sample_result": "Already exported"}),
                "row_version": local_pre["row_version"],
            },
        ), 200, "create result that will be exported").json()
        exported = export_results(client, headers["tech_a"])
        assert len(exported["tasks"]) == 1
        binding = exchange_binding(source["pre"]["id"])
        assert binding["last_exported_local_row_version"] == updated["row_version"]
        exported_state = json.loads(binding["last_exported_result_snapshot_json"])
        assert exported_state["status"] == "Completed"
        assert exported_state["result_json"]["sample_result"] == "Already exported"

    with installation(exported_leader) as client:
        ids, headers = login_all(client)
        pre_tasks, _ = list_tasks(client, headers["leader"])
        source_pre = task_by_id(pre_tasks, source["pre"]["id"])
        expect(client.patch(
            f"/api/pre-sales-tasks/{source_pre['id']}", headers=headers["leader"],
            json={
                "due_date": "2026-10-31",
                "row_version": source_pre["row_version"],
            },
        ), 200, "Leader refreshes only a non-result field after Tech export")
        refreshed = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(exported_tech) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", refreshed,
            headers["tech_a"], "exported-result-refresh.jpttask",
        ), 200, "import non-result refresh after unchanged result export")
        pre_tasks, _ = list_tasks(client, headers["tech_a"])
        assert pre_tasks[0]["due_date"] == "2026-10-31"
        assert json.loads(pre_tasks[0]["result_json"])["sample_result"] == "Already exported"

    with installation(exported_leader) as client:
        ids, headers = login_all(client)
        expect(client.post(
            f"/api/pre-sales-tasks/{source['pre']['id']}/archive",
            headers=headers["leader"],
        ), 200, "withdraw assignment after Tech result export")
        withdrawn = export_assignments(client, headers["leader"], ids["tech_a"])

    with installation(exported_tech) as client:
        _, headers = login_all(client)
        preflight = assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/assignments/preflight", withdrawn,
            headers["tech_a"], "exported-result-withdrawal.jpttask",
        ), "preflight withdrawal after unchanged result export")
        assert any(
            issue["code"] == "assignment_withdrawn"
            for issue in preflight["issues"]
        ), preflight
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", withdrawn,
            headers["tech_a"], "exported-result-withdrawal.jpttask",
        ), 200, "import withdrawal after unchanged result export")
        inactive = exchange_binding(source["pre"]["id"])
        archived = bound_local_task(inactive)
        assert inactive["is_active"] == 0 and archived["archived_at"]


def assert_pre_sales_result_state_merge(root: Path) -> None:
    leader_dir, tech_dir = root / "revert-leader", root / "revert-tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "revert-assignment.jpttask",
        ), 200, "import assignment for result reversion")
        update_first_sample_result(client, headers["tech_a"], "first")
        first = export_results(client, headers["tech_a"])
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", first,
            headers["leader"], "revert-first.jptresult",
        ), 200, "import result before Tech reversion")
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        pre_tasks, _ = list_tasks(client, headers["tech_a"])
        current = pre_tasks[0]
        expect(client.patch(
            f"/api/pre-sales-tasks/{current['id']}", headers=headers["tech_a"],
            json={
                "status": "Open", "result_json": "{}",
                "row_version": current["row_version"],
            },
        ), 200, "Tech returns result to original assignment state")
        reverted = export_results(client, headers["tech_a"])
        assert len(reverted["tasks"]) == 1, reverted
        assert reverted["tasks"][0]["changes"] == {
            "status": "Open", "result_json": {},
        }
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/results/preflight", reverted,
            headers["leader"], "reverted.jptresult",
        ), "preflight explicit Tech result reversion")
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", reverted,
            headers["leader"], "reverted.jptresult",
        ), 200, "import explicit Tech result reversion")
        pre_tasks, _ = list_tasks(client, headers["leader"])
        stored = task_by_id(pre_tasks, source["pre"]["id"])
        assert stored["status"] == "Open"
        assert not stored.get("result_json")

    leader_dir, tech_dir = root / "field-leader", root / "field-tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "field-assignment.jpttask",
        ), 200, "import assignment for result subfield merge")
        pre_tasks, _ = list_tasks(client, headers["tech_a"])
        current = pre_tasks[0]
        expect(client.patch(
            f"/api/pre-sales-tasks/{current['id']}", headers=headers["tech_a"],
            json={
                "result_json": json.dumps({"sample_result": "Tech sample"}),
                "row_version": current["row_version"],
            },
        ), 200, "Tech changes sample result subfield")
        result = export_results(client, headers["tech_a"])
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        pre_tasks, _ = list_tasks(client, headers["leader"])
        current = task_by_id(pre_tasks, source["pre"]["id"])
        expect(client.patch(
            f"/api/pre-sales-tasks/{current['id']}", headers=headers["leader"],
            json={
                "status": "In Progress",
                "result_json": json.dumps({"result_summary": "Leader summary"}),
                "row_version": current["row_version"],
            },
        ), 200, "Leader changes a different result subfield")
        assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/results/preflight", result,
            headers["leader"], "different-result-fields.jptresult",
        ), "preflight different result subfields")
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", result,
            headers["leader"], "different-result-fields.jptresult",
        ), 200, "merge different result subfields")
        pre_tasks, _ = list_tasks(client, headers["leader"])
        stored = task_by_id(pre_tasks, source["pre"]["id"])
        merged = json.loads(stored["result_json"])
        assert stored["status"] == "In Progress"
        assert merged["sample_result"] == "Tech sample"
        assert merged["result_summary"] == "Leader summary"

    leader_dir, tech_dir = root / "after-field-leader", root / "after-field-tech"
    with installation(leader_dir) as client:
        ids, headers = login_all(client)
        source = seed_tasks(client, ids, headers)
        assignment = export_assignments(client, headers["leader"], ids["tech_a"])
    with installation(tech_dir) as client:
        _, headers = login_all(client)
        expect(_upload(
            client, "/api/data/tech-tasks/assignments/import", assignment,
            headers["tech_a"], "after-field-assignment.jpttask",
        ), 200, "import assignment for after-sales field merge")
        _, after_tasks = list_tasks(client, headers["tech_a"])
        current = after_tasks[0]
        expect(client.patch(
            f"/api/after-sales-tasks/{current['id']}", headers=headers["tech_a"],
            json={
                "solution": "Tech solution",
                "row_version": current["row_version"],
            },
        ), 200, "Tech changes after-sales solution")
        result = export_results(client, headers["tech_a"])
    with installation(leader_dir) as client:
        _, headers = login_all(client)
        _, after_tasks = list_tasks(client, headers["leader"])
        current = task_by_id(after_tasks, source["after"]["id"])
        expect(client.patch(
            f"/api/after-sales-tasks/{current['id']}", headers=headers["leader"],
            json={
                "customer_satisfaction": "Leader satisfied",
                "row_version": current["row_version"],
            },
        ), 200, "Leader changes a different after-sales field")
        assert_clean_preflight(_upload(
            client, "/api/data/tech-tasks/results/preflight", result,
            headers["leader"], "different-after-fields.jptresult",
        ), "preflight different after-sales fields")
        expect(_upload(
            client, "/api/data/tech-tasks/results/import", result,
            headers["leader"], "different-after-fields.jptresult",
        ), 200, "merge different after-sales fields")
        _, after_tasks = list_tasks(client, headers["leader"])
        stored = task_by_id(after_tasks, source["after"]["id"])
        assert stored["solution"] == "Tech solution"
        assert stored["customer_satisfaction"] == "Leader satisfied"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt-tech-task-package-") as directory:
        root = Path(directory)
        assert_roundtrip(root / "roundtrip")
        assert_security_and_atomicity(root / "security")
        assert_assignment_snapshot_monotonicity(root / "monotonic")
        assert_cross_leader_snapshot_monotonicity(root / "cross-leader")
        assert_legacy_clone_adoption(root / "legacy-clone")
        assert_stale_clone_is_blocked(root / "stale-legacy-clone")
        assert_continuous_result_delivery(root / "continuous-results")
        assert_assignment_snapshot_reconciliation(root / "snapshot")
        assert_pre_sales_result_state_merge(root / "result-state")
    print("PASS: Tech task packages are narrow, role-scoped, idempotent and atomic")


if __name__ == "__main__":
    main()
