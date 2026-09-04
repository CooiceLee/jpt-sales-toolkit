"""Turn a saved team trip plan into a calculated team itinerary.

This is the layer between what the user stored and what the multi-cursor core
computes: it reads the appointments and the people from the plan, hands them to
`plan_team_itinerary`, and folds the per-member result back into the one shape
the API and the database already speak.
"""

from __future__ import annotations

from ..repositories.base import now_iso
from .trip_leg_contract import validate_stop_order
from .trip_team_schedule import TeamEvent, plan_team_itinerary
from .trip_team_suggestions import _workday


def _named_attendees(stop: dict) -> tuple:
    """Who this stop says is at it, whether or not they are on the trip."""
    if (stop.get("stop_kind") or "customer") == "free":
        return tuple(stop.get("participant_user_ids") or ())
    briefing = stop.get("briefing") or {}
    return tuple(
        row["user_id"] for row in briefing.get("participants") or []
        if row.get("user_id")
    )


def _attendees(stop: dict, team: tuple) -> tuple:
    """Who from the team is at this stop. Empty means the whole team.

    People are named on a visit long before anyone decides who is travelling,
    and the two lists drift: a colleague comes off the trip, or a plan made for
    one traveller names somebody who was never on it. Keeping only the named
    people would then leave the visit assigned to nobody - and a visit assigned
    to nobody is left out of the itinerary entirely, without a word, which is
    how a customer disappears from a trip that was planned around them.

    So it is whoever is both named and travelling. When that is nobody, the
    whole team attends and the caller is handed something to say about it.
    """
    named = _named_attendees(stop)
    if not named:
        return ()
    return tuple(user for user in named if user in team)


def _saved_slot(core, stop: dict) -> tuple | None:
    """The time saved on this stop, whatever it means."""
    day = core._parse_date(stop.get("planned_date"))
    period = stop.get("planned_start_period")
    if not day or period not in ("AM", "PM"):
        return None
    return day, period


def _is_locked(stop: dict, override: dict) -> bool:
    """Whether this visit is an appointment, as of this request.

    Marked on the route form and sent with it: read only from the saved stop,
    a visit the user just marked as agreed is planned as though it were still
    ours to move.
    """
    return bool(override.get("locked", bool(stop.get("schedule_locked"))))


def _preferred_period(stop: dict, override: dict) -> str:
    """Whether this visit should be called on in the morning or the afternoon.

    A wish, not an appointment: it decides which half of the day the visit
    starts in when nothing has been agreed with the customer.
    """
    period = override.get(
        "preferred_period", stop.get("preferred_period") or "auto"
    )
    if period not in {"auto", "AM", "PM"}:
        raise ValueError("Visit time preference must be Automatic, AM, or PM")
    return period


def _slots_of(core, stop: dict, override: dict) -> tuple:
    """What is agreed with the customer, and what we merely decided.

    A locked visit is an appointment and becomes a fact the plan is built
    around. An unlocked visit whose time somebody accepted is a plan of ours and
    has to be honoured, or applying a suggestion would appear to work and then
    be forgotten by the next calculation. A time the last calculation merely
    produced is neither: it is output, and must not constrain the next run.
    """
    saved = _saved_slot(core, stop)
    if not _is_locked(stop, override):
        # Only a time somebody chose to accept holds its place. The calculation
        # writes its own result back to the stop, and treating that as a
        # decision would make every run an anchor for the next one.
        return None, saved if stop.get("planned_time_accepted") else None
    if saved is None:
        raise ValueError(
            "Save a visit date and AM/PM period before locking this visit"
        )
    return saved, None


def build_team_events(
    core, plan: dict, stop_durations: dict, team: tuple = (),
) -> tuple:
    """The plan's stops as events on the team's shared calendar.

    Returns the events and anything the reader has to be told about who is
    attending them.
    """
    events = []
    missing = []
    orphaned = []
    for stop in plan.get("stops") or []:
        point = core._route_point_from_stop(stop)
        if not point:
            missing.append(
                stop.get("location_name") or stop.get("customer_name")
                or stop.get("id")
            )
            continue
        kind = (stop.get("stop_kind") or "customer")
        override = (stop_durations or {}).get(stop["id"], {})
        half_days = core._clean_half_days(
            override.get(
                "half_days",
                stop.get("duration_half_days")
                or core._clean_stay_days(stop.get("stay_days")) * 2,
            ),
            f"duration_half_days[{stop['id']}]",
        )
        if kind == "free" and stop.get("category") in core.WAYPOINT_CATEGORIES:
            half_days = 0
        booked, planned = _slots_of(core, stop, override)
        attendees = _attendees(stop, team)
        if _named_attendees(stop) and not attendees:
            orphaned.append(
                stop.get("customer_name") or stop.get("location_name") or stop["id"]
            )
        events.append(
            TeamEvent(
                stop["id"], kind,
                {**point, "kind": "stop", "stop_id": stop["id"],
                 "stop_kind": kind},
                max(1, int(half_days)) if kind != "free" else int(half_days),
                attendees,
                booked,
                planned,
                label=(
                    stop.get("customer_name") or stop.get("location_name")
                    or stop["id"]
                ),
                preferred_period=_preferred_period(stop, override),
                schedule_locked=_is_locked(stop, override),
                confirmation_status=stop.get("confirmation_status"),
            )
        )
    if missing:
        raise ValueError(
            "Set a location for these stops before planning: "
            + ", ".join(str(item) for item in missing[:5])
        )
    if not events:
        raise ValueError("Add at least one stop before generating an itinerary")
    return events, [
        {
            "code": "attendees_not_travelling",
            "severity": "warning",
            "message": (
                "Nobody named for these visits is travelling, so the whole team "
                "is planned to attend them: "
                + ", ".join(str(item) for item in orphaned)
            ),
        }
    ] if orphaned else []


def member_departure_slots(core, member_repo, plan_id: str,
                           start_slot: tuple, end=None) -> tuple:
    """Each member's own departure half-day, for those who have one.

    The plan's own dates bound the whole trip. A date before the start is not a
    second start - the plan cannot begin before it begins - so the team slot
    stands. A date after the end is a real mistake worth saying out loud: it
    would put somebody's departure past the day the trip is over.
    """
    slots, risks = {}, []
    for user, value in member_repo.departure_slots(plan_id).items():
        day = core._parse_date(value)
        if not day:
            continue
        if end and day > end:
            risks.append(
                {
                    "kind": "member_departure_after_plan_end",
                    "member_id": user,
                    "departure_date": day.isoformat(),
                    "deadline": end.isoformat(),
                }
            )
            continue
        if core._slot_key((day, "AM")) > core._slot_key(start_slot):
            slots[user] = (day, "AM")
    return slots, risks


def validate_team_inputs(team: tuple, origins: dict, destinations: dict) -> None:
    """Everybody on the trip needs somewhere to leave from and return to.

    Without it the core has no cursor to move and would report a complete route
    for somebody who never travelled, so this is rejected as missing data.
    """
    if not team:
        raise ValueError(
            "Add at least one team member before planning a team trip"
        )
    # Named without the account id: the message is shown to a user, and an
    # id in the middle of a sentence cannot be translated either.
    for user in team:
        if not (origins.get(user) or origins.get("__default__")):
            raise ValueError(
                "Set a departure point for the plan, or for every team member"
            )
        if not (destinations.get(user) or destinations.get("__default__")):
            raise ValueError(
                "Set a return point for the plan, or for every team member"
            )


def merge_stop_updates(updates: list) -> list:
    """One stop is one row: the database records visits, not attendances.

    Two attendees of the same event must have been given the same time; if they
    were not, the calculation is wrong and writing either one would hide it.
    """
    merged: dict = {}
    for update in updates:
        row = {key: value for key, value in update.items() if key != "member_id"}
        stop_id = row["id"]
        existing = merged.get(stop_id)
        if existing is None:
            merged[stop_id] = row
            continue
        if existing != row:
            raise ValueError(
                f"Internal error: stop {stop_id} was scheduled at two "
                "different times for the same event"
            )
    return list(merged.values())


def number_stops_in_visit_order(updates: list) -> list:
    """Number the stops in the order the trip reaches them.

    Every stop card is numbered, and that number reads as "the first place we
    go to". Numbered in the order they were typed in, a visit that happens last
    wears a 1, and the printed list disagrees with the route beside it.
    """
    ordered = sorted(
        updates,
        key=lambda item: (
            item.get("planned_date") or "",
            0 if item.get("planned_start_period") == "AM" else 1,
        ),
    )
    for position, item in enumerate(ordered, start=1):
        item["sequence_no"] = position
    return updates


def booked_time_risks(events: list, avoid_weekends: bool, holidays) -> list:
    """What an agreed time costs, said out loud.

    The customer's time wins over a weekend we wanted to keep free and over the
    half of the day we would have preferred. Both are worth knowing about: they
    are why the trip looks the way it does, and the reader is the one who
    decides whether to call the customer back.
    """
    skipped = set(holidays)
    risks = []
    for event in events:
        if not event.booked_slot or event.kind == "free":
            continue
        day, period = event.booked_slot
        if not _workday(day, avoid_weekends, skipped):
            risks.append({
                "kind": "booked_on_skipped_day",
                "stop_id": event.stop_id,
                "date": day.isoformat(),
            })
        if event.preferred_period not in ("auto", period):
            risks.append({
                "kind": "booked_outside_preferred_period",
                "stop_id": event.stop_id,
                "preferred_period": event.preferred_period,
                "booked_period": period,
            })
    return risks


def return_overrun_risks(totals: dict, plan_end, return_end) -> list:
    """Getting home late is worth saying, but it is not a reason to refuse."""
    deadline = return_end or plan_end
    if not deadline:
        return []
    risks = []
    for user, total in totals.items():
        end_date = total.get("calculated_end_date")
        if end_date and end_date > deadline.isoformat():
            risks.append(
                {
                    "kind": "member_return_overrun",
                    "member_id": user,
                    "calculated_end_date": end_date,
                    "calculated_end_period": total.get("calculated_end_period"),
                    "deadline": deadline.isoformat(),
                }
            )
    return risks


def _plan_in_route_order(core, plan: dict, data: dict, priority: list) -> dict:
    """The stops in the order the trip should reach them.

    A visit nobody has agreed a time for happens where the plan lists it. So
    the order of that list is the route: dragged by hand it is the arrangement
    the user chose, and left on automatic it is the one worked out from the
    map. Read straight from storage, both are ignored and the trip is run in
    the order the stops happened to be typed in.
    """
    stops = plan.get("stops") or []
    order = validate_stop_order(
        data.get("stop_order") if "stop_order" in data else None,
        [stop["id"] for stop in stops],
    )
    if order:
        by_id = {stop["id"]: stop for stop in stops}
        return {**plan, "stops": [by_id[stop_id] for stop_id in order]}
    mode = (
        data.get("route_order_mode") if "route_order_mode" in data
        else plan.get("route_order_mode")
    )
    if (mode or "auto") != "auto" or len(stops) < 2:
        return plan
    routable = []
    for stop in stops:
        point = core._route_point_from_stop(stop)
        if not point:
            # Reported by name when the events are built. Ordering an
            # incomplete route here would only hide which stop is missing.
            return plan
        routable.append((
            stop,
            {**point, "kind": "stop", "stop_id": stop["id"],
             "stop_kind": stop.get("stop_kind") or "customer"},
        ))
    merged = _plan_with_request_points(plan, data)
    origin = core._route_endpoint("origin", data, merged)
    destination = core._route_endpoint("destination", data, merged)
    if not origin:
        return plan
    ordered = core._order_route_stops(
        {**origin, "kind": "origin", "stop_id": None},
        {**destination, "kind": "destination", "stop_id": None} if destination
        else None,
        routable,
        priority,
    )
    return {**plan, "stops": [stop for stop, _ in ordered]}


def _reject_unknown_leg_overrides(plan: dict, data: dict) -> None:
    """A mode chosen for a connection this route does not have.

    The browser keeps a choice only for the connections it drew, so on a route
    the user arranged by hand a key that is not on it means the page has fallen
    behind the plan. Taking it in would drop that choice without a word; the
    refusal sends the page back for the route as it now stands.
    """
    incoming = data.get("leg_overrides")
    if not isinstance(incoming, dict) or not incoming:
        return
    mode = (
        data.get("route_order_mode") if "route_order_mode" in data
        else plan.get("route_order_mode")
    ) or "auto"
    if mode != "manual":
        # Reordering by itself makes a key stale, which is ordinary and is
        # reported in the summary rather than refused.
        return
    points = [
        "origin", *[stop["id"] for stop in plan.get("stops") or []], "destination",
    ]
    keys = {f"{left}>{right}" for left, right in zip(points, points[1:])}
    unknown = sorted(set(incoming) - keys)
    if unknown:
        raise ValueError("Unknown leg override: " + ", ".join(unknown))


def _plan_with_request_points(plan: dict, data: dict) -> dict:
    """The plan as this request describes it, not only as it was last saved.

    A route is previewed from what is on the form, and where the trip leaves
    from is on the form. Reading only the saved plan meant a departure point
    that had been typed but not yet saved did nothing, and the preview refused
    a trip the reader could plainly see had a starting point.
    """
    merged = dict(plan)
    for field in (
        "origin_name", "origin_lat", "origin_lng",
        "destination_name", "destination_lat", "destination_lng",
    ):
        if field in data:
            merged[field] = data[field]
    return merged


def _shared_summary_fields(core, plan, data, settings, result, events) -> dict:
    """The parts of a route summary that do not depend on how it was planned.

    The itinerary panel asks a route when it ends, how many days of it are
    travelling, and whether it runs past the dates it was given. Those
    questions are the same however many people are on the trip, and a summary
    that leaves them out draws a panel of blanks beside a route that is
    perfectly well planned.

    The team answers them per member, so the trip's answer is the last member
    to finish and the sum of what each of them does.
    """
    # Said in the summary, not only refused: a date nobody can parse and a trip
    # that runs past its end are both things the reader has to see next to the
    # route, and a route that reports neither reads as a route with no problems.
    holiday_input = (
        data.get("holiday_dates") if "holiday_dates" in data
        else plan.get("holiday_dates")
    )
    holidays, invalid_holidays = core._parse_holiday_dates(holiday_input)
    warnings = []
    if invalid_holidays:
        warnings.append(
            "Ignored invalid holiday dates: " + ", ".join(invalid_holidays[:5])
        )
    totals = result.member_totals or {}
    ends = sorted(
        (value.get("calculated_end_date"), value.get("calculated_end_period"))
        for value in totals.values()
        if value.get("calculated_end_date")
    )
    last_end, last_period = ends[-1] if ends else (None, None)
    stays = sum(
        int(item.duration_half_days or 0) for item in events
    )
    travel_half_days = sum(
        1 for item in result.schedule_items if item.get("item_type") in ("leg", "airport")
    )
    requested_end = plan.get("end_date") if "end_date" not in data else data.get("end_date")
    overrun = 0
    if last_end and requested_end and last_end > str(requested_end):
        overrun = (
            core._parse_date(last_end) - core._parse_date(str(requested_end))
        ).days
    if overrun:
        warnings.append(
            f"Itinerary exceeds requested end date {requested_end} "
            f"by {overrun} day(s)"
        )
    # An agreed appointment holds its date even when the trip is later moved
    # around it, so the route can end up starting before the trip does. Left
    # unsaid, that route reads as one that fits the dates it was given.
    # A mode somebody picked for a connection the route no longer makes is a
    # decision that quietly did nothing. Dropped in silence, the next draw
    # simply shows it unset and the user retypes it.
    incoming = data.get("leg_overrides")
    if isinstance(incoming, dict):
        planned_keys = {leg["leg_key"] for leg in result.legs}
        obsolete = sorted(set(incoming) - planned_keys)
        if obsolete:
            warnings.append(
                "Ignored obsolete leg overrides after automatic route reorder: "
                + ", ".join(obsolete)
            )
    requested_start = settings["initial_slot"][0].isoformat()
    starts = [item["date"] for item in result.schedule_items if item.get("date")]
    first_day = min(starts) if starts else None
    if first_day and first_day < requested_start:
        early = (
            core._parse_date(requested_start) - core._parse_date(first_day)
        ).days
        warnings.append(
            f"Itinerary starts {first_day}, {early} day(s) before the requested "
            f"start date {requested_start}"
        )
    return {
        "generated_at": now_iso(),
        "start_date": settings["initial_slot"][0].isoformat(),
        "calculated_end_date": last_end,
        "calculated_end_period": last_period,
        "requested_end_date": requested_end,
        "overrun_days": float(overrun),
        "overrun_half_days": overrun * 2,
        "within_date_window": overrun == 0,
        "stop_count": len(events),
        "leg_count": len(result.legs),
        "total_stay_half_days": stays,
        "total_stay_days": stays / 2,
        "total_travel_half_days": travel_half_days,
        "total_travel_days": travel_half_days / 2,
        "total_schedule_half_days": stays + travel_half_days,
        "total_business_days": (stays + travel_half_days) / 2,
        "total_calendar_days": (stays + travel_half_days) / 2,
        "travel_mode": (
            data.get("travel_mode") or plan.get("travel_mode") or "auto"
        ),
        "route_order_mode": (
            data.get("route_order_mode") if "route_order_mode" in data
            else plan.get("route_order_mode")
        ) or "auto",
        "transport_mode_priority": list(settings["priority"]),
        "avoid_weekends": bool(
            data.get("avoid_weekends") if "avoid_weekends" in data
            else plan.get("avoid_weekends", True)
        ),
        "holiday_dates": holidays,
        "warnings": warnings,
    }


def calculate_team_itinerary(core, member_repo, plan: dict, data: dict) -> dict:
    """The team equivalent of `_calculate_trip_itinerary`."""
    settings = core._team_plan_settings(plan, data)
    plan = _plan_in_route_order(core, plan, data, settings["priority"])
    _reject_unknown_leg_overrides(plan, data)
    plan_id = plan["id"]
    team = member_repo.member_ids(plan_id)
    origins, destinations = member_repo.points(
        plan_id, _plan_with_request_points(plan, data)
    )
    validate_team_inputs(team, origins, destinations)

    # Normalised the same way however many people are travelling: the legacy
    # full-day key is still accepted, unknown stops are still refused, and a
    # duration of 999 days is still clamped rather than believed.
    durations = core._clean_stop_durations(
        data, {stop["id"] for stop in plan.get("stops") or []}
    )
    events, attendee_risks = build_team_events(core, plan, durations, team)
    departures, departure_risks = member_departure_slots(
        core, member_repo, plan_id, settings["initial_slot"], settings["end"]
    )
    result = plan_team_itinerary(
        core, team, events, origins, settings["initial_slot"],
        settings["priority"], destinations=destinations,
        leg_settings=core._team_leg_settings(
            plan_id, team, data.get("leg_overrides")
        ),
        departures=departures,
        avoid_weekends=settings["avoid_weekends"],
        holidays=settings["holidays"],
    )
    risks = [
        *result.risks,
        *attendee_risks,
        *departure_risks,
        *booked_time_risks(
            events, settings["avoid_weekends"], settings["holidays"]
        ),
        *return_overrun_risks(
            result.member_totals, settings["end"], settings["return_end"]
        ),
    ]
    return {
        **_shared_summary_fields(core, plan, data, settings, result, events),
        "planning_mode": "team",
        "legs": result.legs,
        "schedule_items": result.schedule_items,
        "stop_updates": number_stops_in_visit_order(
            flag_moved_confirmations(
                plan, merge_stop_updates(result.stop_updates)
            )
        ),
        "member_totals": result.member_totals,
        "risks": risks,
        "members": team,
        "total_distance_km": round(
            sum(t["distance_km"] for t in result.member_totals.values()), 1
        ),
        "total_travel_hours": round(
            sum(t["travel_hours"] for t in result.member_totals.values()), 1
        ),
        "route_complete": all(
            t["route_complete"] for t in result.member_totals.values()
        ),
    }


TEAM_TIME_FIELDS = (
    "planned_date", "planned_end_date",
    "planned_start_period", "planned_end_period",
    "duration_half_days", "stay_days", "preferred_period", "schedule_locked",
)


def flag_moved_confirmations(plan: dict, updates: list) -> list:
    """A confirmed visit the calculation moved has to be agreed again.

    The customer agreed to a day, not to whatever the route later works out.
    Left marked confirmed, a visit the route quietly moved is how somebody
    turns up on a day nobody agreed to. Filling in a field that was blank is
    not a move: the end of a visit is derived from its start and its length,
    and the first calculation after an agreed time is entered supplies it.
    """
    saved = {stop["id"]: stop for stop in (plan.get("stops") or [])}
    for update in updates:
        stop = saved.get(update["id"])
        if not stop or stop.get("confirmation_status") != "confirmed":
            continue
        if any(
            stop.get(field) and stop.get(field) != update.get(field)
            for field in TEAM_TIME_FIELDS
        ):
            update["confirmation_status"] = "needs_reconfirmation"
    return updates


def persist_team_itinerary(service, plan_id: str, summary: dict,
                           actor_id: str, now: str) -> None:
    """Write the calculated team itinerary.

    Only the times are written back to the stops: in team planning a stop has no
    single order or inbound journey any more, those belong to each member's lane.
    """
    conn = service.core.lead_repo.conn
    for item in summary["stop_updates"]:
        table = (
            "trip_plan_free_stops" if item.get("stop_kind") == "free"
            else "trip_plan_stops"
        )
        fields = list(TEAM_TIME_FIELDS)
        if item.get("sequence_no"):
            fields.append("sequence_no")
        if item.get("confirmation_status"):
            fields.append("confirmation_status")
        assignments = ", ".join(f"{field} = ?" for field in fields)
        conn.execute(
            f"""
            UPDATE {table}
            SET {assignments}, updated_at = ?, updated_by = ?,
                row_version = row_version + 1
            WHERE id = ? AND plan_id = ? AND archived_at IS NULL
            """,
            (
                *[item.get(field) for field in fields],
                now, actor_id, item["id"], plan_id,
            ),
        )
    service.leg_repo.replace_active(plan_id, summary["legs"], actor_id, now)


def suggest_team_visits(core, member_repo, plan: dict, data: dict) -> list:
    """The saved plan's flexible visits, with a time proposed for each."""
    from .trip_team_suggestions import suggest_flexible_visits

    plan_id = plan["id"]
    team = member_repo.member_ids(plan_id)
    origins, destinations = member_repo.points(
        plan_id, _plan_with_request_points(plan, data)
    )
    validate_team_inputs(team, origins, destinations)

    settings = core._team_plan_settings(plan, data)
    events, _ = build_team_events(
        core, plan,
        core._clean_stop_durations(
            data, {stop["id"] for stop in plan.get("stops") or []}
        ),
        team,
    )
    holidays, _ = core._parse_holiday_dates(
        data.get("holiday_dates") if "holiday_dates" in data
        else plan.get("holiday_dates")
    )
    avoid_weekends = data.get("avoid_weekends")
    if avoid_weekends is None:
        avoid_weekends = bool(plan.get("avoid_weekends", True))

    found = suggest_flexible_visits(core, team, events, {
        **settings,
        "origins": origins,
        "destinations": destinations,
        "leg_settings": core._team_leg_settings(
            plan_id, team, data.get("leg_overrides")
        ),
        "departures": member_departure_slots(
            core, member_repo, plan_id, settings["initial_slot"],
            settings["end"],
        )[0],
        "avoid_weekends": bool(avoid_weekends),
        "holidays": tuple(holidays),
    })
    labels = {
        stop["id"]: stop.get("customer_name") or stop.get("location_name")
        for stop in plan.get("stops") or []
    }
    return [
        {
            "stop_id": item.stop_id,
            "label": labels.get(item.stop_id),
            "date": item.date,
            "period": item.period,
            "participants": list(item.participants),
            "added_travel_hours": item.added_travel_hours,
            "added_distance_km": item.added_distance_km,
            "reason": item.reason,
        }
        for item in found
    ]
