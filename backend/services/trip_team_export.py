"""The team dimension of an exported trip plan.

An export is a record of what was decided, so it keeps one row per member's
journey rather than merging colleagues who travel together: the map and the
timeline are where a shared journey is one line, and a record that merges them
cannot answer "whose leg was this".
"""

from __future__ import annotations


def is_team(plan: dict) -> bool:
    return (plan or {}).get("planning_mode") == "team"


def member_name(plan: dict, user_id) -> str:
    if not user_id:
        return ""
    for member in (plan or {}).get("members") or []:
        if member.get("user_id") == user_id:
            return member.get("display_name") or user_id
    return str(user_id)


def schedule_state(stop: dict) -> str:
    """Who decided this visit's time, in the words the app already uses."""
    if stop.get("schedule_locked"):
        return "Confirmed"
    if stop.get("planned_time_accepted"):
        return "Planned"
    return "Calculated" if stop.get("planned_date") else "Unscheduled"


def attendee_ids(stop: dict) -> list:
    if (stop.get("stop_kind") or "customer") == "free":
        return list(stop.get("participant_user_ids") or [])
    briefing = stop.get("briefing") or {}
    return [
        row["user_id"] for row in briefing.get("participants") or []
        if row.get("user_id")
    ]


def attendee_names(plan: dict, stop: dict) -> str:
    ids = attendee_ids(stop)
    if not ids:
        return "Whole travel team"
    return " / ".join(member_name(plan, user_id) for user_id in ids)


def endpoints(plan: dict, member: dict) -> str:
    origin = member.get("origin_name_override") or plan.get("origin_name") or "-"
    home = (
        member.get("destination_name_override")
        or plan.get("destination_name") or "-"
    )
    return f"{origin} to {home}"


def header_lines(plan: dict) -> list:
    """Who is travelling, and what the trip costs each of them."""
    members = plan.get("members") or []
    if not members:
        return []
    totals = (plan.get("itinerary_summary") or {}).get("member_totals") or {}
    lines = ["", "## Travel Team", ""]
    lines.append("| Member | Departure to Return | Distance km | Travel hours "
                 "| Expected back | Route complete |")
    lines.append("|---|---|---:|---:|---|---|")
    for member in members:
        total = totals.get(member["user_id"]) or {}
        lines.append(
            "| {name} | {ends} | {km} | {hours} | {back} | {complete} |".format(
                name=member.get("display_name") or member["user_id"],
                ends=endpoints(plan, member),
                km=total.get("distance_km", "-"),
                hours=total.get("travel_hours", "-"),
                back=" ".join(str(value) for value in (
                    total.get("calculated_end_date"),
                    total.get("calculated_end_period"),
                ) if value) or "-",
                complete="yes" if total.get("route_complete") else "no",
            )
        )
    return lines


def risk_lines(plan: dict) -> list:
    """The risks as they were recorded, kinds and values, not sentences."""
    risks = (plan.get("itinerary_summary") or {}).get("risks") or []
    if not risks:
        return []
    lines = ["", "## Schedule Risks", "", "| Risk | Member | Visit | When |",
             "|---|---|---|---|"]
    for risk in risks:
        lines.append(
            "| {kind} | {member} | {stop} | {when} |".format(
                kind=risk.get("kind") or "-",
                member=member_name(
                    plan, risk.get("member_id") or risk.get("user_id")
                ) or "-",
                stop=risk.get("stop_id")
                or " / ".join(risk.get("stop_ids") or []) or "-",
                when=" ".join(str(value) for value in (
                    risk.get("date"), risk.get("period")
                ) if value) or "-",
            )
        )
    return lines
