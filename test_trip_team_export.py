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


def _legacy_plan(service, actor):
    """A one-traveller plan with a single customer, planned the old way."""
    conn = get_db()
    stamp = now_iso()
    plan_id, customer_id, stop_id = (generate_uuid() for _ in range(3))
    conn.execute(
        """INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,
           travel_mode,route_order_mode,transport_mode_priority,origin_name,
           origin_lat,origin_lng,destination_name,destination_lat,
           destination_lng,avoid_weekends,status,planning_mode,created_at,
           created_by,updated_at,updated_by,row_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Draft','legacy',?,?,?,?,1)""",
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
    conn.commit()
    return plan_id


def check_legacy_export_is_untouched(service, seed) -> None:
    """A single-traveller plan exports exactly as it did before."""
    actor = seed["actor"]
    plan_id = _legacy_plan(service, actor)
    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    markdown = service.export_trip_plan_markdown(plan_id, actor, "leader")
    check_every_table_is_well_formed(markdown, "legacy markdown")
    assert "## Travel Team" not in markdown
    assert "Schedule State" not in markdown
    assert "Team Aggregate" not in markdown
    assert "- Travel Distance:" in markdown
    legs = [table for table in _tables(markdown) if table[0][0] == "#"]
    assert legs, "the legacy route legs table lost its shape"

    text = service.export_trip_plan_csv(plan_id, actor, "leader")
    header = text.splitlines()[0]
    for column in ("leg_member_id", "attendee_names", "schedule_state"):
        assert column not in header, f"legacy CSV gained a team column: {column}"


def main() -> None:
    initialize_database_safely(init_settings(ROOT))
    service = ReviewService()
    seed = roundtrip._seed(service)
    check_team_markdown(service, seed)
    check_team_csv(service, seed)
    check_daily_execution(service, seed)
    check_legacy_export_is_untouched(service, seed)
    close_db()
    print("PASS: team-aware markdown, CSV and daily execution exports")


if __name__ == "__main__":
    main()
