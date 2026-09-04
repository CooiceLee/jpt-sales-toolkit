"""A real team plan survives Preview, Generate and a reload from the database.

Two colleagues leave from different cities, each visits their own customer on
the same booked morning, they meet at a shared stop, and each goes home to their
own place. What the calculation worked out has to still be there after a save.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_team_roundtrip_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from backend.config import init_settings  # noqa: E402
from backend.repositories import close_db  # noqa: E402
from backend.repositories.base import ConflictError  # noqa: E402
from backend.repositories.base import generate_uuid, get_db, now_iso  # noqa: E402
from backend.services.review_service import ReviewService  # noqa: E402
from backend.services.trip_visit_briefing_repository import (  # noqa: E402
    normalize_payload,
)
from backend.startup_upgrade import initialize_database_safely  # noqa: E402

SHANGHAI = ("Shanghai", 31.2304, 121.4737)
SHENZHEN = ("Shenzhen", 22.5431, 114.0579)
FRANKFURT = ("Frankfurt Customer", 50.1109, 8.6821)
PARIS = ("Paris Customer", 48.8566, 2.3522)
MUNICH = ("Munich Expo", 48.1351, 11.5820)


def _seed(service: ReviewService) -> dict:
    conn = get_db()
    stamp = now_iso()
    people = {}
    for key, name in (("zhang", "Zhang"), ("li", "Li")):
        people[key] = generate_uuid()
        conn.execute(
            "INSERT INTO users (id,username,display_name,role,password_hash,"
            "is_active,created_at) VALUES (?,?,?,'sales','h',1,?)",
            (people[key], name.lower(), name, stamp),
        )
    actor = people["zhang"]
    plan_id = generate_uuid()
    conn.execute(
        """INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,
           travel_mode,route_order_mode,transport_mode_priority,
           origin_name,origin_lat,origin_lng,
           destination_name,destination_lat,destination_lng,
           avoid_weekends,status,planning_mode,
           created_at,created_by,updated_at,updated_by,row_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Draft','team',?,?,?,?,1)""",
        (plan_id, "Team Europe", actor, "2026-09-14", "2026-09-30", "flight",
         "manual", '["flight","drive","ground_public"]',
         *SHANGHAI[0:1], SHANGHAI[1], SHANGHAI[2],
         *SHANGHAI[0:1], SHANGHAI[1], SHANGHAI[2],
         1, stamp, actor, stamp, actor),
    )
    stops = {}
    for key, (name, lat, lng), attendee in (
        ("frankfurt", FRANKFURT, "zhang"),
        ("paris", PARIS, "li"),
    ):
        customer_id = generate_uuid()
        conn.execute(
            "INSERT INTO customers (id,display_name,normalized_name,lat,lng,"
            "created_at,updated_at,row_version) VALUES (?,?,?,?,?,?,?,1)",
            (customer_id, name, name.lower(), lat, lng, stamp, stamp),
        )
        stop_id = generate_uuid()
        conn.execute(
            """INSERT INTO trip_plan_stops (id,plan_id,customer_id,sequence_no,
               duration_half_days,stay_days,preferred_period,schedule_locked,
               planned_date,planned_start_period,confirmation_status,
               created_at,created_by,updated_at,updated_by,row_version)
               VALUES (?,?,?,1,1,1,'auto',1,'2026-09-16','AM','confirmed',
               ?,?,?,?,1)""",
            (stop_id, plan_id, customer_id, stamp, actor, stamp, actor),
        )
        service.trip_plan_service.briefing_repo.replace(
            stop_id,
            normalize_payload({"participants": [{"user_id": people[attendee]}]}),
            actor, stamp, None,
        )
        stops[key] = stop_id
    conn.commit()

    # A shared stop both of them attend, once each has arrived.
    plan = service.add_trip_free_stop(
        plan_id,
        {"category": "other", "location_name": MUNICH[0],
         "lat": MUNICH[1], "lng": MUNICH[2], "duration_half_days": 2,
         "participant_user_ids": [people["zhang"], people["li"]]},
        actor, "leader",
    )
    stops["munich"] = [
        item["id"] for item in plan["stops"]
        if item.get("location_name") == MUNICH[0]
    ][0]

    for key, origin in (("zhang", SHANGHAI), ("li", SHENZHEN)):
        service.set_trip_member(
            plan_id,
            {
                "user_id": people[key],
                "origin_name_override": origin[0],
                "origin_lat_override": origin[1],
                "origin_lng_override": origin[2],
                "destination_name_override": origin[0],
                "destination_lat_override": origin[1],
                "destination_lng_override": origin[2],
            },
            actor, "leader",
        )
    return {"plan_id": plan_id, "actor": actor, "people": people, "stops": stops}


def check_a_new_plan_travels_with_its_owner(service, seed) -> None:
    """Creating a trip puts the person who created it on it.

    There is one way to plan a trip and it needs somebody to move. A plan
    created with nobody on it could not be previewed, saved or exported until
    the user worked out that they had to add themselves first.
    """
    plan = service.trip_plan_service.create_trip_plan(
        {
            "title": "Fresh plan",
            "start_date": "2026-09-14",
            "end_date": "2026-09-30",
            "origin_name": "Shanghai", "origin_lat": 31.2304,
            "origin_lng": 121.4737,
            "destination_name": "Shanghai", "destination_lat": 31.2304,
            "destination_lng": 121.4737,
        },
        seed["actor"],
    )
    plan = service.get_trip_plan(plan["id"], seed["actor"], "leader")
    travellers = [member["user_id"] for member in plan["members"]]
    assert travellers == [seed["actor"]], (
        f"a new trip travels with {travellers} instead of the person who made it"
    )
    assert plan["planning_mode"] == "team", plan["planning_mode"]


def check_members_are_team_accounts(service, seed) -> None:
    """Only people the company can send are planned for."""
    try:
        service.set_trip_member(
            seed["plan_id"], {"user_id": "not-an-account"},
            seed["actor"], "leader",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("planned a trip for somebody with no account")


def check_missing_endpoints_are_rejected(service, seed) -> None:
    """Somebody with nowhere to leave from is missing data, not route-complete."""
    from backend.services.trip_team_adapter import validate_team_inputs

    try:
        validate_team_inputs(("zhang",), {}, {"__default__": {}})
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a member with no departure point")
    try:
        validate_team_inputs((), {"__default__": {}}, {"__default__": {}})
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a team trip with nobody on it")


def check_member_order_is_stable(service, seed) -> None:
    """Lane order must not depend on a random id.

    Two members added in the same moment reach the frontend as the order of the
    timeline lanes. If that came down to the random membership row id, the lanes
    would swap places on a refresh and the frontend would need a sorting rule of
    its own.
    """
    conn = get_db()
    plan_id = seed["plan_id"]
    stamp = now_iso()
    users = sorted(seed["people"].values())
    # Same created_at, and row ids deliberately in the opposite order.
    for row_id, user_id in zip(("zzzz-row", "aaaa-row"), users):
        conn.execute(
            "UPDATE trip_plan_members SET id = ?, created_at = ? "
            "WHERE plan_id = ? AND user_id = ?",
            (row_id, stamp, plan_id, user_id),
        )
    conn.commit()
    repo = service.trip_plan_service.member_repo
    assert list(repo.member_ids(plan_id)) == users, (
        "member order must be decided by user_id, not the random row id"
    )
    assert [item["user_id"] for item in repo.list_active(plan_id)] == users


def check_round_trip(service, seed) -> None:
    plan_id, actor, people = seed["plan_id"], seed["actor"], seed["people"]
    preview = service.preview_trip_itinerary(plan_id, {}, actor, "leader")
    summary = preview["itinerary_summary"]
    assert summary["planning_mode"] == "team"
    assert set(summary["members"]) == set(people.values())

    # Two customers at the same booked hour is what a team is for, not an error.
    assert not [
        risk for risk in summary["risks"]
        if risk["kind"] in ("member_double_booked", "unassigned_parallel_events")
    ], summary["risks"]

    # One stop is one row, however many colleagues attend it.
    munich_rows = [
        row for row in summary["stop_updates"]
        if row["id"] == seed["stops"]["munich"]
    ]
    assert len(munich_rows) == 1, f"a shared stop wrote {len(munich_rows)} rows"

    expected_legs = {
        (leg["member_id"], leg["leg_key"]): (
            leg["sequence_no"], leg["planned_start_date"],
            leg["planned_start_period"], leg["planned_end_date"],
            leg["planned_end_period"],
        )
        for leg in summary["legs"]
    }
    assert expected_legs, "a team trip has journeys in it"
    for member in people.values():
        lane = sorted(
            value[0] for key, value in expected_legs.items() if key[0] == member
        )
        assert lane == list(range(1, len(lane) + 1)), f"{member} lane: {lane}"

    saved = service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    assert saved is not None

    reloaded = service.get_trip_plan(plan_id, actor, "leader")
    actual_legs = {
        (leg["member_id"], leg["leg_key"]): (
            leg["sequence_no"], leg["planned_start_date"],
            leg["planned_start_period"], leg["planned_end_date"],
            leg["planned_end_period"],
        )
        for leg in reloaded["legs"]
    }
    assert actual_legs == expected_legs, (
        "the saved journeys differ from the ones that were calculated:\n"
        f"  calculated {sorted(expected_legs)}\n  reloaded   {sorted(actual_legs)}"
    )

    stored = reloaded["itinerary_summary"]
    assert stored["member_totals"] == summary["member_totals"]
    assert stored["risks"] == summary["risks"]
    assert stored["schedule_items"] == summary["schedule_items"]

    # The times the calculation gave the stops are on the stops themselves.
    by_id = {item["id"]: item for item in reloaded["stops"]}
    for row in summary["stop_updates"]:
        stop = by_id[row["id"]]
        assert stop["planned_date"] == row["planned_date"], stop
        assert stop["planned_start_period"] == row["planned_start_period"]
        assert stop["planned_end_date"] == row["planned_end_date"]
        assert stop["planned_end_period"] == row["planned_end_period"]

    # Everybody is planned all the way home, each to their own city.
    homes = {
        leg["member_id"]: leg["to_label"] for leg in reloaded["legs"]
        if leg["leg_key"].endswith(">destination")
    }
    assert set(homes.values()) == {SHANGHAI[0], SHENZHEN[0]}, homes
    for total in stored["member_totals"].values():
        assert total["route_complete"] is True
        assert total["calculated_end_date"]


def _is_stale(plan) -> bool:
    summary = plan.get("itinerary_summary") or {}
    return summary.get("stale") is True or summary.get("valid") is False


def check_changing_who_attends_invalidates_the_route(service, seed) -> None:
    """Who goes decides the route, so changing it makes the old one out of date.

    Swapping the colleague on a visit changes whose lane it is on, the legs to
    and from it, the travel time and where everybody is afterwards. Leaving the
    calculated route in place would show a trip nobody is taking.
    """
    plan_id, actor, people = seed["plan_id"], seed["actor"], seed["people"]
    stop_id = seed["stops"]["frankfurt"]

    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    assert not _is_stale(service.get_trip_plan(plan_id, actor, "leader"))

    stop = [
        item for item in service.get_trip_plan(plan_id, actor, "leader")["stops"]
        if item["id"] == stop_id
    ][0]
    briefing = stop["briefing"]
    service.put_trip_visit_briefing(
        plan_id, stop_id,
        {**briefing, "stop_row_version": stop["row_version"],
         "participants": [{"user_id": people["li"]}]},
        actor, "leader",
    )
    assert _is_stale(service.get_trip_plan(plan_id, actor, "leader")), (
        "changing who attends a visit must make the calculated route stale"
    )

    # The same people in another order is not a change.
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    stop = [
        item for item in service.get_trip_plan(plan_id, actor, "leader")["stops"]
        if item["id"] == stop_id
    ][0]
    service.put_trip_visit_briefing(
        plan_id, stop_id,
        {**stop["briefing"], "stop_row_version": stop["row_version"],
         "participants": [{"user_id": people["li"]}]},
        actor, "leader",
    )
    assert not _is_stale(service.get_trip_plan(plan_id, actor, "leader")), (
        "saving the same attendees again must not throw the route away"
    )


def check_changing_a_free_stop_scope_invalidates_the_route(service, seed) -> None:
    """Who is at a personal stop decides whose route it is on."""
    plan_id, actor, people = seed["plan_id"], seed["actor"], seed["people"]
    free_stop_id = seed["stops"]["munich"]

    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    assert not _is_stale(service.get_trip_plan(plan_id, actor, "leader"))

    service.update_trip_free_stop(
        plan_id, free_stop_id,
        {"participant_user_ids": [people["zhang"]]},
        actor, "leader",
    )
    assert _is_stale(service.get_trip_plan(plan_id, actor, "leader")), (
        "narrowing a personal stop to one member must make the route stale"
    )


def _flexible_stop(service, seed):
    """Add a customer visit with no agreed time, and return its stop id."""
    conn = get_db()
    stamp = now_iso()
    customer_id = generate_uuid()
    conn.execute(
        "INSERT INTO customers (id,display_name,normalized_name,lat,lng,"
        "created_at,updated_at,row_version) VALUES (?,?,?,?,?,?,?,1)",
        (customer_id, "Stuttgart Customer", "stuttgart customer",
         48.7758, 9.1829, stamp, stamp),
    )
    stop_id = generate_uuid()
    conn.execute(
        """INSERT INTO trip_plan_stops (id,plan_id,customer_id,sequence_no,
           duration_half_days,stay_days,preferred_period,schedule_locked,
           confirmation_status,created_at,created_by,updated_at,updated_by,
           row_version) VALUES (?,?,?,9,1,1,'auto',0,'unconfirmed',?,?,?,?,1)""",
        (stop_id, seed["plan_id"], customer_id, stamp, seed["actor"], stamp,
         seed["actor"]),
    )
    conn.commit()
    service.trip_plan_service.briefing_repo.replace(
        stop_id,
        normalize_payload({"participants": [{"user_id": seed["people"]["zhang"]}]}),
        seed["actor"], stamp, None,
    )
    return stop_id


def _solo_team_plan(service):
    """A team plan with one member and one visit with no agreed time."""
    conn = get_db()
    stamp = now_iso()
    actor = generate_uuid()
    conn.execute(
        "INSERT INTO users (id,username,display_name,role,password_hash,"
        "is_active,created_at) VALUES (?,?,'Solo','sales','h',1,?)",
        (actor, f"solo-{actor[:8]}", stamp),
    )
    plan_id, customer_id, stop_id = (generate_uuid() for _ in range(3))
    conn.execute(
        """INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,
           travel_mode,route_order_mode,transport_mode_priority,origin_name,
           origin_lat,origin_lng,destination_name,destination_lat,
           destination_lng,avoid_weekends,status,planning_mode,created_at,
           created_by,updated_at,updated_by,row_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Draft','team',?,?,?,?,1)""",
        (plan_id, "Solo trip", actor, "2026-09-14", "2026-10-10", "flight",
         "manual", '["flight","drive"]', "Shanghai", 31.2304, 121.4737,
         "Shanghai", 31.2304, 121.4737, 1, stamp, actor, stamp, actor),
    )
    conn.execute(
        "INSERT INTO customers (id,display_name,normalized_name,lat,lng,"
        "created_at,updated_at,row_version) VALUES (?,?,?,?,?,?,?,1)",
        (customer_id, "Frankfurt Solo", "frankfurt solo", 50.1109, 8.6821,
         stamp, stamp),
    )
    conn.execute(
        """INSERT INTO trip_plan_stops (id,plan_id,customer_id,sequence_no,
           duration_half_days,stay_days,preferred_period,schedule_locked,
           confirmation_status,created_at,created_by,updated_at,updated_by,
           row_version) VALUES (?,?,?,1,1,1,'auto',0,'unconfirmed',?,?,?,?,1)""",
        (stop_id, plan_id, customer_id, stamp, actor, stamp, actor),
    )
    conn.commit()
    service.trip_plan_service.member_repo.add(plan_id, actor, {}, actor)
    service.trip_plan_service.briefing_repo.replace(
        stop_id, normalize_payload({"participants": [{"user_id": actor}]}),
        actor, stamp, None,
    )
    return plan_id, stop_id, actor


def _planned(service, plan_id, stop_id, actor):
    stop = [item for item in service.get_trip_plan(plan_id, actor, "leader")["stops"]
            if item["id"] == stop_id][0]
    return stop["planned_date"], bool(stop.get("planned_time_accepted"))


def check_a_calculated_time_is_not_an_anchor(service, seed) -> None:
    """The calculation's own result must not constrain the next run.

    Generate writes the time it worked out back to the stop. If that counted as
    a time somebody accepted, the first run would pin the visit: move the trip a
    week earlier and it would stay on the date the first run happened to give
    it, which is a route the plan no longer describes.
    """
    plan_id, stop_id, actor = _solo_team_plan(service)
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    first, accepted = _planned(service, plan_id, stop_id, actor)
    assert first == "2026-09-15", first
    assert accepted is False, "the calculation must not mark its own output"

    service.update_trip_plan(
        plan_id,
        {"start_date": "2026-09-07", "departure_window_start": "2026-09-07"},
        actor, "leader",
    )
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    second, _ = _planned(service, plan_id, stop_id, actor)
    assert second == "2026-09-08", (
        f"the visit is frozen on the first run's date instead of moving with "
        f"the trip: {first} -> {second}"
    )


def check_an_accepted_time_is_an_anchor(service, seed) -> None:
    """A time somebody accepted does hold, even when the trip could start sooner."""
    plan_id, stop_id, actor = _solo_team_plan(service)
    stop = [item for item in service.get_trip_plan(plan_id, actor, "leader")["stops"]
            if item["id"] == stop_id][0]
    service.update_trip_stop(
        plan_id, stop_id,
        {"planned_date": "2026-09-25", "planned_start_period": "AM",
         "schedule_locked": False, "planned_time_accepted": True,
         "row_version": stop["row_version"]},
        actor, "leader",
    )
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    kept, accepted = _planned(service, plan_id, stop_id, actor)
    assert accepted is True
    assert kept == "2026-09-25", (
        f"an accepted time must hold its place, but moved to {kept}"
    )
    # And it is no longer offered a suggestion, because it is arranged.
    offered = service.suggest_trip_flexible_visits(plan_id, {}, actor, "leader")
    assert not [
        item for item in offered["suggestions"] if item["stop_id"] == stop_id
    ], offered


def check_generate_does_not_end_flexible_planning(service, seed) -> None:
    """A visit with no agreed time is still suggestible after a Generate."""
    plan_id, stop_id, actor = _solo_team_plan(service)
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    offered = service.suggest_trip_flexible_visits(plan_id, {}, actor, "leader")
    assert [item for item in offered["suggestions"] if item["stop_id"] == stop_id], (
        "generating a route must not make every visit look already arranged: "
        f"{offered}"
    )


def check_apply_a_suggestion(service, seed) -> None:
    """Applying a suggestion plans the visit without agreeing it with anybody."""
    plan_id, actor = seed["plan_id"], seed["actor"]
    stop_id = _flexible_stop(service, seed)

    first = service.suggest_trip_flexible_visits(plan_id, {}, actor, "leader")
    proposed = [
        item for item in first["suggestions"] if item["stop_id"] == stop_id
    ]
    assert proposed, f"the flexible visit was not offered a time: {first}"
    suggestion = proposed[0]
    assert suggestion["date"], suggestion
    assert suggestion["label"] == "Stuttgart Customer"
    assert suggestion["participants"] == [seed["people"]["zhang"]]

    stop = [item for item in service.get_trip_plan(plan_id, actor, "leader")["stops"]
            if item["id"] == stop_id][0]
    plan = service.update_trip_stop(
        plan_id, stop_id,
        {
            "planned_date": suggestion["date"],
            "planned_start_period": suggestion["period"],
            "schedule_locked": False,
            "planned_time_accepted": True,
            "row_version": stop["row_version"],
            "plan_row_version": first["plan_row_version"],
        },
        actor, "leader",
    )
    assert plan, "applying the suggestion did not return the plan"

    applied = [item for item in plan["stops"] if item["id"] == stop_id][0]
    assert applied["planned_date"] == suggestion["date"]
    assert applied["planned_start_period"] == suggestion["period"]
    assert not applied["schedule_locked"], (
        "a time we suggested is not a time the customer agreed to"
    )

    # It is arranged now, so it is not offered again.
    second = service.suggest_trip_flexible_visits(plan_id, {}, actor, "leader")
    assert not [
        item for item in second["suggestions"] if item["stop_id"] == stop_id
    ], f"an applied visit must not be suggested again: {second}"
    # And the next round is worked out from the plan as it now stands.
    assert second["plan_row_version"] > first["plan_row_version"], (
        "the second round must be based on the plan after the first Apply"
    )


def check_a_stale_suggestion_cannot_be_applied(service, seed) -> None:
    """A suggestion from before the plan changed is not quietly applied."""
    plan_id, actor = seed["plan_id"], seed["actor"]
    stop_id = _flexible_stop(service, seed)
    offered = service.suggest_trip_flexible_visits(plan_id, {}, actor, "leader")
    suggestion = [item for item in offered["suggestions"]
                  if item["stop_id"] == stop_id][0]

    # Something else about the plan changes: the suggestion was worked out from
    # the whole plan, so it is no longer the plan being changed.
    service.update_trip_plan(
        plan_id, {"title": "Team Europe (revised)"}, actor, "leader"
    )
    stop = [item for item in service.get_trip_plan(plan_id, actor, "leader")["stops"]
            if item["id"] == stop_id][0]
    try:
        service.update_trip_stop(
            plan_id, stop_id,
            {
                "planned_date": suggestion["date"],
                "planned_start_period": suggestion["period"],
                "schedule_locked": False,
                "planned_time_accepted": True,
                "row_version": stop["row_version"],
                "plan_row_version": offered["plan_row_version"],
            },
            actor, "leader",
        )
    except ConflictError:
        pass
    else:
        raise AssertionError(
            "a suggestion worked out from an older plan must not be applied"
        )
    # An ordinary stop edit does not send a plan version and is unaffected.
    assert service.update_trip_stop(
        plan_id, stop_id, {"visit_purpose": "Ordinary edit",
                           "row_version": stop["row_version"]},
        actor, "leader",
    )


def check_a_route_that_starts_before_the_trip_says_so(service, seed) -> None:
    """An appointment holds its date even when the trip is moved past it.

    The customer's time is a fact, so a trip whose start is pushed beyond it
    keeps planning around the appointment - and then runs before the day it
    claims to begin on. Said nowhere, that route reads as one that fits.
    """
    plan_id, stop_id, actor = _solo_team_plan(service)
    stop = [item for item in service.get_trip_plan(plan_id, actor, "leader")["stops"]
            if item["id"] == stop_id][0]
    service.update_trip_stop(
        plan_id, stop_id,
        {"planned_date": "2026-09-16", "planned_start_period": "AM",
         "schedule_locked": True, "confirmation_status": "confirmed",
         "row_version": stop["row_version"]},
        actor, "leader",
    )
    saved = service.generate_trip_itinerary(
        plan_id, {"start_date": "2026-09-28", "end_date": "2026-10-20"},
        actor, "leader",
    )
    assert saved is not None, "a trip planned around an appointment must save"
    kept, _ = _planned(service, plan_id, stop_id, actor)
    assert kept == "2026-09-16", (
        f"the appointment moved to {kept} when the trip dates changed"
    )
    warnings = saved["itinerary_summary"]["warnings"]
    assert any("before the requested start date" in str(item) for item in warnings), (
        f"a route running before the trip starts must be reported: {warnings}"
    )


def check_overrun_is_a_risk_not_a_refusal(service, seed) -> None:
    """With fixed appointments the dates are what gives, so say it and save it."""
    plan_id, actor = seed["plan_id"], seed["actor"]
    service.update_trip_plan(
        plan_id, {"end_date": "2026-09-16"}, actor, "leader"
    )
    saved = service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    assert saved is not None, "a team trip that runs long must still save"
    kinds = [risk["kind"] for risk in saved["itinerary_summary"]["risks"]]
    assert "member_return_overrun" in kinds, kinds


def main() -> None:
    settings = init_settings(ROOT)
    initialize_database_safely(settings)
    service = ReviewService()
    seed = _seed(service)
    check_a_new_plan_travels_with_its_owner(service, seed)
    check_members_are_team_accounts(service, seed)
    check_missing_endpoints_are_rejected(service, seed)
    check_member_order_is_stable(service, seed)
    check_round_trip(service, seed)
    check_changing_who_attends_invalidates_the_route(service, seed)
    check_changing_a_free_stop_scope_invalidates_the_route(service, seed)
    check_a_calculated_time_is_not_an_anchor(service, seed)
    check_an_accepted_time_is_an_anchor(service, seed)
    check_generate_does_not_end_flexible_planning(service, seed)
    check_apply_a_suggestion(service, seed)
    check_a_stale_suggestion_cannot_be_applied(service, seed)
    check_a_route_that_starts_before_the_trip_says_so(service, seed)
    check_overrun_is_a_risk_not_a_refusal(service, seed)
    close_db()
    print("PASS: team itinerary survives preview, generate and reload")


if __name__ == "__main__":
    main()
