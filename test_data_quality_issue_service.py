#!/usr/bin/env python3
"""Service and runtime-migration tests for imported data-quality issues."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.repositories import close_db, get_db, init_db
from backend.services import DataQualityIssueService
from backend.tests.data_quality_issue_fixture import actor, build_fixture


ACTIVE_OWNER = {
    "customer", "contact", "alias", "lead", "assignment", "activity",
    "pre_assigned", "pre_other", "after_assigned",
}


def issue_keys(service: DataQualityIssueService, ids: dict, name: str) -> set[str]:
    by_id = {value: key for key, value in ids["issues"].items()}
    return {by_id[item["id"]] for item in service.list(actor(ids, name))}


def expect_error(error_type, action) -> None:
    try:
        action()
    except error_type:
        return
    raise AssertionError(f"Expected {error_type.__name__}")


def assert_migrations(root: Path) -> None:
    tables = {"import_batches", "import_bindings", "data_quality_issues"}
    new_path, old_path = root / "new.sqlite", root / "old.sqlite"
    close_db(); init_db(new_path)
    assert tables <= {row[0] for row in get_db().execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    close_db(); init_db(old_path); close_db()
    with sqlite3.connect(old_path) as conn:
        conn.execute("CREATE TABLE legacy_marker (value TEXT)")
        conn.execute("INSERT INTO legacy_marker VALUES ('preserved')")
        conn.executescript("""DROP TABLE data_quality_issues;
            DROP TABLE import_bindings; DROP TABLE import_batches;""")
    init_db(old_path)
    names = {row[0] for row in get_db().execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert tables <= names
    assert get_db().execute("SELECT value FROM legacy_marker").fetchone()[0] == "preserved"


def assert_permissions(service: DataQualityIssueService, ids: dict) -> None:
    assert issue_keys(service, ids, "leader") == set(ids["issues"])
    assert issue_keys(service, ids, "sales_owner") == ACTIVE_OWNER
    assert issue_keys(service, ids, "sales_collab") == ACTIVE_OWNER
    assert issue_keys(service, ids, "sales_watcher") == set()
    assert issue_keys(service, ids, "sales_other") == {"other_lead"}
    assert issue_keys(service, ids, "tech_assigned") == {"pre_assigned", "after_assigned"}
    assert issue_keys(service, ids, "tech_other") == {"pre_other"}
    assert service.counts_for_leads([ids["lead_id"]]) == {ids["lead_id"]: 1}


def assert_lifecycle(service: DataQualityIssueService, ids: dict) -> None:
    issues = ids["issues"]
    owner, tech, leader = (actor(ids, name) for name in (
        "sales_owner", "tech_assigned", "leader"
    ))
    resolved = service.update(issues["lead"], "resolved", "fixed", owner)
    assert resolved["status"] == "resolved" and resolved["resolved_by"] == owner["id"]
    reopened = service.update(issues["lead"], "open", "", owner)
    assert reopened["status"] == "open" and reopened["resolved_at"] is None
    service.update(issues["pre_assigned"], "resolved", "fixed", tech)
    assert service.update(issues["pre_assigned"], "open", "", tech)["status"] == "open"
    expect_error(PermissionError, lambda: service.update(issues["lead"], "ignored", "", owner))
    expect_error(PermissionError, lambda: service.update(issues["pre_assigned"], "ignored", "", tech))
    ignored = service.update(issues["unbound"], "ignored", "not actionable", leader)
    assert ignored["status"] == "ignored" and ignored["resolved_by"] == leader["id"]
    assert service.update(issues["unbound"], "open", "", leader)["resolved_by"] is None
    expect_error(PermissionError, lambda: service.update(issues["other_lead"], "resolved", "", owner))
    expect_error(LookupError, lambda: service.update("missing", "resolved", "", leader))
    expect_error(ValueError, lambda: service.update(issues["lead"], "invalid", "", leader))


def main() -> None:
    with TemporaryDirectory(prefix="jpt_quality_service_") as tmp:
        root = Path(tmp)
        assert_migrations(root)
        ids = build_fixture(root / "data")
        service = DataQualityIssueService()
        assert_permissions(service, ids)
        assert_lifecycle(service, ids)
        close_db()
    print("PASS: quality-issue service permissions, lifecycle, and migrations")


if __name__ == "__main__":
    main()
