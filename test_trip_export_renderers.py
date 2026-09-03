"""Focused format checks for the formal trip export renderers."""

from __future__ import annotations

import io
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from backend.services.trip_export_html import render_trip_html
from backend.services.trip_export_ics import render_trip_ics
from backend.services.trip_export_model import (
    TIMELINE_HEADERS, build_trip_export_model)
from backend.services.trip_export_xlsx import render_trip_xlsx

ROOT = Path(__file__).parent


def _fixture():
    schedule = [
        {"slot_key": "2026-09-15:AM", "date": "2026-09-15", "period": "AM", "schedule_index": 1, "item_type": "leg", "source_id": "origin>s1", "sequence_no": 1, "title": "Shanghai → Paris", "half_day_index": 1, "half_day_count": 1, "selected_mode": "flight", "distance_km": 9200, "time_hours": 13, "confirmation_status": None},
        {"slot_key": "2026-09-15:PM", "date": "2026-09-15", "period": "PM", "schedule_index": 2, "item_type": "customer", "source_id": "s1", "sequence_no": 1, "title": "Visit <Alpha>", "half_day_index": 1, "half_day_count": 1, "confirmation_status": "confirmed"},
        {"slot_key": "2026-09-16:AM", "date": "2026-09-16", "period": "AM", "schedule_index": 3, "item_type": "free", "source_id": "f1", "sequence_no": 2, "title": "Hotel & preparation", "half_day_index": 1, "half_day_count": 1, "confirmation_status": "tentative"},
        {"slot_key": "2026-09-29:PM", "date": "2026-09-29", "period": "PM", "schedule_index": 4, "item_type": "leg", "source_id": "f1>destination", "sequence_no": 3, "title": "Rome → Shanghai", "half_day_index": 1, "half_day_count": 1, "selected_mode": "flight", "distance_km": 9000, "time_hours": 12, "confirmation_status": None},
    ]
    plan = {
        "id": "plan-export-1", "title": "Europe <September> Trip",
        "start_date": "2026-09-15", "end_date": "2026-09-30", "region": "EU",
        "owner_name": "Li Liang", "origin_name": "Shanghai",
        "destination_name": "Shanghai", "description": "Customer meetings",
        "itinerary_summary": {"calculated_end_date": "2026-09-29", "calculated_end_period": "PM", "total_distance_km": 18200, "total_travel_hours": 25},
        "stops": [
            {"id": "s1", "stop_kind": "customer", "customer_name": "Alpha", "visit_purpose": "Demo", "notes": "Bring samples", "confirmation_status": "confirmed", "visit_location": {"label": "Alpha Office", "full_address": "1 Rue Test, Paris"}},
            {"id": "f1", "stop_kind": "free", "location_name": "Hotel", "category": "hotel", "visit_purpose": "Rest", "confirmation_status": "tentative", "address": "2 Via Test", "city": "Rome", "country": "Italy"},
        ],
        "legs": [
            {"leg_key": "origin>s1", "sequence_no": 1, "from_label": "Shanghai", "to_label": "Alpha Office", "selected_mode": "flight", "distance_km": 9200, "time_hours": 13, "travel_half_days": 1, "planned_start_date": "2026-09-15", "planned_start_period": "AM"},
            {"leg_key": "f1>destination", "sequence_no": 3, "from_label": "Rome", "to_label": "Shanghai", "selected_mode": "flight", "distance_km": 9000, "time_hours": 12, "travel_half_days": 1, "planned_start_date": "2026-09-29", "planned_start_period": "PM"},
        ],
        "schedule_items": schedule,
    }
    plan["stops"][0]["briefing"] = {
        "timezone": "Europe/Paris",
        "customer_team": [{"name": "Customer Engineer"}],
        "contacts": [{"name": "Kim", "source_contact_id": "hidden-contact"}],
        "participants": [
            {"display_name": "Aydan", "role": "tech", "user_id": "hidden-uuid"}
        ],
        "channel_partner_companions": [
            {"company_name": "Euro Partner", "name": "Anna"}
        ],
        "equipment": [{"kind": "demo", "model": "CW 2000W"}],
        "agenda_items": [{"topic": "Demo & review"}],
    }
    return plan, build_trip_export_model(plan, lambda _: "heuristic_estimate_confirm_manually")


def run() -> None:
    plan, model = _fixture()
    assert model["visits"][0]["PO Laser"].startswith("待补充 / To complete")
    assert ("地区 / Region", "欧洲 / Europe") in model["metadata"]
    assert "hidden-uuid" not in str(model) and "hidden-contact" not in str(model)
    customer_personnel = model["visits"][0]["客户人员 / Customer Personnel"]
    channel_companions = model["visits"][0][
        "渠道代理公司陪同人员（如有） / Channel Partner Companions (if any)"
    ]
    assert "Customer Engineer" in customer_personnel and "Kim" in customer_personnel
    assert "Anna" not in customer_personnel and "Aydan" not in customer_personnel
    assert "Anna" in channel_companions and "Kim" not in channel_companions
    assert "Aydan" not in channel_companions
    plan["stops"][0]["briefing"]["channel_partner_companions"] = []
    empty_partner_model = build_trip_export_model(
        plan, lambda _: "heuristic_estimate_confirm_manually"
    )
    assert empty_partner_model["visits"][0][
        "渠道代理公司陪同人员（如有） / Channel Partner Companions (if any)"
    ] == "无 / None"
    assert model["timeline"][0]["交通 / Mode"] == "航班 / Flight"
    assert model["legs"][0]["确认依据 / Basis"] == "估算，需人工确认 / Estimate, confirm manually"
    assert model["legs"][-1]["目的地 / To"] == "Shanghai"

    xlsx = render_trip_xlsx(model)
    with ZipFile(io.BytesIO(xlsx)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {"xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml", "xl/worksheets/sheet3.xml"} <= names
        for name in names:
            if name.endswith((".xml", ".rels")):
                ElementTree.fromstring(archive.read(name))
        workbook = archive.read("xl/workbook.xml").decode()
        assert all(name in workbook for name in ("拜访计划", "完整日程", "交通行程"))
        assert "Rome" in archive.read("xl/worksheets/sheet3.xml").decode()

    html = render_trip_html(model).decode()
    assert '<html lang="zh-CN">' in html and "window.print()" in html
    assert "https://" not in html and "http://" not in html
    assert "Europe &lt;September&gt; Trip" in html and "Visit &lt;Alpha&gt;" in html

    ics = render_trip_ics(model).decode()
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == len(model["timeline"])
    assert ics.count("DTSTAMP:") == len(model["timeline"])
    assert "DTSTART;VALUE=DATE:20260929" in ics and "[PM]" in ics
    assert "T090000" not in ics and "Rome" in ics and "Shanghai" in ics

    check_a_shared_journey_reads_as_one_line()
    check_each_member_keeps_their_own_leg()
    check_two_lines_differing_only_by_traveller_are_two_events()
    check_members_leaving_from_different_places_are_not_merged()
    check_the_itinerary_is_numbered_in_the_order_it_runs()
    check_an_event_keeps_its_name_when_the_plan_is_edited()
    check_splitting_up_and_travelling_together_keep_their_events()
    check_team_totals_say_they_are_totals_per_person()
    check_same_route_but_different_distance_is_not_one_line()
    check_segments_on_different_days_are_not_one_line()
    check_two_journeys_in_one_half_day_keep_their_order()
    check_two_visits_that_read_alike_stay_two_visits()
    check_two_separate_journeys_that_read_alike_stay_separate()
    check_the_calendar_says_it_is_a_snapshot()
    check_the_shared_copy_keeps_the_whole_journey(plan)
    check_the_shared_copy_carries_no_visit_preparation(plan)
    check_the_shared_workbook_opens_with_the_sheets_it_declares(plan)
    check_the_two_copies_do_not_overwrite_each_other()
    check_the_page_offers_both_copies()
    print("PASS: formal trip XLSX, offline HTML, and all-day ICS renderers")


TEAM_PLAN = {
    "id": "p-team", "title": "Split trip", "planning_mode": "team",
    "members": [
        {"user_id": "a", "display_name": "Ayden"},
        {"user_id": "b", "display_name": "Slluu"},
    ],
    "stops": [{"id": "s1", "customer_name": "VJT", "stop_kind": "customer"}],
    "itinerary_summary": {"member_totals": {}, "risks": []},
}


def _team_plan(**overrides) -> dict:
    from copy import deepcopy
    plan = deepcopy(TEAM_PLAN)
    plan.update(overrides)
    return plan


def check_a_shared_journey_reads_as_one_line() -> None:
    """Colleagues travelling together are one line naming both of them.

    A stored leg is one member's movement, so a journey two people make is two
    rows describing the same travelling. Printed as stored, a two-person trip
    reads as twice the distance it covers.
    """
    plan = _team_plan(
        legs=[
            {"leg_key": "origin>s1", "member_id": member, "selected_mode": "flight",
             "from_label": "Shenzhen", "to_label": "VJT", "sequence_no": 1,
             "distance_km": 9039.5, "time_hours": 16.6}
            for member in ("a", "b")
        ],
        schedule_items=[
            {"member_id": member, "date": "2026-09-03", "period": "AM",
             "item_type": "leg", "source_id": "origin>s1",
             "title": "Shenzhen → VJT", "selected_mode": "flight"}
            for member in ("a", "b")
        ],
    )
    model = build_trip_export_model(plan, lambda leg: "")
    who = [row["出行人 / Travellers"] for row in model["timeline"]]
    assert who == ["Ayden · Slluu"], f"one line naming both: {who}"
    legs = [row["出行人 / Travellers"] for row in model["legs"]]
    assert legs == ["Ayden · Slluu"], f"one journey, printed once: {legs}"


def check_each_member_keeps_their_own_leg() -> None:
    """Two members over the same places by different means keep their own facts.

    Looked up by connection alone, both lines take whichever of the two legs was
    stored last - so one member's document states the other's flight as theirs.
    """
    plan = _team_plan(
        legs=[
            {"leg_key": "origin>s1", "member_id": "a", "selected_mode": "flight",
             "from_label": "Shenzhen", "to_label": "VJT", "sequence_no": 1,
             "distance_km": 9039.5, "time_hours": 16.6},
            {"leg_key": "origin>s1", "member_id": "b", "selected_mode": "drive",
             "from_label": "Shenzhen", "to_label": "VJT", "sequence_no": 1,
             "distance_km": 11200.0, "time_hours": 140.0},
        ],
        schedule_items=[
            {"member_id": "a", "date": "2026-09-03", "period": "AM",
             "item_type": "leg", "source_id": "origin>s1",
             "title": "Shenzhen → VJT", "selected_mode": "flight"},
            {"member_id": "b", "date": "2026-09-03", "period": "AM",
             "item_type": "leg", "source_id": "origin>s1",
             "title": "Shenzhen → VJT", "selected_mode": "drive"},
        ],
    )
    model = build_trip_export_model(plan, lambda leg: "")
    by_traveller = {
        row["出行人 / Travellers"]: row for row in model["timeline"]
    }
    assert set(by_traveller) == {"Ayden", "Slluu"}, (
        f"different means is different travelling, so two lines: {sorted(by_traveller)}"
    )
    assert by_traveller["Ayden"]["距离 / Distance km"] == 9039.5, by_traveller["Ayden"]
    assert by_traveller["Slluu"]["距离 / Distance km"] == 11200.0, (
        "Slluu's line took Ayden's flight as her own journey: "
        f"{by_traveller['Slluu']}"
    )


def _calendar_uids(plan: dict) -> set:
    """The event names a calendar would see, through the production path."""
    from backend.services.trip_export_ics import _uid

    model = build_trip_export_model(plan, lambda leg: "")
    return {_uid(model, row["_key"]) for row in model["calendar"]}


def check_two_lines_differing_only_by_traveller_are_two_events() -> None:
    """Two travellers' places in the itinerary are two events.

    A calendar keeps one event per name, so two given the same one leave the
    reader with whichever was imported last.
    """
    plan = _team_plan(legs=[], schedule_items=[
        {"member_id": member, "date": "2026-09-03", "period": "AM",
         "item_type": "leg", "source_id": "origin>s1", "half_day_index": 1,
         "title": "Shenzhen → VJT", "selected_mode": "flight"}
        for member in ("a", "b")
    ])
    assert len(_calendar_uids(plan)) == 2, (
        "two travellers' journeys were given one name, so a calendar keeps "
        "only one of them"
    )


def check_members_leaving_from_different_places_are_not_merged() -> None:
    """Two members are one row only when every fact about the row agrees.

    Members may leave from their own city, so two of them hold the same
    connection key while travelling different distances from different places.
    Merged on the key alone, one takes the other's journey as their own and the
    document states a departure city the traveller never left from.
    """
    plan = _team_plan(
        legs=[
            {"leg_key": "origin>s1", "member_id": "a", "selected_mode": "flight",
             "from_label": "Shenzhen", "to_label": "VJT", "sequence_no": 1,
             "distance_km": 9000.0, "time_hours": 16.6,
             "planned_start_date": "2026-09-03", "planned_start_period": "AM"},
            {"leg_key": "origin>s1", "member_id": "b", "selected_mode": "flight",
             "from_label": "Guangzhou", "to_label": "VJT", "sequence_no": 1,
             "distance_km": 8800.0, "time_hours": 16.2,
             "planned_start_date": "2026-09-03", "planned_start_period": "AM"},
        ],
        schedule_items=[],
    )
    model = build_trip_export_model(plan, lambda leg: "")
    rows = {row["出发地 / From"]: row for row in model["legs"]}
    assert set(rows) == {"Shenzhen", "Guangzhou"}, (
        "two members leaving from different cities were printed as one "
        f"journey: {[row['出发地 / From'] for row in model['legs']]}"
    )
    assert rows["Guangzhou"]["距离 / Distance km"] == 8800.0, (
        f"Slluu's row took Ayden's distance: {rows['Guangzhou']}"
    )
    assert rows["Shenzhen"]["出行人 / Travellers"] == "Ayden", rows["Shenzhen"]
    assert rows["Guangzhou"]["出行人 / Travellers"] == "Slluu", rows["Guangzhou"]


def check_the_itinerary_is_numbered_in_the_order_it_runs() -> None:
    """The document reads as one trip, in the order it is travelled.

    Team planning records each member's own run of items and numbers them
    within that run, so the stored order is one member's whole trip and then
    the next one's. Printed that way the document is not an itinerary.
    """
    def item(member, date, period, title):
        return {"member_id": member, "date": date, "period": period,
                "item_type": "customer", "source_id": f"s-{title}",
                "title": title, "half_day_index": 1}

    plan = _team_plan(schedule_items=[
        item("a", "2026-09-14", "AM", "VJT"),
        item("a", "2026-09-16", "AM", "SMG"),
        item("b", "2026-09-14", "PM", "PMI"),
        item("b", "2026-09-16", "PM", "ATG"),
    ], legs=[])
    model = build_trip_export_model(plan, lambda leg: "")
    order = [(row["日期 / Date"], row["时段 / Period"]) for row in model["timeline"]]
    assert order == sorted(order), (
        f"the itinerary is in member order, not the order it runs: {order}"
    )
    numbers = [row["序号 / No."] for row in model["timeline"]]
    assert numbers == [1, 2, 3, 4], (
        f"every line has to be numbered, in reading order: {numbers}"
    )


def check_an_event_keeps_its_name_when_the_plan_is_edited() -> None:
    """A calendar re-imported after an edit updates events, never doubles them.

    A calendar keeps one event per name. Built from the date, the title, the
    transport or the people on it, the name changes on exactly the edits that
    make somebody export the file again - so the old event stays and a second
    one appears beside it.
    """
    def plan_with(**changes):
        base = {"member_id": "a", "date": "2026-09-14", "period": "AM",
                "item_type": "customer", "source_id": "stop-1",
                "title": "VJT", "half_day_index": 1, "selected_mode": None}
        return _team_plan(schedule_items=[{**base, **changes}], legs=[])

    original = _calendar_uids(plan_with())
    for what, changes in (
        ("moved to another day", {"date": "2026-09-20"}),
        ("renamed", {"title": "VJT GmbH"}),
        ("travelled to differently", {"selected_mode": "drive"}),
    ):
        assert _calendar_uids(plan_with(**changes)) == original, (
            f"a visit {what} was given a new name, so importing the file again "
            "leaves the old event behind and adds a second one"
        )

    # A different visit is a different event, whatever it looks like.
    assert _calendar_uids(plan_with(source_id="stop-2")) != original, (
        "two different visits share one name"
    )


def check_splitting_up_and_travelling_together_keep_their_events() -> None:
    """Colleagues splitting up or joining does not renumber everybody's events.

    Two members on one flight print as one line; if one switches to driving they
    become two lines, and if they join up again, one line. A name taken from how
    the document happens to group them changes on every one of those, so each
    time the file is imported the previous events stay behind.
    """
    def plan_with(mode_for_b):
        return _team_plan(legs=[], schedule_items=[
            {"member_id": "a", "date": "2026-09-03", "period": "AM",
             "item_type": "leg", "source_id": "origin>s1", "half_day_index": 1,
             "title": "Shenzhen → VJT", "selected_mode": "flight"},
            {"member_id": "b", "date": "2026-09-03", "period": "AM",
             "item_type": "leg", "source_id": "origin>s1", "half_day_index": 1,
             "title": "Shenzhen → VJT", "selected_mode": mode_for_b},
        ])

    together = plan_with("flight")
    apart = plan_with("drive")

    # The document groups them differently either way round.
    merged_rows = build_trip_export_model(together, lambda leg: "")["timeline"]
    split_rows = build_trip_export_model(apart, lambda leg: "")["timeline"]
    assert len(merged_rows) == 1 and len(split_rows) == 2, (
        f"the document must merge one and not the other: "
        f"{len(merged_rows)} vs {len(split_rows)}"
    )

    assert _calendar_uids(together) == _calendar_uids(apart), (
        "splitting up renamed both travellers' events, so importing the "
        "updated file leaves the shared event behind and adds two more"
    )


def check_team_totals_say_they_are_totals_per_person() -> None:
    """The header does not call a per-person sum the length of the route.

    Three colleagues on one 100 km drive add up to 300: that is how much
    travelling the team does, not how far the route goes.
    """
    plan = _team_plan(legs=[], schedule_items=[], itinerary_summary={
        "member_totals": {}, "risks": [],
        "total_distance_km": 300.0, "total_travel_hours": 9.0,
    })
    labels = [label for label, _ in build_trip_export_model(
        plan, lambda leg: "")["metadata"]]
    assert any("累计" in label and "km" in label for label in labels), (
        f"the team's aggregate distance is labelled as a plain total: {labels}"
    )
    assert not any(label.startswith("总里程") for label in labels), labels

    solo = {**plan, "planning_mode": "legacy", "members": []}
    solo_labels = [label for label, _ in build_trip_export_model(
        solo, lambda leg: "")["metadata"]]
    assert any(label.startswith("总里程") for label in solo_labels), (
        f"one traveller's distance is a plain total: {solo_labels}"
    )


def check_same_route_but_different_distance_is_not_one_line() -> None:
    """Two members over the same places with different facts stay two lines.

    Schedule items carry no distance of their own, so a merge decided from them
    compares two empty fields and calls the lines identical - then prints one
    member's leg under both their names.
    """
    def item(member):
        return {"member_id": member, "date": "2026-09-03", "period": "AM",
                "item_type": "leg", "source_id": "origin>s1",
                "half_day_index": 1, "title": "Shenzhen → VJT",
                "selected_mode": "flight"}

    plan = _team_plan(
        schedule_items=[item("a"), item("b")],
        legs=[
            {"leg_key": "origin>s1", "member_id": "a", "selected_mode": "flight",
             "from_label": "Shenzhen", "to_label": "VJT", "sequence_no": 1,
             "distance_km": 9000.0, "time_hours": 16.0},
            {"leg_key": "origin>s1", "member_id": "b", "selected_mode": "flight",
             "from_label": "Shenzhen", "to_label": "VJT", "sequence_no": 1,
             "distance_km": 8800.0, "time_hours": 15.0},
        ],
    )
    rows = build_trip_export_model(plan, lambda leg: "")["timeline"]
    by_distance = {row["距离 / Distance km"]: row for row in rows}
    assert set(by_distance) == {9000.0, 8800.0}, (
        "two members whose legs differ in distance were printed as one line: "
        f"{[(r['出行人 / Travellers'], r['距离 / Distance km']) for r in rows]}"
    )
    assert by_distance[8800.0]["出行人 / Travellers"] == "Slluu", by_distance[8800.0]


def check_segments_on_different_days_are_not_one_line() -> None:
    """Two members flying the same route on different days stay two lines.

    The printed row carries each segment's start and end, so two members whose
    transfers fall on different days describe different travelling - merged,
    one of them is told to be at the airport a day early.
    """
    def leg(member, day):
        return {
            "leg_key": "origin>s1", "member_id": member, "sequence_no": 1,
            "selected_mode": "flight", "from_label": "Shenzhen",
            "to_label": "VJT", "distance_km": 9000.0, "time_hours": 16.0,
            "segments": [{
                "role": "flight", "selected_mode": "flight",
                "from_label": "SZX", "to_label": "CDG",
                "distance_km": 9000.0, "time_hours": 16.0,
                "travel_half_days": 2, "stay_half_days": 0,
                "planned_start_date": day, "planned_start_period": "AM",
                "planned_end_date": day, "planned_end_period": "PM",
            }],
        }

    plan = _team_plan(schedule_items=[],
                      legs=[leg("a", "2026-09-03"), leg("b", "2026-09-04")])
    rows = build_trip_export_model(plan, lambda leg: "")["legs"]
    starts = {row["开始 / Start"] for row in rows}
    assert len(rows) == 2 and len(starts) == 2, (
        "two members flying on different days were printed as one journey: "
        f"{[(r['出行人 / Travellers'], r['开始 / Start']) for r in rows]}"
    )


def check_two_journeys_in_one_half_day_keep_their_order() -> None:
    """The drive to the airport comes before the flight it is for.

    Two connections can share a half-day. Ordered by title after that, the
    itinerary reads them alphabetically - which reverses a transfer and the
    flight that follows it as often as not.
    """
    def item(order, title):
        return {"member_id": "a", "date": "2026-09-03", "period": "AM",
                "item_type": "leg", "source_id": f"leg-{order}",
                "half_day_index": 1, "lane_order": order, "title": title,
                "selected_mode": "drive"}

    plan = _team_plan(legs=[], schedule_items=[
        item(1, "Hotel → Airport"),
        item(2, "Airport → Frankfurt"),
    ])
    titles = [row["事项 / Item"]
              for row in build_trip_export_model(plan, lambda leg: "")["timeline"]]
    assert titles == ["Hotel → Airport", "Airport → Frankfurt"], (
        f"the itinerary reversed two journeys inside one half-day: {titles}"
    )


def check_two_visits_that_read_alike_stay_two_visits() -> None:
    """Two pieces of work are two lines, however alike they read.

    Comparing only what is printed loses which record a line came from. Two
    separate visits that fall on the same morning at customers of the same name
    then become one line naming both travellers - stating that they attended
    together something they each did on their own.
    """
    def visit(member, stop_id):
        return {"member_id": member, "date": "2026-09-03", "period": "AM",
                "item_type": "customer", "source_id": stop_id,
                "half_day_index": 1, "title": "VJT", "lane_order": 1}

    plan = _team_plan(
        stops=[{"id": "s1", "customer_name": "VJT", "stop_kind": "customer"},
               {"id": "s2", "customer_name": "VJT", "stop_kind": "customer"}],
        schedule_items=[visit("a", "s1"), visit("b", "s2")],
        legs=[],
    )
    rows = build_trip_export_model(plan, lambda leg: "")["timeline"]
    who = sorted(row["出行人 / Travellers"] for row in rows)
    assert who == ["Ayden", "Slluu"], (
        "two separate visits were printed as one attended together: "
        f"{[(r['序号 / No.'], r['出行人 / Travellers']) for r in rows]}"
    )


def check_two_separate_journeys_that_read_alike_stay_separate() -> None:
    """Two connections are two rows even when every printed fact matches.

    A leg key is the connection the plan recorded. Two of them that happen to
    describe the same places, distance and hours are still two journeys, and
    printing them as one hides half the travelling.
    """
    def leg(member, key):
        return {"leg_key": key, "member_id": member, "sequence_no": 1,
                "selected_mode": "drive", "from_label": "Hotel",
                "to_label": "Airport", "distance_km": 30.0, "time_hours": 0.6}

    plan = _team_plan(schedule_items=[],
                      legs=[leg("a", "s1>s2"), leg("b", "s3>s4")])
    rows = build_trip_export_model(plan, lambda leg: "")["legs"]
    assert len(rows) == 2, (
        "two different connections were printed as one journey: "
        f"{[r['出行人 / Travellers'] for r in rows]}"
    )


def check_the_calendar_says_it_is_a_snapshot() -> None:
    """The file states what it can and cannot do, and so does the button.

    An event keeps its name when a visit moves, is renamed, is travelled to
    differently, or when colleagues split up - so importing again updates those.
    A visit deleted, shortened or reassigned leaves behind the event it used to
    have, and nothing in a file of current events can ask for its removal. The
    reader is told to clear the previous import rather than promised otherwise.
    """
    from backend.services.trip_export_ics import SNAPSHOT_NOTE, render_trip_ics

    plan = _team_plan(legs=[], schedule_items=[
        {"member_id": "a", "date": "2026-09-03", "period": "AM",
         "item_type": "customer", "source_id": "s1", "half_day_index": 1,
         "title": "VJT", "lane_order": 1},
    ])
    model = build_trip_export_model(plan, lambda leg: "")
    text = render_trip_ics(model).decode()
    assert "X-WR-CALDESC:" in text, (
        "the file has to carry what it is, since whoever receives it over chat "
        "has nothing else to go on"
    )
    for language in ("删除上次导入", "remove the calendar imported last time"):
        assert language in SNAPSHOT_NOTE, f"the note must say it in {language!r}"

    # Every current line is in the file: a snapshot is only usable if complete.
    assert text.count("BEGIN:VEVENT") == len(model["calendar"]), (
        "a snapshot that leaves lines out is not a snapshot"
    )

    # And the button says the same thing, where the reader is standing.
    page = ROOT.joinpath("frontend", "index.html").read_text(encoding="utf-8")
    assert "delete the calendar you imported last time" in page, (
        "the calendar download must say what importing again does before it is "
        "clicked, not only inside the file"
    )


def _shared(plan: dict) -> dict:
    return build_trip_export_model(
        plan, lambda _: "heuristic_estimate_confirm_manually", variant="shared"
    )


ARRANGEMENT = tuple(
    header for header in TIMELINE_HEADERS
    if header not in ("目的 / Purpose", "备注 / Notes")
)


def check_the_shared_copy_keeps_the_whole_journey(plan: dict) -> None:
    """The copy the team confirms has to show the same trip, not less of it.

    This is the version circulated for everyone to agree to, so a day, a
    journey or a mileage total that only exists in the other copy would have
    people confirming a trip nobody is taking. Only what a visit is for and
    what was noted about it may differ between the two.
    """
    full = build_trip_export_model(
        plan, lambda _: "heuristic_estimate_confirm_manually"
    )
    shared = _shared(plan)
    assert len(shared["timeline"]) == len(full["timeline"]), (
        "the shared copy dropped or added days: "
        f"{len(shared['timeline'])} rows against {len(full['timeline'])}"
    )
    for shared_row, full_row in zip(shared["timeline"], full["timeline"]):
        for header in ARRANGEMENT:
            assert shared_row[header] == full_row[header], (
                f"the shared copy changed {header}: "
                f"{shared_row[header]!r} against {full_row[header]!r}"
            )
    assert shared["legs"] == full["legs"], "the shared copy changed the journeys"
    assert shared["overview"] == full["overview"], (
        "the shared copy changed the trip summary, so the two copies would "
        "disagree about dates, mileage or who is going"
    )
    assert len(shared["calendar"]) == len(full["calendar"])
    for shared_row, full_row in zip(shared["calendar"], full["calendar"]):
        assert shared_row["_key"] == full_row["_key"], (
            "the calendar entries no longer line up, so the same day would be "
            "imported twice under two names"
        )
    assert shared["title"] == full["title"] and shared["plan_id"] == full["plan_id"]


def check_the_shared_copy_carries_no_visit_preparation(plan: dict) -> None:
    """Nothing prepared for a visit reaches the copy anyone may forward.

    Not only the visit table: names, phone numbers, equipment and topics must
    not surface anywhere else in the workbook or the page either.
    """
    shared = _shared(plan)
    assert shared["visits"] == [], "the shared copy still carries the visit table"

    # Nor on the itinerary itself: what a customer visit is for, and what was
    # noted about it, are prepared for that visit.
    stops = {stop["id"]: stop for stop in plan["stops"]}
    customer = next(stop for stop in plan["stops"] if stop["stop_kind"] == "customer")
    assert customer.get("visit_purpose") and customer.get("notes"), (
        "the fixture has to prepare a purpose and a note for this to prove "
        "anything"
    )
    for row in shared["timeline"]:
        if row["类型 / Type"].startswith("客户拜访"):
            assert not row["目的 / Purpose"], (
                f"the visit still says what it is for: {row['目的 / Purpose']!r}"
            )
            assert not row["备注 / Notes"], (
                f"the visit still carries its note: {row['备注 / Notes']!r}"
            )
    kept = [row["目的 / Purpose"] for row in shared["timeline"]
            if row["类型 / Type"].startswith("个人安排")]
    assert any(kept), (
        "a hotel or a rest day says what the trip is doing, not what will be "
        "discussed, so it keeps its purpose"
    )

    calendar = render_trip_ics(shared).decode()
    for text in (customer["visit_purpose"], customer["notes"]):
        assert text not in calendar, (
            f"{text!r} was prepared for a visit and reached the calendar, which "
            "is imported and forwarded on its own"
        )

    full = build_trip_export_model(
        plan, lambda _: "heuristic_estimate_confirm_manually"
    )
    prepared = set()
    for row in full["visits"]:
        for header, value in row.items():
            if header in (
                "No.", "Company Name", "Full Address", "Recommended Visit Date",
            ):
                continue  # who, where and when is what the team confirms
            prepared.update(
                part.strip() for part in str(value).replace("|", "\n").split("\n")
                if len(part.strip()) > 3 and "待补充" not in part
            )
    assert prepared, "the fixture has to prepare something for this to prove anything"

    xlsx = render_trip_xlsx(shared)
    with ZipFile(io.BytesIO(xlsx)) as archive:
        printed = "".join(
            archive.read(name).decode()
            for name in archive.namelist() if name.endswith(".xml")
        )
    page = render_trip_html(shared).decode()
    for text in prepared:
        assert text not in printed, f"{text!r} was prepared for a visit and reached the workbook"
        assert text not in page, f"{text!r} was prepared for a visit and reached the page"


def check_the_shared_workbook_opens_with_the_sheets_it_declares(plan: dict) -> None:
    """A workbook that names more sheets than it holds will not open at all."""
    shared = _shared(plan)
    with ZipFile(io.BytesIO(render_trip_xlsx(shared))) as archive:
        names = archive.namelist()
        sheets = [name for name in names if name.startswith("xl/worksheets/sheet")]
        workbook = archive.read("xl/workbook.xml").decode()
        relationships = archive.read("xl/_rels/workbook.xml.rels").decode()
        content_types = archive.read("[Content_Types].xml").decode()
    declared = ElementTree.fromstring(workbook).iter()
    titles = [
        element.get("name") for element in declared
        if element.tag.endswith("}sheet")
    ]
    assert titles == ["行程总览", "完整日程", "交通行程"], (
        f"the shared workbook declares {titles}"
    )
    assert len(sheets) == len(titles), (
        f"{len(titles)} sheets are declared but {len(sheets)} are in the file"
    )
    assert "拜访计划" not in workbook, "the visit sheet is still named in the workbook"
    for index in range(1, len(titles) + 1):
        assert f"sheet{index}.xml" in relationships, f"sheet{index} has no relationship"
        assert f"/xl/worksheets/sheet{index}.xml" in content_types, (
            f"sheet{index} is missing from the content types"
        )
    assert f"sheet{len(titles) + 1}.xml" not in relationships, (
        "the workbook still points at a sheet that is not in the file"
    )

    # And it survives being opened rather than only inspected: the reader
    # resolves every declared sheet through its relationship and parses it.
    from backend.services.importing.workbook import read_workbook

    book = read_workbook(render_trip_xlsx(shared), "trip-shared.xlsx")
    assert list(book.sheets) == titles, f"the reader found {list(book.sheets)}"
    for name, sheet in book.sheets.items():
        assert sheet.rows, f"{name} opened empty"



def check_the_two_copies_do_not_overwrite_each_other() -> None:
    """Both copies land in the same download folder, so they need two names."""
    from backend.routers.review import _formal_export_response

    names = {}
    for variant in ("shared", "full"):
        response = _formal_export_response(
            b"x", "plan-1", "xlsx", "application/octet-stream", variant
        )
        names[variant] = response.headers["content-disposition"]
    assert names["shared"] != names["full"], (
        f"both copies download as {names['full']}, so the second one silently "
        "becomes a duplicate and the wrong file gets forwarded"
    )
    assert "shared" in names["shared"] and "shared" not in names["full"]


def check_the_page_offers_both_copies() -> None:
    """The reader chooses between them before downloading, by what they are."""
    page = ROOT.joinpath("frontend", "index.html").read_text(encoding="utf-8")
    assert "exportCurrentTripPlan('xlsx', 'shared')" in page, (
        "there is no way to download the shared itinerary from the page"
    )
    assert "exportCurrentTripPlan('xlsx', 'full')" in page, (
        "the copy with visit preparation is no longer reachable"
    )
    assert "Shared itinerary" in page and "visit preparation" in page, (
        "the two downloads have to say which is which before being clicked"
    )
    actions = ROOT.joinpath(
        "frontend", "js", "modules", "trip-export-actions.js"
    ).read_text(encoding="utf-8")
    assert "download(format, variant" in actions, (
        "the download never passes the chosen version on"
    )
    client = ROOT.joinpath("frontend", "js", "api-client.js").read_text(encoding="utf-8")
    assert "variant=${encodeURIComponent(variant)}" in client, (
        "the request does not ask the server for the chosen version"
    )


if __name__ == "__main__":
    run()
