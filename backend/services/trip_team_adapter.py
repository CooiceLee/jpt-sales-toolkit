"""Turn a saved team trip plan into a calculated team itinerary.

This is the layer between what the user stored and what the multi-cursor core
computes: it reads the appointments and the people from the plan, hands them to
`plan_team_itinerary`, and folds the per-member result back into the one shape
the API and the database already speak.
"""

from __future__ import annotations

from .trip_team_schedule import TeamEvent, plan_team_itinerary


def _attendees(core, stop: dict) -> tuple:
    """Who from the team is at this stop. Empty means the whole team."""
    if (stop.get("stop_kind") or "customer") == "free":
        return tuple(stop.get("participant_user_ids") or ())
    briefing = stop.get("briefing") or {}
    return tuple(
        row["user_id"] for row in briefing.get("participants") or []
        if row.get("user_id")
    )


def _saved_slot(core, stop: dict) -> tuple | None:
    """The time saved on this stop, whatever it means."""
    day = core._parse_date(stop.get("planned_date"))
    period = stop.get("planned_start_period")
    if not day or period not in ("AM", "PM"):
        return None
    return day, period


def _slots_of(core, stop: dict) -> tuple:
    """What is agreed with the customer, and what we merely decided.

    A locked visit is an appointment and becomes a fact the plan is built
    around. An unlocked visit whose time somebody accepted is a plan of ours and
    has to be honoured, or applying a suggestion would appear to work and then
    be forgotten by the next calculation. A time the last calculation merely
    produced is neither: it is output, and must not constrain the next run.
    """
    saved = _saved_slot(core, stop)
    if not stop.get("schedule_locked"):
        # Only a time somebody chose to accept holds its place. The calculation
        # writes its own result back to the stop, and treating that as a
        # decision would make every run an anchor for the next one.
        return None, saved if stop.get("planned_time_accepted") else None
    if saved is None:
        raise ValueError(
            "Save a visit date and AM/PM period before locking this visit"
        )
    return saved, None


def build_team_events(core, plan: dict, stop_durations: dict) -> list:
    """The plan's stops as events on the team's shared calendar."""
    events = []
    missing = []
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
        booked, planned = _slots_of(core, stop)
        events.append(
            TeamEvent(
                stop["id"], kind,
                {**point, "kind": "stop", "stop_id": stop["id"],
                 "stop_kind": kind},
                max(1, int(half_days)) if kind != "free" else int(half_days),
                _attendees(core, stop),
                booked,
                planned,
                label=(
                    stop.get("customer_name") or stop.get("location_name")
                    or stop["id"]
                ),
            )
        )
    if missing:
        raise ValueError(
            "Set a location for these stops before planning: "
            + ", ".join(str(item) for item in missing[:5])
        )
    if not events:
        raise ValueError("Add at least one stop before generating an itinerary")
    return events


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


def calculate_team_itinerary(core, member_repo, plan: dict, data: dict) -> dict:
    """The team equivalent of `_calculate_trip_itinerary`."""
    settings = core._team_plan_settings(plan, data)
    plan_id = plan["id"]
    team = member_repo.member_ids(plan_id)
    origins, destinations = member_repo.points(plan_id, plan)
    validate_team_inputs(team, origins, destinations)

    events = build_team_events(core, plan, data.get("stop_durations") or {})
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
    )
    risks = [
        *result.risks,
        *departure_risks,
        *return_overrun_risks(
            result.member_totals, settings["end"], settings["return_end"]
        ),
    ]
    return {
        "planning_mode": "team",
        "legs": result.legs,
        "schedule_items": result.schedule_items,
        "stop_updates": merge_stop_updates(result.stop_updates),
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
)


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
        assignments = ", ".join(f"{field} = ?" for field in TEAM_TIME_FIELDS)
        conn.execute(
            f"""
            UPDATE {table}
            SET {assignments}, updated_at = ?, updated_by = ?,
                row_version = row_version + 1
            WHERE id = ? AND plan_id = ? AND archived_at IS NULL
            """,
            (
                *[item.get(field) for field in TEAM_TIME_FIELDS],
                now, actor_id, item["id"], plan_id,
            ),
        )
    service.leg_repo.replace_active(plan_id, summary["legs"], actor_id, now)


def suggest_team_visits(core, member_repo, plan: dict, data: dict) -> list:
    """The saved plan's flexible visits, with a time proposed for each."""
    from .trip_team_suggestions import suggest_flexible_visits

    plan_id = plan["id"]
    team = member_repo.member_ids(plan_id)
    origins, destinations = member_repo.points(plan_id, plan)
    validate_team_inputs(team, origins, destinations)

    settings = core._team_plan_settings(plan, data)
    events = build_team_events(core, plan, data.get("stop_durations") or {})
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
