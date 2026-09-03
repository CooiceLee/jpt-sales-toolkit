"""Shared read model for distributable trip-plan exports."""

from __future__ import annotations

from typing import Callable

from . import trip_team_export as team_export
from .trip_export_labels import (
    product_basis, product_category, product_mode, product_region, product_status,
)
from .trip_export_visit import (
    CHANNEL_PARTNER_COMPANIONS_HEADER,
    CUSTOMER_PERSONNEL_HEADER,
    formal_visit_row,
)


OVERVIEW_HEADERS = ["项目 / Item", "内容 / Detail"]
# What a shared itinerary is for: everybody on the trip reading the same
# arrangement and confirming it. What each visit is prepared for, and what came
# of it, belongs to the people making the visit and travels separately.
SHARED_VARIANT = "shared"
FULL_VARIANT = "full"

VISIT_HEADERS = [
    "No.", "Company Name", "Full Address", "Recommended Visit Date",
    "Demo Laser", "PO Laser", "Other Equipment", CUSTOMER_PERSONNEL_HEADER,
    CHANNEL_PARTNER_COMPANIONS_HEADER, "Visiting topic",
]
TIMELINE_HEADERS = [
    "序号 / No.", "日期 / Date", "时段 / Period", "出行人 / Travellers", "类型 / Type",
    "分类 / Category", "地点 / Place", "地址 / Address", "事项 / Item", "目的 / Purpose",
    "交通 / Mode", "距离 / Distance km", "时长 / Time hours",
    "确认状态 / Status", "备注 / Notes",
]
LEG_HEADERS = [
    "序号 / No.", "出行人 / Travellers", "出发地 / From", "目的地 / To", "交通方式 / Mode",
    "距离 / Distance km", "预计时长 / Time hours", "开始 / Start",
    "结束 / End", "占用半天数 / Half-days", "确认依据 / Basis",
    "备注 / Notes",
]


def _text(value) -> str:
    return "" if value is None else str(value)


def _first(*values):
    return next((value for value in values if value is not None), None)


def _missing_to_product_text(value) -> str:
    text = _text(value)
    if text.startswith("MISSING:"):
        return f"待补充 / To complete: {text.split(':', 1)[1].strip()}"
    return text


def _address(stop: dict) -> str:
    location = stop.get("visit_location") or {}
    if location.get("full_address"):
        return _text(location["full_address"])
    return ", ".join(
        _text(location.get(key, stop.get(key)))
        for key in ("address", "city", "postal_code", "country")
        if location.get(key, stop.get(key))
    )


def _slot(value: dict, prefix: str = "planned_start") -> str:
    return " ".join(
        _text(value.get(key))
        for key in (f"{prefix}_date", f"{prefix}_period")
        if value.get(key)
    )


def _travellers(plan: dict, member_ids) -> str:
    """Who is on this line, by name.

    Empty on a single-traveller plan: there is one person and the document is
    already about them, so a column repeating their name on every line says
    nothing.
    """
    names = [team_export.member_name(plan, user_id) for user_id in member_ids]
    return " · ".join(name for name in names if name)


PERIOD_ORDER = {"AM": 0, "PM": 1}
MERGE_IGNORED = ("序号 / No.", "出行人 / Travellers")


def _same_row(row: dict) -> tuple:
    """Everything a printed line states, except its number and the names on it.

    Deciding this from the inputs instead - a connection key, a date, a mode -
    has been wrong twice: schedule items carry no distance, and segment times
    are printed but were not compared. The row is the only complete description
    of what the reader will see.
    """
    return tuple(
        (header, _text(row.get(header)))
        for header in row
        if header not in MERGE_IGNORED
    )


def _merge_rows(built: list[tuple[str, dict, list]]) -> list[tuple[dict, list]]:
    """Lines from one business record that say the same thing become one.

    Both halves are needed. The record - a visit, a connection, a segment of one
    - is what proves two lines are the same piece of work: two different visits
    that happen to fall on the same morning at customers of the same name are
    not one visit, however alike they read. The printed row is what proves they
    can safely share a line: same record but different distances, times or
    airports is two people doing that work differently.
    """
    merged: dict = {}
    for source, row, member_ids in built:
        key = (source, _same_row(row))
        entry = merged.get(key)
        if entry is None:
            merged[key] = (row, list(member_ids))
            continue
        for member in member_ids:
            if member not in entry[1]:
                entry[1].append(member)
    return list(merged.values())


def _when(item: dict) -> tuple:
    """When a line happens, for putting the itinerary in the order it runs.

    Team planning records each member's own run of items and numbers them
    within that run, so the stored order is one member's day after another.
    A document is read as one trip, in the order it is travelled - and inside
    one half-day, in the order that member actually travels it. Two connections
    can share a half-day: the drive to the airport and the flight that follows.
    """
    return (
        _text(item.get("date")),
        PERIOD_ORDER.get(item.get("period"), 2),
        int(item.get("lane_order") or item.get("schedule_index") or 0),
        int(item.get("half_day_index") or 0),
        0 if item.get("item_type") == "leg" else 1,
        _text(item.get("title")),
    )


def _leg_for(plan: dict, item: dict) -> dict:
    """The stored leg one travel line came from.

    Keyed by who travelled it as well as which connection: in team planning two
    colleagues cover the same pair of places, and a lookup by connection alone
    returns whichever of them was stored last.
    """
    base = str(item.get("source_id") or "").split("#")[0]
    member = item.get("member_id")
    for leg in plan.get("legs") or []:
        if leg.get("leg_key") == base and leg.get("member_id") == member:
            return leg
    for leg in plan.get("legs") or []:
        if leg.get("leg_key") == base:
            return leg
    return {}


def _calendar_key(item: dict) -> str:
    """The lasting name of one traveller's place in the itinerary.

    A calendar keeps one event per name, so re-importing an updated file has to
    land on the events already there. The name is what the plan records - the
    visit or the connection, which half-day of it, and whose - and never a date,
    a title, a mode or a person's display name: editing any of those is the
    ordinary reason to export again. Naming it per traveller also survives two
    colleagues splitting up or starting to travel together, which changes how
    the printed document groups them but not whose day it is.
    """
    return "#".join((
        str(item.get("source_id") or ""),
        str(int(item.get("half_day_index") or 0)),
        str(item.get("member_id") or ""),
    ))


TYPE_LABELS = {
    "customer": "客户拜访 / Customer visit",
    "free": "个人安排 / Personal stop",
    "leg": "交通 / Travel",
    "airport": "机场等待 / Airport wait",
}


def _timeline_row(
    plan: dict, stops: dict, item: dict, travellers: str,
    variant: str = FULL_VARIANT,
) -> dict:
    """One traveller's line of the itinerary, exactly as it will be read.

    What a customer visit is *for* and what was noted about it are prepared
    for that visit, so the copy meant to be forwarded leaves them out. A hotel,
    an airport wait or a rest day keeps both: they say what the trip is doing,
    not what will be discussed. Notes written against a connection stay too.
    """
    stop = stops.get(item.get("source_id"), {})
    prepared = variant == SHARED_VARIANT and stop.get("stop_kind") == "customer"
    leg = _leg_for(plan, item)
    kind = item.get("item_type")
    place = (
        (stop.get("visit_location") or {}).get("label")
        or stop.get("location_name") or stop.get("customer_name")
        or item.get("title")
    )
    return dict(zip(TIMELINE_HEADERS, (
        None, item.get("date"), item.get("period"), travellers,
        TYPE_LABELS.get(kind, _text(kind)), product_category(stop.get("category")),
        place, _address(stop),
        item.get("title"), None if prepared else stop.get("visit_purpose"),
        product_mode(item.get("selected_mode") or leg.get("selected_mode") or leg.get("mode")),
        _first(item.get("distance_km"), leg.get("distance_km")),
        _first(item.get("time_hours"), leg.get("time_hours")),
        product_status(item.get("confirmation_status")),
        leg.get("notes") if prepared else (stop.get("notes") or leg.get("notes")),
    )))


def _timeline(plan: dict, variant: str = FULL_VARIANT) -> tuple[list[dict], list[dict]]:
    """The itinerary as it is printed, and as a calendar reads it.

    Each traveller's line is built in full first. Two lines become one only
    when everything printed on them agrees - the alternative, guessing from the
    inputs which lines describe the same travelling, has twice missed a field
    that is printed and produced one member's journey under both their names.

    The calendar keeps one entry per traveller whatever the document does with
    them, so an event keeps its name when colleagues split up or start
    travelling together.
    """
    stops = {stop.get("id"): stop for stop in plan.get("stops") or []}
    ordered = sorted(plan.get("schedule_items") or [], key=_when)
    built = []
    calendar = []
    for item in ordered:
        member = item.get("member_id")
        row = _timeline_row(plan, stops, item, _travellers(plan, [member]), variant)
        built.append((
            "|".join((
                _text(item.get("item_type")), _text(item.get("source_id")),
                _text(item.get("half_day_index")),
            )),
            row, [member],
        ))
        calendar.append({**row, "_key": _calendar_key(item)})
    rows = []
    for number, (row, member_ids) in enumerate(_merge_rows(built), start=1):
        rows.append({
            **row,
            "序号 / No.": number,
            "出行人 / Travellers": _travellers(plan, member_ids),
        })
    return rows, calendar


def _leg_lines(leg: dict, confirmation: Callable[[dict], str]) -> list[tuple]:
    """The printed lines one stored connection produces.

    A flown connection is distributed as the movements it is made of, so a
    printed itinerary shows the transfers to and from the airport too.
    """
    segments = leg.get("segments") or []
    if segments:
        return [
            (
                leg.get("sequence_no"), None, segment.get("from_label"),
                segment.get("to_label"),
                product_mode(segment.get("selected_mode")),
                segment.get("distance_km"), segment.get("time_hours"),
                _slot(segment), _slot(segment, "planned_end"),
                segment.get("travel_half_days"),
                product_basis(confirmation(leg)), leg.get("notes"),
            )
            for segment in segments
        ]
    return [(
        leg.get("sequence_no"), None,
        leg.get("from_label") or leg.get("from"),
        leg.get("to_label") or leg.get("to"),
        product_mode(leg.get("selected_mode") or leg.get("mode")), leg.get("distance_km"),
        leg.get("time_hours"), _slot(leg), _slot(leg, "planned_end"),
        leg.get("travel_half_days"), product_basis(confirmation(leg)), leg.get("notes"),
    )]


def _leg_rows(plan: dict, confirmation: Callable[[dict], str]) -> list[dict]:
    """Every journey once, naming everybody travelling it.

    A stored leg is one member's movement, so colleagues travelling together
    are several legs describing one journey. Each member's lines are built in
    full and then merged where everything printed on them agrees, so a
    difference in any printed fact - a different departure city, a segment on
    another day, another confirmation basis - keeps them apart.
    """
    built = []
    for leg in plan.get("legs") or []:
        for index, line in enumerate(_leg_lines(leg, confirmation)):
            built.append((
                f"{leg.get('leg_key')}|{index}",
                dict(zip(LEG_HEADERS, line)), [leg.get("member_id")],
            ))
    return [
        {**row, "出行人 / Travellers": _travellers(plan, member_ids)}
        for row, member_ids in _merge_rows(built)
    ]


def _team_rows(plan: dict, summary: dict) -> list[tuple]:
    """One line per traveller: where they go, how far, and when they are back.

    A team trip is not described by one departure point and one return date, so
    the header carries each member's own. Written as plain label and value, not
    as the Markdown table the text exports use, because this block is also read
    as spreadsheet cells and as an HTML definition list.
    """
    totals = summary.get("member_totals") or {}
    rows = []
    for member in plan.get("members") or []:
        total = totals.get(member.get("user_id")) or {}
        back = " ".join(_text(value) for value in (
            total.get("calculated_end_date"), total.get("calculated_end_period"),
        ) if value)
        detail = " · ".join(part for part in (
            team_export.endpoints(plan, member),
            f"{total['distance_km']} km" if total.get("distance_km") is not None else "",
            f"回程 / Back {back}" if back else "",
            "" if total.get("route_complete", True) else "路线未完整 / Route incomplete",
        ) if part)
        rows.append((
            f"出行人 / Traveller · {member.get('display_name') or member.get('user_id')}",
            detail,
        ))
    for risk in summary.get("risks") or []:
        rows.append((
            "需确认 / To confirm",
            " · ".join(_text(value) for value in (
                risk.get("kind"),
                team_export.member_name(plan, risk.get("member_id") or risk.get("user_id")),
                risk.get("date") or risk.get("departure_date"),
                risk.get("deadline"),
            ) if value),
        ))
    return rows


def build_trip_export_model(
    plan: dict,
    leg_confirmation: Callable[[dict], str],
    variant: str = FULL_VARIANT,
) -> dict:
    """Build one format-neutral export model from an authorized fresh plan.

    The shared variant carries the arrangement - who goes where, when, and how -
    and nothing about what each visit is prepared for or what came of it. It is
    the file that circulates so the whole team can confirm the trip.
    """
    visits = []
    customer_stops = [
        stop for stop in plan.get("stops") or [] if stop.get("stop_kind") != "free"
    ]
    for number, stop in enumerate(customer_stops, start=1):
        row = formal_visit_row(stop, number)
        visits.append({key: _missing_to_product_text(row.get(key)) for key in VISIT_HEADERS})
    summary = plan.get("itinerary_summary") or {}
    metadata = [
        ("行程名称 / Trip", plan.get("title")),
        ("日期 / Date", f"{plan.get('start_date') or '-'} — {plan.get('end_date') or '-'}"),
        ("地区 / Region", product_region(plan.get("region"))),
        ("负责人 / Owner", plan.get("owner_name")),
        ("出发 / Origin", plan.get("origin_name")),
        ("出发窗口 / Departure", f"{plan.get('departure_window_start') or '-'} — {plan.get('departure_window_end') or '-'}"),
        ("返回 / Return", plan.get("destination_name")),
        ("返回窗口 / Return window", f"{plan.get('return_window_start') or '-'} — {plan.get('return_window_end') or '-'}"),
        ("预计结束 / Calculated end", " ".join(_text(value) for value in (summary.get("calculated_end_date"), summary.get("calculated_end_period")) if value)),
        # On a team trip these are the sum over members: three colleagues on
        # one 100 km drive add up to 300. That is how much travelling the team
        # does, not how long the route is, and the label has to say which.
        (
            "团队累计里程 / Team aggregate km" if team_export.is_team(plan)
            else "总里程 / Distance km",
            summary.get("total_distance_km"),
        ),
        (
            "团队累计交通时长 / Team aggregate hours"
            if team_export.is_team(plan) else "预计交通时长 / Travel hours",
            summary.get("total_travel_hours"),
        ),
        ("行程说明 / Notes", plan.get("description")),
    ]
    if team_export.is_team(plan):
        # The two travel windows describe the whole team leaving at once, which
        # a team trip does not do - each member's own dates are below instead.
        metadata = [row for row in metadata
                    if not row[0].startswith(("出发窗口", "返回窗口"))]
        metadata.extend(_team_rows(plan, summary))
    timeline, calendar = _timeline(plan, variant)
    return {
        "plan_id": plan.get("id"), "title": plan.get("title") or "出差计划",
        "variant": SHARED_VARIANT if variant == SHARED_VARIANT else FULL_VARIANT,
        "metadata": metadata,
        # The same header as a table, so a workbook can carry it on a sheet of
        # its own rather than on top of whichever sheet happens to come first.
        "overview": [
            dict(zip(OVERVIEW_HEADERS, (label, _text(value))))
            for label, value in metadata
        ],
        "visits": [] if variant == SHARED_VARIANT else visits,
        "timeline": timeline,
        # One entry per traveller, each carrying the lasting name of their place
        # in the itinerary, for formats that must recognise it again next time.
        "calendar": calendar,
        "legs": _leg_rows(plan, leg_confirmation),
    }
