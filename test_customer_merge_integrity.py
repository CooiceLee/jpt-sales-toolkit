#!/usr/bin/env python3
"""Regression coverage for alias lifecycle and loss-aware customer merge."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import CustomerRepository, LeadRepository, UserRepository, close_db, init_db
from backend.repositories.base import now_iso
from backend.services.customer_alias_service import CustomerAliasService
from backend.services.customer_merge_service import CustomerMergeService
from backend.services.customer_service import CustomerService
from backend.routers.deps import get_current_user


def _fresh_db(path: Path) -> dict:
    close_db()
    init_db(path)
    users = UserRepository()
    leader = users.create("mergeleader", "dummy", "Merge Leader", "leader")
    sales = users.create("mergesales", "dummy", "Merge Sales", "sales")
    customers = CustomerRepository()
    source = customers.create({
        "display_name": "Old Europe Laser", "normalized_name": "old europe laser",
        "country": "Germany", "extra_json": '{"legacy":"keep"}',
    }, leader)
    target = customers.create({
        "display_name": "Europe Laser GmbH", "normalized_name": "europe laser gmbh",
    }, leader)
    return {"leader": leader, "sales": sales, "source": source, "target": target}


def _insert_trip_stop(conn, ids: dict, lead_id: str) -> str:
    now = now_iso()
    plan_id, stop_id = "merge-plan", "merge-stop"
    conn.execute(
        """INSERT INTO trip_plans
           (id, title, owner_id, status, created_at, created_by, updated_at, updated_by, row_version)
           VALUES (?, 'Merge Plan', ?, 'Draft', ?, ?, ?, ?, 1)""",
        (plan_id, ids["leader"], now, ids["leader"], now, ids["leader"]),
    )
    conn.execute(
        """INSERT INTO trip_plan_stops
           (id, plan_id, customer_id, lead_id, sequence_no, result_status,
            created_at, created_by, updated_at, updated_by, row_version)
           VALUES (?, ?, ?, ?, 1, 'Planned', ?, ?, ?, ?, 1)""",
        (stop_id, plan_id, ids["source"], lead_id, now, ids["leader"], now, ids["leader"]),
    )
    conn.commit()
    return stop_id


def _seed_generated_trip_route(conn, ids: dict, stop_id: str) -> str:
    """Create one locked active leg so merge invalidation is observable."""
    now = now_iso()
    leg_id = "merge-leg"
    conn.execute(
        """UPDATE trip_plans
           SET itinerary_generated_at = ?, itinerary_summary = ?,
               updated_at = ?, updated_by = ?
           WHERE id = 'merge-plan'""",
        (now, json.dumps({"valid": True}), now, ids["leader"]),
    )
    conn.execute(
        """INSERT INTO trip_plan_legs
           (id, plan_id, leg_key, sequence_no, from_kind, from_label,
            to_kind, to_stop_id, to_label, selected_mode, mode_locked,
            distance_km, time_hours, travel_days, manual_distance_km,
            manual_time_hours, manual_travel_days, notes,
            created_at, created_by, updated_at, updated_by, row_version)
           VALUES (?, 'merge-plan', ?, 1, 'origin', 'Origin',
                   'stop', ?, 'Old Europe Laser', 'other', 1,
                   9, 1, 0, 9, 1, 0, 'Locked before merge',
                   ?, ?, ?, ?, 1)""",
        (leg_id, f"origin>{stop_id}", stop_id, now, ids["leader"], now, ids["leader"]),
    )
    conn.commit()
    return leg_id


def test_alias_lifecycle_and_match(path: Path) -> None:
    ids = _fresh_db(path)
    aliases = CustomerAliasService()
    alias = aliases.create(ids["target"], "ELG Europe", ids["leader"])
    assert CustomerService().match(None, "ELG Europe")[0]["match_type"] == "alias"
    assert CustomerService().list(search="ELG Europe")[0]["id"] == ids["target"]

    alias = aliases.update(ids["target"], alias["id"], "ELG EU", ids["leader"])
    assert not CustomerService().match(None, "ELG Europe")
    assert CustomerService().match(None, "ELG EU")[0]["id"] == ids["target"]
    aliases.archive(ids["target"], alias["id"], ids["leader"])
    assert not CustomerService().match(None, "ELG EU")
    assert len(aliases.list(ids["target"], include_archived=True)) == 1
    aliases.restore(ids["target"], alias["id"], ids["leader"])
    assert CustomerService().match(None, "ELG EU")[0]["id"] == ids["target"]


def test_fuzzy_candidate_ranking(path: Path) -> None:
    ids = _fresh_db(path)
    service = CustomerService()
    service.alias_repo.create(ids["target"], "ELG Europe", ids["leader"])
    hidden = service.alias_repo.create(ids["source"], "Hidden Old Name", ids["leader"])
    service.alias_repo.set_archived(ids["source"], hidden["id"], ids["leader"], True)
    third = service.create({
        "display_name": "European Laser Systems",
        "country": "France",
    }, ids["leader"])

    alias_matches = service.fuzzy_merge_candidates("ELG Europe")
    assert alias_matches[0]["id"] == ids["target"]
    assert alias_matches[0]["matched_on"] == "alias"
    assert alias_matches[0]["matched_value"] == "ELG Europe"
    assert alias_matches[0]["score"] == 100
    assert not any(item["id"] == ids["source"] for item in service.fuzzy_merge_candidates("Hidden Old Name"))

    typo_matches = service.fuzzy_merge_candidates("Europe Lazer Gmbh")
    assert typo_matches[0]["id"] == ids["target"]
    assert typo_matches[0]["score"] > typo_matches[1]["score"]
    assert any(item["id"] == third["id"] for item in typo_matches)


def test_alias_and_merge_api(path: Path) -> None:
    ids = _fresh_db(path)
    LeadRepository().create({
        "customer_id": ids["target"], "title": "API Access Lead",
        "owner_id": ids["sales"], "sales_stage": "New",
    }, ids["sales"])
    users = {
        "leader": {"id": ids["leader"], "role": "leader"},
        "sales": {"id": ids["sales"], "role": "sales"},
    }
    actor = {"value": users["leader"]}

    async def current_user():
        return actor["value"]

    app = create_app()
    app.dependency_overrides[get_current_user] = current_user
    client = TestClient(app)
    created = client.post(
        f"/api/customers/{ids['target']}/aliases", json={"alias_name": "API Alias"}
    )
    assert created.status_code == 200, created.text
    alias_id = created.json()["id"]
    assert client.patch(
        f"/api/customers/{ids['target']}/aliases/{alias_id}", json={"alias_name": "API Alias Updated"}
    ).status_code == 200
    assert client.post(
        f"/api/customers/{ids['target']}/aliases/{alias_id}/archive"
    ).status_code == 200
    assert client.post(
        f"/api/customers/{ids['target']}/aliases/{alias_id}/restore"
    ).status_code == 200
    actor["value"] = users["sales"]
    assert client.get(f"/api/customers/{ids['target']}/aliases").status_code == 200
    assert client.post(
        f"/api/customers/{ids['target']}/aliases", json={"alias_name": "Denied"}
    ).status_code == 403
    assert client.post("/api/customers/merge/preview", json={
        "source_customer_id": ids["source"], "target_customer_id": ids["target"],
        "source_row_version": 1, "target_row_version": 1,
    }).status_code == 403
    assert client.get("/api/customers/merge/candidates?query=API%20Alias").status_code == 403
    actor["value"] = users["leader"]
    candidates = client.get("/api/customers/merge/candidates?query=API%20Alias%20Updated")
    assert candidates.status_code == 200, candidates.text
    assert candidates.json()[0]["id"] == ids["target"]
    assert candidates.json()[0]["matched_on"] == "alias"
    assert client.post("/api/customers/merge/preview", json={
        "source_customer_id": ids["source"], "target_customer_id": ids["target"],
    }).status_code == 422
    response = client.post("/api/customers/merge/preview", json={
        "source_customer_id": ids["source"], "target_customer_id": ids["target"],
        "source_row_version": 1, "target_row_version": 1,
    })
    assert response.status_code == 200, response.text


def test_complete_merge(path: Path) -> None:
    ids = _fresh_db(path)
    customers = CustomerRepository()
    aliases = CustomerAliasService()
    aliases.create(ids["source"], "Legacy Laser Europe", ids["leader"])
    customers.add_domain(ids["target"], "laser.example", True)
    source_domain = customers.add_domain(ids["source"], "laser.example", True)

    target_contact = customers.add_contact(ids["target"], {
        "name": "Target Name", "email": "same@laser.example", "is_primary": True,
    })
    source_contact = customers.add_contact(ids["source"], {
        "name": "Source Name", "email": "same@laser.example", "phone": "+49-123",
        "is_primary": True,
    })
    customers.add_contact(ids["source"], {
        "name": "Field Name", "email": "field@laser.example", "is_primary": True,
    })

    leads = LeadRepository()
    active_lead = leads.create({
        "customer_id": ids["source"], "primary_contact_id": source_contact,
        "title": "Active Opportunity", "owner_id": ids["sales"], "sales_stage": "Following",
    }, ids["sales"])
    archived_lead = leads.create({
        "customer_id": ids["source"], "title": "Archived Opportunity",
        "owner_id": ids["sales"], "sales_stage": "Lost",
    }, ids["sales"])
    leads.archive(archived_lead, ids["leader"])
    stop_id = _insert_trip_stop(customers.conn, ids, active_lead)
    leg_id = _seed_generated_trip_route(customers.conn, ids, stop_id)

    source = customers.get_by_id(ids["source"])
    target = customers.get_by_id(ids["target"])
    merger = CustomerMergeService(customers)
    preview = merger.preview(ids["source"], ids["target"], source["row_version"], target["row_version"])
    assert preview["counts"]["leads"] == 2
    assert preview["counts"]["trip_plan_stops"] == 1
    result = merger.merge(
        ids["source"], ids["target"], ids["leader"],
        source["row_version"], target["row_version"],
    )
    assert result["moved_leads"] == 2
    assert result["moved_trip_plan_stops"] == 1
    assert result["archived_duplicate_contacts"] == 1

    conn = customers.conn
    for table in ("leads", "trip_plan_stops", "customer_contacts", "customer_domains", "customer_aliases"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE customer_id = ?", (ids["source"],)).fetchone()[0] == 0
    assert conn.execute("SELECT customer_id FROM trip_plan_stops WHERE id = ?", (stop_id,)).fetchone()[0] == ids["target"]
    moved_lead = conn.execute("SELECT customer_id, primary_contact_id FROM leads WHERE id = ?", (active_lead,)).fetchone()
    assert tuple(moved_lead) == (ids["target"], target_contact)
    assert conn.execute("SELECT phone FROM customer_contacts WHERE id = ?", (target_contact,)).fetchone()[0] == "+49-123"
    assert conn.execute(
        "SELECT COUNT(*) FROM customer_contacts WHERE customer_id = ? AND archived_at IS NULL AND is_primary = 1",
        (ids["target"],),
    ).fetchone()[0] == 1
    retired_domain = conn.execute("SELECT customer_id, archived_at, domain FROM customer_domains WHERE id = ?", (source_domain,)).fetchone()
    assert retired_domain[0] == ids["target"] and retired_domain[1] and "#merged-" in retired_domain[2]
    assert CustomerService().match(None, "Old Europe Laser")[0]["id"] == ids["target"]

    route = conn.execute(
        "SELECT itinerary_generated_at, itinerary_summary FROM trip_plans WHERE id='merge-plan'"
    ).fetchone()
    assert route[0] is None
    route_summary = json.loads(route[1])
    assert route_summary["stale"] is True
    assert route_summary["reason"] == "customer_merged"
    merged_leg = conn.execute(
        "SELECT archived_at, mode_locked FROM trip_plan_legs WHERE id = ?", (leg_id,)
    ).fetchone()
    assert merged_leg[0] is not None and merged_leg[1] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id='merge-plan' AND archived_at IS NULL"
    ).fetchone()[0] == 0

    audit = conn.execute("SELECT before_json, after_json FROM audit_logs WHERE id = ?", (result["audit_id"],)).fetchone()
    before, after = json.loads(audit[0]), json.loads(audit[1])
    assert before["source_relations"]["trip_plan_stops"][0]["id"] == stop_id
    assert after["moved_trip_plan_stops"] == 1


def test_audit_failure_rolls_back(path: Path) -> None:
    ids = _fresh_db(path)
    leads = LeadRepository()
    lead_id = leads.create({
        "customer_id": ids["source"], "title": "Rollback Opportunity",
        "owner_id": ids["sales"], "sales_stage": "New",
    }, ids["sales"])
    conn = leads.conn
    stop_id = _insert_trip_stop(conn, ids, lead_id)
    leg_id = _seed_generated_trip_route(conn, ids, stop_id)
    conn.execute(
        """CREATE TRIGGER fail_merge_audit BEFORE INSERT ON audit_logs
           WHEN NEW.event_type = 'merge_customer'
           BEGIN SELECT RAISE(ABORT, 'audit failure'); END"""
    )
    conn.commit()
    source = CustomerRepository().get_by_id(ids["source"])
    target = CustomerRepository().get_by_id(ids["target"])
    try:
        CustomerMergeService().merge(
            ids["source"], ids["target"], ids["leader"],
            source["row_version"], target["row_version"],
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("Expected audit insertion to abort the merge")
    assert LeadRepository().get_by_id(lead_id)["customer_id"] == ids["source"]
    assert CustomerRepository().get_by_id(ids["source"])["archived_at"] is None
    assert conn.execute(
        "SELECT customer_id FROM trip_plan_stops WHERE id = ?", (stop_id,)
    ).fetchone()[0] == ids["source"]
    route = conn.execute(
        "SELECT itinerary_generated_at, itinerary_summary FROM trip_plans WHERE id='merge-plan'"
    ).fetchone()
    assert route[0] is not None and json.loads(route[1]) == {"valid": True}
    rolled_back_leg = conn.execute(
        "SELECT archived_at, mode_locked FROM trip_plan_legs WHERE id = ?", (leg_id,)
    ).fetchone()
    assert rolled_back_leg[0] is None and rolled_back_leg[1] == 1


def main() -> None:
    with TemporaryDirectory(prefix="jpt-customer-merge-") as temp:
        root = Path(temp)
        test_alias_lifecycle_and_match(root / "alias.sqlite")
        test_fuzzy_candidate_ranking(root / "fuzzy.sqlite")
        test_alias_and_merge_api(root / "api.sqlite")
        test_complete_merge(root / "merge.sqlite")
        test_audit_failure_rolls_back(root / "rollback.sqlite")
    close_db()
    print("customer alias and merge integrity regression passed")


if __name__ == "__main__":
    main()
