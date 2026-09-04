"""A team plan exports with the member dimension it was planned on.

Without it a leg from Frankfurt to Munich cannot be attributed to anybody, and
two colleagues' journeys read as one person's itinerary. Legacy single-traveller
exports must be untouched.
"""

from __future__ import annotations

import csv
import io as _io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
os.environ["JPT_DATA_DIR"] = tempfile.mkdtemp(prefix="jpt_team_export_")

from backend.config import init_settings  # noqa: E402
from backend.repositories import close_db  # noqa: E402
from backend.repositories.base import (  # noqa: E402
    generate_uuid,
    get_db,
    now_iso,
)
from backend.services.review_service import ReviewService  # noqa: E402
from backend.startup_upgrade import initialize_database_safely  # noqa: E402
import test_trip_team_roundtrip as roundtrip  # noqa: E402


def _tables(markdown: str) -> list:
    """Every Markdown table as (header cells, separator cells, row count)."""
    tables = []
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("|") or index + 1 >= len(lines):
            continue
        rule = lines[index + 1]
        if not set(rule.replace("|", "").replace(":", "")) <= {"-"}:
            continue
        if not rule.startswith("|"):
            continue
        header = [cell.strip() for cell in line.strip("|").split("|")]
        separator = [cell.strip() for cell in rule.strip("|").split("|")]
        rows = 0
        for row in lines[index + 2:]:
            if not row.startswith("|"):
                break
            rows += 1
        tables.append((header, separator, rows))
    return tables


def _table_after(markdown: str, heading: str) -> list:
    """The cells of the first table under a heading, header row included."""
    body = markdown.split(heading, 1)
    assert len(body) == 2, f"the export has no {heading} section"
    rows = []
    for line in body[1].splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if not set("".join(cells).replace(":", "")) <= {"-"}:
                rows.append(cells)
        elif rows:
            break
    assert rows, f"the table under {heading} is empty"
    return rows


def check_every_table_is_well_formed(markdown: str, label: str) -> None:
    """A table whose rule is a different width than its header renders broken."""
    for header, separator, _ in _tables(markdown):
        assert len(header) == len(separator), (
            f"{label}: table '{header[0]}' has {len(header)} columns and a rule "
            f"of {len(separator)}: {separator}"
        )
        assert "" not in separator, (
            f"{label}: table '{header[0]}' has an empty rule cell: {separator}"
        )


def check_team_markdown(service, seed) -> None:
    plan_id, actor = seed["plan_id"], seed["actor"]
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    markdown = service.export_trip_plan_markdown(plan_id, actor, "leader")
    check_every_table_is_well_formed(markdown, "team markdown")

    assert "## Travel Team" in markdown
    for name in ("Zhang", "Li"):
        assert name in markdown, f"{name} is missing from the export"
    assert "Shenzhen to Shenzhen" in markdown, (
        "each member's own departure and return must be recorded"
    )

    # An aggregate is named as one: two colleagues on one flight count it twice.
    assert "Team Aggregate Travel Distance" in markdown
    assert "\n- Travel Distance:" not in markdown, (
        "an aggregate must not be labelled as if it were the route's length"
    )

    # Every leg is attributable, and shared journeys are not merged away.
    # The Travel Team table also starts with Member, so match the legs table
    # by its shape rather than its first cell.
    legs = [
        table for table in _tables(markdown)
        if table[0][:2] == ["Member", "#"]
    ]
    assert legs, "the route legs table has no Member column"
    leg_headers, _, leg_rows = legs[0]
    assert leg_headers[:2] == ["Member", "#"], leg_headers
    assert leg_rows == len(plan_saved_legs(service, plan_id, actor)), (
        "an export is a record: one row per member's leg, none merged"
    )

    visits = [
        table for table in _tables(markdown) if "Schedule State" in table[0]
    ]
    assert visits, "the visit table has no Schedule State column"
    assert "Attendees" in visits[0][0]
    assert "| Zhang | Confirmed |" in markdown, (
        "a locked visit is recorded as agreed with the customer"
    )
    assert "Zhang / Li" in markdown, (
        "a stop both of them attend must name both"
    )


def plan_saved_legs(service, plan_id, actor):
    return service.get_trip_plan(plan_id, actor, "leader")["legs"]


def check_team_csv(service, seed) -> None:
    plan_id, actor = seed["plan_id"], seed["actor"]
    text = service.export_trip_plan_csv(plan_id, actor, "leader")
    rows = list(csv.DictReader(_io.StringIO(text)))
    for column in ("leg_member_id", "leg_member_name", "attendee_user_ids",
                   "attendee_names", "schedule_state"):
        assert column in rows[0], f"CSV has no {column} column"

    legs = [row for row in rows if row["record_type"] == "leg"]
    assert legs, rows
    assert all(row["leg_member_id"] for row in legs), (
        "every exported leg must say whose it is"
    )
    assert {row["leg_member_name"] for row in legs} == {"Zhang", "Li"}, (
        {row["leg_member_name"] for row in legs}
    )

    stops = [row for row in rows if row["record_type"].endswith("_stop")]
    states = {row["schedule_state"] for row in stops}
    assert states <= {"Confirmed", "Planned", "Calculated", "Unscheduled"}, states
    assert "Confirmed" in states, states
    assert any(" " in row["attendee_user_ids"] for row in stops), (
        "the shared stop must list both attendees"
    )


def check_daily_execution(service, seed) -> None:
    plan_id, actor = seed["plan_id"], seed["actor"]
    markdown = service.export_trip_execution_markdown(
        plan_id, actor, "leader", "2026-09-16"
    )
    check_every_table_is_well_formed(markdown, "team execution")
    timeline = [
        table for table in _tables(markdown)
        if table[0][:2] == ["Member", "Order"]
    ]
    assert timeline, (
        "the daily timeline has no Member column, so a day with two people in "
        "two cities cannot be read"
    )


def _solo_plan(service, actor):
    """A one-traveller plan with a single customer: a team of one."""
    conn = get_db()
    stamp = now_iso()
    plan_id, customer_id, stop_id = (generate_uuid() for _ in range(3))
    conn.execute(
        """INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,
           travel_mode,route_order_mode,transport_mode_priority,origin_name,
           origin_lat,origin_lng,destination_name,destination_lat,
           destination_lng,avoid_weekends,status,planning_mode,created_at,
           created_by,updated_at,updated_by,row_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Draft','team',?,?,?,?,1)""",
        (plan_id, "Solo Europe", actor, "2026-09-14", "2026-09-30", "flight",
         "auto", '["flight","drive"]', "Shanghai", 31.2304, 121.4737,
         "Shanghai", 31.2304, 121.4737, 1, stamp, actor, stamp, actor),
    )
    conn.execute(
        "INSERT INTO customers (id,display_name,normalized_name,lat,lng,"
        "created_at,updated_at,row_version) VALUES (?,?,?,?,?,?,?,1)",
        (customer_id, "Legacy Customer", "legacy customer", 50.1109, 8.6821,
         stamp, stamp),
    )
    conn.execute(
        """INSERT INTO trip_plan_stops (id,plan_id,customer_id,sequence_no,
           duration_half_days,stay_days,preferred_period,schedule_locked,
           confirmation_status,created_at,created_by,updated_at,updated_by,
           row_version) VALUES (?,?,?,1,2,1,'auto',0,'unconfirmed',?,?,?,?,1)""",
        (stop_id, plan_id, customer_id, stamp, actor, stamp, actor),
    )
    # A team of one still has that one person on it.
    conn.execute(
        """INSERT INTO trip_plan_members (id,plan_id,user_id,created_at,
           created_by,updated_at,updated_by,row_version)
           VALUES (?,?,?,?,?,?,?,1)""",
        (generate_uuid(), plan_id, actor, stamp, actor, stamp, actor),
    )
    conn.commit()
    return plan_id


def check_a_lone_traveller_is_named(service, seed) -> None:
    """One person travelling is a team of one, and the file says who."""
    actor = seed["actor"]
    plan_id = _solo_plan(service, actor)
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    name = service.get_trip_plan(plan_id, actor, "leader")["members"][0]["display_name"]
    markdown = service.export_trip_plan_markdown(plan_id, actor, "leader")
    check_every_table_is_well_formed(markdown, "one-traveller markdown")

    team = _table_after(markdown, "## Travel Team")
    assert len(team) == 2, f"one traveller must be one row, got {len(team) - 1}"
    assert team[1][0] == name, f"the travel team names {team[1][0]}, not {name}"

    legs = _table_after(markdown, "## Route Legs")
    assert legs[0][0] == "Member", "route legs must say whose journey each one is"
    assert legs[1:], "the one traveller's route legs are missing"
    assert all(row[0] == name for row in legs[1:]), (
        f"every leg belongs to {name}: {[row[0] for row in legs[1:]]}"
    )

    text = service.export_trip_plan_csv(plan_id, actor, "leader")
    header = text.splitlines()[0].split(",")
    for column in ("leg_member_id", "leg_member_name", "attendee_names",
                   "schedule_state"):
        assert column in header, f"one-traveller CSV dropped {column}"
    rows = [line for line in text.splitlines()[1:] if line.startswith("leg,")]
    assert rows, "the CSV lost the route legs"
    assert all(name in line for line in rows), (
        "a leg row does not name the person who travels it"
    )


def check_every_format_carries_the_team(service, seed) -> None:
    """Excel, HTML and the calendar describe who travelled, not just where.

    They are built from one model that used to look a leg up by its key alone.
    Two colleagues between the same pair of places share that key, so one
    overwrote the other and the file would have stated one member's journey as
    both of theirs - which is why these three refused a team trip outright.
    """
    plan_id, actor = seed["plan_id"], seed["actor"]
    plan = service.get_trip_plan(plan_id, actor, "leader")

    # The collision this guards against is real in an ordinary team trip.
    keys = [leg["leg_key"] for leg in plan["legs"]]
    assert len(keys) != len(set(keys)), (
        "this plan no longer has two members sharing a leg key, so the test is "
        "not exercising what it claims"
    )

    from backend.services.trip_export_model import build_trip_export_model

    model = build_trip_export_model(plan, lambda leg: "")
    travellers = [row["出行人 / Travellers"] for row in model["timeline"]]
    assert any(travellers), "no line of the itinerary says who is on it"
    assert any(" · " in who for who in travellers), (
        f"colleagues travelling together are one line naming both: {travellers}"
    )

    journeys = [(row["出发地 / From"], row["目的地 / To"],
                 row["交通方式 / Mode"], row["出行人 / Travellers"])
                for row in model["legs"]]
    assert len(journeys) == len(set(journeys)), (
        f"a journey is printed more than once: {journeys}"
    )

    names = {member["display_name"] for member in plan["members"]}
    header = " ".join(f"{label} {value}" for label, value in model["metadata"])
    for name in names:
        assert name in header, f"{name} is missing from the document header"

    # And every format actually produces a file for that plan.
    for export in (service.export_trip_plan_xlsx, service.export_trip_plan_html,
                   service.export_trip_plan_ics,
                   service.export_trip_plan_markdown,
                   service.export_trip_plan_csv):
        assert export(plan_id, actor, "leader"), (
            f"{export.__name__} produced nothing for a team trip"
        )


def check_record_formats_state_their_own_terms(service, seed) -> None:
    """Markdown and CSV are records, and say the same thing about the team.

    They print one row per member's leg on purpose: a record is read a row at a
    time and filtered by who, so a shared journey is one row for each person on
    it. What they must not do is disagree with the formal documents about the
    trip itself - the shared travel windows describe the whole team leaving at
    once, which a team trip does not do, and they were removed from the plan.
    """
    plan_id, actor = seed["plan_id"], seed["actor"]

    text = service.export_trip_plan_markdown(plan_id, actor, "leader")
    for banned in ("Departure Window", "Return Window"):
        assert banned not in text, (
            f"{banned} describes the whole team leaving at once, which this "
            "plan does not do; each member's own dates are in the team table"
        )
    assert "## Travel Team" in text, "the record has to say who is going"

    # The plan carries windows, so blanking them is a decision this test can
    # see rather than something the fixture happened to leave empty.
    conn = get_db()
    conn.execute(
        "UPDATE trip_plans SET departure_window_start = ?, "
        "departure_window_end = ?, return_window_start = ?, "
        "return_window_end = ? WHERE id = ?",
        ("2026-09-13T09:00", "2026-09-13T18:00",
         "2026-09-29T09:00", "2026-09-30T18:00", plan_id),
    )
    conn.commit()

    csv_text = service.export_trip_plan_csv(plan_id, actor, "leader")
    rows = list(csv.DictReader(_io.StringIO(csv_text)))
    for field in ("departure_window_start", "departure_window_end",
                  "return_window_start", "return_window_end"):
        assert field in (rows[0] if rows else {}), (
            f"{field} must stay a column so the file shape does not change "
            "between one kind of plan and another"
        )
        assert all(not row[field] for row in rows), (
            f"{field} still carries a value that does not describe this trip"
        )

    # One row per member's leg is the point of a record format, so a journey
    # two of them share is two rows - one for each of them to be found by.
    travelled = [row for row in rows if row.get("leg_member_id")]
    assert travelled, "the record has to say who travelled each leg"
    shared = {}
    for row in travelled:
        shared.setdefault(row["leg_key"], set()).add(row["leg_member_id"])
    assert any(len(members) > 1 for members in shared.values()), (
        "a journey two members share is one row each in a record format, and "
        f"this plan has one: {shared}"
    )


def check_a_lone_traveller_keeps_every_format(service, seed) -> None:
    """A one-traveller plan still downloads in all five formats."""
    actor = seed["actor"]
    plan_id = _solo_plan(service, actor)
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    for export in (service.export_trip_plan_xlsx, service.export_trip_plan_html,
                   service.export_trip_plan_ics,
                   service.export_trip_plan_markdown,
                   service.export_trip_plan_csv):
        assert export(plan_id, actor, "leader"), export.__name__


def main() -> None:
    initialize_database_safely(init_settings(ROOT))
    service = ReviewService()
    seed = roundtrip._seed(service)
    check_team_markdown(service, seed)
    check_team_csv(service, seed)
    check_daily_execution(service, seed)
    check_record_formats_state_their_own_terms(service, seed)
    check_every_format_carries_the_team(service, seed)
    check_a_lone_traveller_keeps_every_format(service, seed)
    check_a_lone_traveller_is_named(service, seed)
    close_db()
    print("PASS: team-aware markdown, CSV and daily execution exports")


if __name__ == "__main__":
    main()
