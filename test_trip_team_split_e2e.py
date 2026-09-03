"""Three colleagues, one trip, three different routes - over the real HTTP API.

This is the trip the team planning feature exists for and the one it was asked
for by name: two people fly out together, one of them goes home early, a third
leaves a week later and meets the first abroad, and they come home separately.

It runs through FastAPI, SQLite and a reload rather than the frontend payload
alone, because every defect this file was written for survived a frontend-only
check: a stop date the request model did not declare (422 before the service was
ever reached), two stops booked into the same half-day, and a member who could
not be given a departure day of their own.
"""
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.environ["JPT_DATA_DIR"] = tempfile.mkdtemp(prefix="jpt_team_e2e_")

from backend.config import init_settings
from backend.repositories.base import generate_uuid, get_db, now_iso
from backend.services.password_service import hash_password
from backend.startup_upgrade import initialize_database_safely

initialize_database_safely(init_settings(ROOT))

SZX = ("Shenzhen", 22.6393, 113.8106)
CUSTOMERS = {
    "VJT": (48.0922, 11.1500),   # near Munich
    "PMI": (41.9028, 12.4964),   # Rome
    "SMG": (45.9600, 4.7100),    # France
    "ATG": (53.8800, 10.8100),   # north Germany
}

conn = get_db()
stamp = now_iso()
leader = generate_uuid()
conn.execute(
    "INSERT INTO users (id,username,password_hash,display_name,role,is_active,"
    "created_at) VALUES (?,'lead',?,'Lead','leader',1,?)",
    (leader, hash_password("pw123456"), stamp),
)
people = {}
for key, name in (("A", "Ayden"), ("B", "Slluu"), ("C", "Eric")):
    uid = generate_uuid()
    conn.execute(
        "INSERT INTO users (id,username,password_hash,display_name,role,"
        "is_active,created_at) VALUES (?,?,?,?,'sales',1,?)",
        (uid, name.lower(), hash_password("pw123456"), name, stamp),
    )
    people[key] = uid
conn.execute("UPDATE organizations SET signing_public_key=NULL")

plan = generate_uuid()
conn.execute(
    """INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,travel_mode,
    route_order_mode,transport_mode_priority,origin_name,origin_lat,origin_lng,
    destination_name,destination_lat,destination_lng,avoid_weekends,status,
    planning_mode,departure_window_start,departure_window_end,
    created_at,created_by,updated_at,updated_by,row_version)
    VALUES (?,?,?,'2026-09-03','2026-09-30','flight','manual',?,?,?,?,?,?,?,0,
    'Draft','team','2026-09-03T09:00','2026-09-03T18:00',?,?,?,?,1)""",
    (plan, "Split trip", leader, '["flight","drive"]',
     SZX[0], SZX[1], SZX[2], SZX[0], SZX[1], SZX[2], stamp, leader, stamp, leader),
)
stops = {}
for index, (name, (lat, lng)) in enumerate(CUSTOMERS.items(), start=1):
    cid, sid = generate_uuid(), generate_uuid()
    conn.execute(
        "INSERT INTO customers (id,display_name,normalized_name,lat,lng,"
        "created_at,updated_at,row_version) VALUES (?,?,?,?,?,?,?,1)",
        (cid, name, name.lower(), lat, lng, stamp, stamp),
    )
    conn.execute(
        """INSERT INTO trip_plan_stops (id,plan_id,customer_id,sequence_no,
        duration_half_days,stay_days,preferred_period,schedule_locked,
        confirmation_status,created_at,created_by,updated_at,updated_by,
        row_version) VALUES (?,?,?,?,2,1,'auto',0,'unconfirmed',?,?,?,?,1)""",
        (sid, plan, cid, index, stamp, leader, stamp, leader),
    )
    stops[name] = sid
conn.commit()

from backend.repositories import close_db
close_db()

from fastapi.testclient import TestClient
from backend.app_v2 import create_app

client = TestClient(create_app())
token = client.post(
    "/api/auth/login", json={"username": "lead", "password": "pw123456"}
).json()["token"]
H = {"Authorization": f"Bearer {token}"}
BASE = f"/api/review/trip-plans/{plan}"

PAYLOAD = {
    "title": "Split trip", "start_date": "2026-09-03", "end_date": "2026-09-30",
    "region": None, "origin_name": SZX[0], "origin_lat": SZX[1],
    "origin_lng": SZX[2], "destination_name": SZX[0], "destination_lat": SZX[1],
    "destination_lng": SZX[2], "avoid_weekends": False, "holiday_dates": [],
    "description": None, "travel_mode": "auto", "route_order_mode": "manual",
    "transport_mode_priority": ["flight", "drive"],
    "departure_window_start": "2026-09-03T09:00",
    "departure_window_end": "2026-09-03T18:00",
    "return_window_start": None, "return_window_end": None, "stop_durations": {},
}

ATTENDEES = {"VJT": ("A", "B"), "PMI": ("A", "C"), "SMG": ("A",), "ATG": ("C",)}
AGREED = {"VJT": "2026-09-04", "PMI": "2026-09-10",
          "SMG": "2026-09-13", "ATG": "2026-09-15"}


def plan_now():
    return client.get(BASE, headers=H).json()


def stop_now(stop_id):
    return [s for s in plan_now()["stops"] if s["id"] == stop_id][0]


def fail(message, detail=""):
    raise AssertionError(f"{message}{(': ' + str(detail)[:400]) if detail else ''}")


# --- 1. the three of them join the trip, and C leaves on a day of their own ---
for key in ("A", "B", "C"):
    body = {"user_id": people[key]}
    if key == "C":
        # C's first appointment is a week after the team leaves. Without a
        # departure day of their own the plan flies C out on day one and has
        # them wait abroad, which is not the trip anybody agreed to.
        body["departure_date"] = "2026-09-09"
    r = client.put(f"{BASE}/members", json=body, headers=H)
    if r.status_code != 200:
        fail(f"member {key} could not join", r.text)

members = {m["user_id"]: m for m in plan_now()["members"]}
if members[people["C"]].get("departure_date") != "2026-09-09":
    fail("C's own departure day was not stored", members[people["C"]])
if members[people["A"]].get("departure_date"):
    fail("a member who leaves with the team must keep no date of their own")


# --- 2. the agreed appointments, and who attends each ---
for name, day in AGREED.items():
    sid = stops[name]
    r = client.patch(f"{BASE}/stops/{sid}", headers=H, json={
        "row_version": stop_now(sid)["row_version"],
        "planned_date": day, "planned_start_period": "AM",
        "schedule_locked": True, "confirmation_status": "confirmed",
    })
    if r.status_code != 200:
        fail(f"agreed time for {name} was rejected", r.text)
    r = client.put(f"{BASE}/stops/{sid}/briefing", headers=H, json={
        "stop_row_version": stop_now(sid)["row_version"],
        "participants": [{"user_id": people[k]} for k in ATTENDEES[name]],
    })
    if r.status_code != 200:
        fail(f"attendees for {name} were rejected", r.text)


# --- 3. the personal stop: a day of its own, and only A stops there ---
# VJT runs 9/4 AM through 9/4 PM, so the stay cannot start before 9/5: two
# places in one half-day is the same person in two countries.
r = client.post(f"{BASE}/free-stops", headers=H, json={
    "category": "hotel", "location_name": "Stuttgart",
    "lat": 48.7758, "lng": 9.1829, "duration_half_days": 8,
    "preferred_period": "auto", "confirmation_status": "confirmed",
    "planned_date": "2026-09-05", "planned_start_period": "AM",
    "schedule_locked": True, "participant_user_ids": [people["A"]],
})
if r.status_code != 200:
    fail(
        "a personal stop given a day must be accepted; the request model must "
        "declare every field the form sends or the browser only ever sees 422",
        r.text,
    )
stuttgart = [
    s for s in r.json()["stops"]
    if s.get("stop_kind") == "free" and s.get("location_name") == "Stuttgart"
][0]["id"]

# Editing it must work the same way the browser edits it.
saved = stop_now(stuttgart)
r = client.patch(f"{BASE}/free-stops/{stuttgart}", headers=H, json={
    "row_version": saved["row_version"], "planned_date": "2026-09-05",
    "planned_start_period": "AM", "schedule_locked": True,
    "participant_user_ids": [people["A"]], "duration_half_days": 8,
})
if r.status_code != 200:
    fail("editing a personal stop with a day must be accepted", r.text)

reloaded = stop_now(stuttgart)
if reloaded["planned_date"] != "2026-09-05":
    fail("the stay day did not survive a reload", reloaded)
if reloaded["planned_start_period"] != "AM":
    fail("the stay half-day did not survive a reload", reloaded)
if list(reloaded.get("participant_user_ids") or []) != [people["A"]]:
    fail("who stops there did not survive a reload", reloaded)


# --- 3b. the people this visit can be given are the people on this trip ---
r = client.get(f"{BASE}/stops/{stops['VJT']}/briefing", headers=H)
if r.status_code != 200:
    fail("the visit preparation could not be read", r.text)
offered = {
    str(person.get("user_id") or person.get("id"))
    for person in r.json().get("available_participants") or []
}
if offered != {people["A"], people["B"], people["C"]}:
    fail(
        "the people offered for a visit must be the people on this trip, not "
        "the whole account directory: naming somebody who is not travelling is "
        "not a visit anybody attends",
        sorted(offered),
    )


# --- 4. save the route, then read back what was stored ---
r = client.post(f"{BASE}/generate-itinerary", headers=H,
                json={**PAYLOAD, "row_version": plan_now()["row_version"]})
if r.status_code != 200:
    fail("saving the team route failed", r.text)
summary = r.json()["itinerary_summary"]

items = summary["schedule_items"]
NAME_OF = {v: k for k, v in people.items()}


def lane(member_key, include_travel=False):
    """This member's lane in order: where they stop, and how they get there."""
    mine = sorted(
        (item for item in items if item["member_id"] == people[member_key]
         and (include_travel or item["item_type"] != "leg")),
        key=lambda item: (item["lane_order"], item.get("half_day_index") or 0),
    )
    ordered = []
    for item in mine:
        if not ordered or ordered[-1] != item["title"]:
            ordered.append(item["title"])
    return ordered


def route(member_key):
    return lane(member_key)


a_route, b_route, c_route = route("A"), route("B"), route("C")

if a_route != ["VJT", "Stuttgart", "PMI", "SMG"]:
    fail("A's route is not the one that was planned", a_route)
if b_route != ["VJT"]:
    fail("B must attend VJT and nothing else", b_route)
if c_route != ["PMI", "ATG"]:
    fail("C must attend PMI and ATG and nothing else", c_route)

# The return leg is what says somebody actually went home, so it is checked
# on the lane that includes travel rather than inferred from the last visit.
for who, last_leg in (("A", "SMG → Shenzhen"), ("B", "VJT → Shenzhen"),
                      ("C", "ATG → Shenzhen")):
    if lane(who, include_travel=True)[-1] != last_leg:
        fail(f"{who} did not travel home from their own last stop",
             lane(who, include_travel=True))

for absent, where in (("B", "Stuttgart"), ("C", "Stuttgart"), ("C", "VJT")):
    if where in route(absent):
        fail(
            f"{absent} was sent to {where}; a stop that names who attends must "
            "not carry the rest of the team along",
            route(absent),
        )


# --- 5. nobody is in two places at once, and everybody gets home ---
risks = summary.get("risks") or []
double = [r for r in risks if r["kind"] == "member_double_booked"]
if double:
    fail("two stops were booked into the same half-day", double)

totals = summary["member_totals"]
for key in ("A", "B", "C"):
    total = totals[people[key]]
    if not total["route_complete"]:
        fail(f"{key}'s route is incomplete", total)

# B goes home from VJT, not from wherever the trip ends.
b_end = totals[people["B"]]["calculated_end_date"]
c_end = totals[people["C"]]["calculated_end_date"]
if not (b_end < AGREED["PMI"]):
    fail("B should be home before the PMI visit the others attend", b_end)
if not (c_end >= AGREED["ATG"]):
    fail("C should get home after their own last visit", c_end)

# Each member's lane starts on the day that member leaves: C on their own,
# the other two on the team's. Read off the timeline rather than the leg row,
# because the timeline is what the plan shows and what the export repeats.
def first_day(member_key):
    mine = [item for item in items if item["member_id"] == people[member_key]]
    if not mine:
        fail(f"{member_key} has no itinerary at all")
    return min(item["date"] for item in mine)


if first_day("C") != "2026-09-09":
    fail(
        "C must leave on their own departure day, not with the team a week "
        "earlier and then wait abroad",
        first_day("C"),
    )
for key in ("A", "B"):
    if first_day(key) != "2026-09-03":
        fail(
            f"{key} leaves with the team and must still start on the team's "
            "departure day",
            first_day(key),
        )


# --- 5b0. the formal documents carry the travel team ---
# Excel, offline HTML and the calendar are built from one model. It used to
# have no member dimension, and looked legs up by connection alone - so two
# colleagues on the same pair of places overwrote each other and the file
# stated one member's journey as both of theirs. It refused team trips instead.
for suffix in ("xlsx", "html", "ics"):
    r = client.get(f"{BASE}/export.{suffix}", headers=H)
    if r.status_code != 200:
        fail(f"export.{suffix} must carry a team trip", r.text[:200])
    if not r.content:
        fail(f"export.{suffix} produced an empty file")

from backend.services.trip_export_model import build_trip_export_model

model = build_trip_export_model(plan_now(), lambda leg: "")
TRAVELLERS = "出行人 / Travellers"

named = {
    row[TRAVELLERS] for row in model["timeline"] if row[TRAVELLERS]
}
if not named:
    fail("every line of a team itinerary has to say who is on it")
together = [who for who in named if " · " in who]
if not together:
    fail(
        "colleagues travelling together are one line naming all of them, and "
        "this trip has people who travel together",
        sorted(named),
    )
if any("Eric" in who and "Slluu" in who for who in named):
    fail(
        "Eric and Slluu never travel together on this trip, so no line may "
        "name both",
        sorted(named),
    )

# One journey, one row - not one row per member of it.
shared = [row for row in model["legs"] if " · " in row[TRAVELLERS]]
if not shared:
    fail("a leg two of them share must appear once, naming both",
         [row[TRAVELLERS] for row in model["legs"]])
keys = [(row["出发地 / From"], row["目的地 / To"], row["交通方式 / Mode"],
         row["出行人 / Travellers"]) for row in model["legs"]]
if len(keys) != len(set(keys)):
    fail("a journey is printed more than once", keys)

# Each member's own endpoints and distance, since one departure point and one
# return date cannot describe a trip people leave and come back from apart.
labels = {label for label, _ in model["metadata"]}
for name in ("Ayden", "Slluu", "Eric"):
    if not any(name in label for label in labels):
        fail(f"{name} is missing from the document header", sorted(labels))
if any(label.startswith(("出发窗口", "返回窗口")) for label in labels):
    fail(
        "the shared travel windows do not describe a team trip and were "
        "removed from the plan; the document must not still show them",
        sorted(labels),
    )

# The calendar is one file for the whole trip, and every event says whose it is.
calendar = client.get(f"{BASE}/export.ics", headers=H).text
summaries = [
    line for line in calendar.split("\r\n") if line.startswith("SUMMARY:")
]
if not summaries:
    fail("the calendar has no events")
if not any(" · " in line and line.count("·") >= 3 for line in summaries):
    fail("a shared journey is one event naming its travellers", summaries[:4])
uids = [line for line in calendar.split("\r\n") if line.startswith("UID:")]
if len(uids) != len(set(uids)):
    fail("two events share an identifier, so a calendar keeps only one of them")


# --- 5b. taking somebody off a visit takes them off the route ---
# The saved itinerary is what the timeline draws. If changing the attendees left
# it standing, the plan would keep showing a colleague on a visit they were just
# removed from, and on every leg that visit caused.
before = {
    item["member_id"] for item in items
    if item["source_id"] == stops["VJT"]
}
if before != {people["A"], people["B"]}:
    fail("VJT should have started with two attendees", sorted(before))

saved_briefing = client.get(
    f"{BASE}/stops/{stops['VJT']}/briefing", headers=H).json()
r = client.put(f"{BASE}/stops/{stops['VJT']}/briefing", headers=H, json={
    "stop_row_version": stop_now(stops["VJT"])["row_version"],
    "row_version": saved_briefing.get("row_version"),
    "participants": [{"user_id": people["A"]}],
})
if r.status_code != 200:
    fail("removing an attendee was rejected", r.text)

after = plan_now()
if after["itinerary_summary"].get("stale") is not True:
    fail(
        "changing who attends must mark the saved route out of date, or the "
        "plan keeps showing the colleagues of a calculation that no longer "
        "describes it",
        after["itinerary_summary"],
    )
if after.get("schedule_items"):
    fail(
        "an out-of-date route must not be handed back as if it still held",
        after["schedule_items"][:2],
    )

r = client.post(f"{BASE}/generate-itinerary", headers=H,
                json={**PAYLOAD, "row_version": after["row_version"]})
if r.status_code != 200:
    fail("recalculating after the attendee change failed", r.text)
recut = {
    item["member_id"] for item in r.json()["itinerary_summary"]["schedule_items"]
    if item["source_id"] == stops["VJT"]
}
if recut != {people["A"]}:
    fail("B is still on the VJT visit they were removed from", sorted(recut))


# --- 5c. choosing how a leg is travelled is honoured ---
# The browser keys its choice by the connection, because colleagues travelling
# together are one row on the route and one choice is made on it. Dropping that
# on the way in leaves the reader picking a mode and watching it go back to
# unset on the next draw.
r = client.post(f"{BASE}/generate-itinerary", headers=H, json={
    **PAYLOAD, "row_version": plan_now()["row_version"],
})
if r.status_code != 200:
    fail("could not recalculate before choosing a transport mode", r.text)
sample = next(
    (leg for leg in r.json()["itinerary_summary"]["legs"]
     if leg.get("selected_mode") != "drive"),
    None,
)
if not sample:
    fail("expected at least one leg not already driven")

r = client.post(f"{BASE}/preview-itinerary", headers=H, json={
    **PAYLOAD,
    "leg_overrides": {
        sample["leg_key"]: {"selected_mode": "drive", "mode_locked": True},
    },
})
if r.status_code != 200:
    fail("previewing with a chosen transport mode failed", r.text)
chosen = [
    leg for leg in r.json()["itinerary_summary"]["legs"]
    if leg["leg_key"] == sample["leg_key"]
]
if not chosen:
    fail("the leg disappeared from the preview", sample["leg_key"])
if any(leg.get("selected_mode") != "drive" for leg in chosen):
    fail(
        "the chosen transport mode was dropped, so the route comes back with "
        "it unset and the choice reads as not having been made",
        [leg.get("selected_mode") for leg in chosen],
    )


# --- 5d. the plan's own dates bound the trip, and nothing else does ---
# The separate departure and return windows said the same thing a second time
# for the whole team at once. A team trip now starts on the plan's start date,
# whatever those windows still hold.
r = client.post(f"{BASE}/preview-itinerary", headers=H, json={
    **PAYLOAD,
    "departure_window_start": "2026-09-20T09:00",
    "departure_window_end": "2026-09-21T09:00",
})
if r.status_code != 200:
    fail("a stale travel window must not block the preview", r.text)
windowed = r.json()["itinerary_summary"]["schedule_items"]
earliest = min(item["date"] for item in windowed)
if earliest != "2026-09-03":
    fail(
        "the trip must start on the plan's start date, not on a departure "
        "window that no longer has a say",
        earliest,
    )

# A member set to leave after the trip is over is a mistake worth saying.
r = client.put(f"{BASE}/members", headers=H,
               json={"user_id": people["C"], "departure_date": "2026-10-15"})
if r.status_code != 200:
    fail("setting a departure date was rejected", r.text)
r = client.post(f"{BASE}/preview-itinerary", headers=H, json=PAYLOAD)
if r.status_code != 200:
    fail("a departure past the end must be reported, not refused", r.text)
kinds = {
    risk["kind"] for risk in r.json()["itinerary_summary"].get("risks") or []
}
if "member_departure_after_plan_end" not in kinds:
    fail(
        "a member leaving after the trip ends must be reported against the "
        "plan's own window",
        sorted(kinds),
    )
client.put(f"{BASE}/members", headers=H,
           json={"user_id": people["C"], "departure_date": "2026-09-09"})


# --- 5e. a flown leg is the flight and the drives at either end ---
# Naming the airports turns one stored connection into three real movements.
# All three recorded at the departure half-day would say the whole of Shenzhen
# to Germany happened before lunch, and leave the days it takes looking free.
flown = summary["legs"][0]["leg_key"]
r = client.post(f"{BASE}/preview-itinerary", headers=H, json={
    **PAYLOAD,
    "leg_overrides": {
        flown: {
            "selected_mode": "flight", "mode_locked": True,
            "departure_airport_name": "Shenzhen SZX",
            "departure_airport_lat": 22.6393, "departure_airport_lng": 113.8106,
            "arrival_airport_name": "Paris CDG",
            "arrival_airport_lat": 49.0097, "arrival_airport_lng": 2.5479,
        },
    },
})
if r.status_code != 200:
    fail("naming the airports of a flown leg was rejected", r.text)
expanded = r.json()["itinerary_summary"]
leg = next(item for item in expanded["legs"] if item["leg_key"] == flown)
if leg.get("departure_airport_name") != "Shenzhen SZX":
    fail("the departure airport was dropped on the way in", leg)
if len(leg.get("segments") or []) != 3:
    fail(
        "a flown leg with both airports is a drive, a flight and a drive",
        leg.get("segments"),
    )
hops = [
    item for item in expanded["schedule_items"]
    if str(item.get("source_id", "")).startswith(f"{flown}#")
    and item["member_id"] == people["A"]
]
ROLES = ("to_airport", "flight", "from_airport")
moves = {}
for item in hops:
    moves.setdefault(item["source_id"].rsplit("#", 1)[1], []).append(
        (item["date"], item["period"])
    )
if sorted(moves) != sorted(ROLES):
    fail("each movement must appear on the timeline in its own right",
         sorted(moves))

# A journey occupies every half-day it runs through, the way a visit does.
# Recording only the first leaves the days in between looking free, and a
# two-day drive reading as half a day.
for role, slots in moves.items():
    span = next(
        item["half_day_count"] for item in hops
        if item["source_id"].endswith(f"#{role}")
    )
    if len(slots) != span:
        fail(f"{role} runs for {span} half-days but is shown on {len(slots)}",
             sorted(slots))
    if slots != sorted(slots):
        fail("the half-days of one movement must run in order", slots)

# They run in the order they are travelled, and two that each take time never
# share a half-day. One that takes none may sit in the same slot as the next.
starts = [moves[role][0] for role in ROLES]
if starts != sorted(starts):
    fail("the movements must run in the order they are travelled", starts)
timed = [moves[role][0] for role in ROLES if len(moves[role]) > 1]
if len(timed) != len(set(timed)):
    fail("two journeys that each take time share a half-day", timed)


# --- 5f. every part of a flown leg can be given a time ---
# A flown connection is a drive, a flight and a drive. What the reader typed on
# the connection is the flight they looked up; each drive has its own field.
# Estimating all three regardless showed times the reader could see were wrong
# and had nowhere to correct.
r = client.post(f"{BASE}/preview-itinerary", headers=H, json={
    **PAYLOAD,
    "leg_overrides": {
        flown: {
            "selected_mode": "flight", "mode_locked": True,
            "departure_airport_name": "Shenzhen SZX",
            "departure_airport_lat": 22.6393, "departure_airport_lng": 113.8106,
            "arrival_airport_name": "Paris CDG",
            "arrival_airport_lat": 49.0097, "arrival_airport_lng": 2.5479,
            "manual_time_hours": 16.6, "manual_travel_half_days": 4,
            "departure_transfer_half_days": 1,
            "departure_transfer_mode": "ground_public",
            "departure_transfer_time_hours": 1.2,
            "arrival_transfer_half_days": 3,
            "arrival_transfer_mode": "drive",
            "arrival_transfer_time_hours": 9.5,
        },
    },
})
if r.status_code != 200:
    fail("giving each part of a flown leg a time was rejected", r.text)
timed = next(
    item for item in r.json()["itinerary_summary"]["legs"]
    if item["leg_key"] == flown
)
parts = {segment["role"]: segment for segment in timed["segments"]}
if parts["to_airport"]["travel_half_days"] != 1:
    fail("the drive to the airport must take the time it was given", parts["to_airport"])
if parts["from_airport"]["travel_half_days"] != 3:
    fail("the drive from the airport must take the time it was given",
         parts["from_airport"])
if parts["flight"]["travel_half_days"] != 4:
    fail(
        "the hours and days typed on the connection describe the flight, and "
        "must not be thrown away when the airports are named",
        parts["flight"],
    )
if parts["flight"]["time_hours"] != 16.6:
    fail("the flight must keep the hours it was given", parts["flight"])
# How each drive is made, and how long it takes, is the traveller's to say: a
# train to the airport and a taxi at the other end is an ordinary trip.
if parts["to_airport"]["selected_mode"] != "ground_public":
    fail(
        "the way to the airport must be the way that was chosen, not the "
        "plan's first ground mode for both ends at once",
        parts["to_airport"],
    )
if parts["from_airport"]["selected_mode"] != "drive":
    fail("the way from the airport must be the way that was chosen",
         parts["from_airport"])
if parts["to_airport"]["time_hours"] != 1.2:
    fail("the transfer must keep the hours it was given", parts["to_airport"])
if parts["from_airport"]["time_hours"] != 9.5:
    fail("the transfer must keep the hours it was given", parts["from_airport"])
if timed["travel_half_days"] != 8:
    fail(
        "the connection takes as long as its parts do together",
        timed["travel_half_days"],
    )

# Leaving a drive empty is not the same as saying it takes no time.
r = client.post(f"{BASE}/preview-itinerary", headers=H, json={
    **PAYLOAD,
    "leg_overrides": {
        flown: {
            "selected_mode": "flight", "mode_locked": True,
            "departure_airport_name": "Shenzhen SZX",
            "departure_airport_lat": 22.6393, "departure_airport_lng": 113.8106,
            "arrival_airport_name": "Paris CDG",
            "arrival_airport_lat": 49.0097, "arrival_airport_lng": 2.5479,
        },
    },
})
estimated = next(
    item for item in r.json()["itinerary_summary"]["legs"]
    if item["leg_key"] == flown
)
guessed = {seg["role"]: seg for seg in estimated["segments"]}
if guessed["from_airport"]["selected_mode"] not in (
    "drive", "ground_public", "other"
):
    fail(
        "a transfer nobody has described still falls back to the plan's ground "
        "preference, and never to flying",
        guessed["from_airport"],
    )
if guessed["from_airport"]["travel_half_days"] < 1:
    fail(
        "a drive nobody has timed is still estimated, never treated as free",
        guessed["from_airport"],
    )


# --- 5g. a part that takes no time does not lengthen the trip ---
# Reported from a real plan: the drive to the airport was set to zero because
# the trip already starts at one, and the whole journey still came out half a
# day longer than the numbers on it.
r = client.post(f"{BASE}/preview-itinerary", headers=H, json={
    **PAYLOAD,
    "leg_overrides": {
        flown: {
            "selected_mode": "flight", "mode_locked": True,
            "departure_airport_name": "Shenzhen SZX",
            "departure_airport_lat": 22.6393, "departure_airport_lng": 113.8106,
            "arrival_airport_name": "Paris CDG",
            "arrival_airport_lat": 49.0097, "arrival_airport_lng": 2.5479,
            "manual_time_hours": 16.6, "manual_travel_half_days": 4,
            "departure_transfer_half_days": 0,
            "arrival_transfer_half_days": 4,
        },
    },
})
if r.status_code != 200:
    fail("a transfer of zero half-days was rejected", r.text)
summary_zero = r.json()["itinerary_summary"]
zero_leg = next(
    item for item in summary_zero["legs"] if item["leg_key"] == flown
)
if zero_leg["travel_half_days"] != 8:
    fail(
        "the connection takes exactly as long as its parts: 0 + 4 + 4",
        zero_leg["travel_half_days"],
    )
zero_hops = [
    item for item in summary_zero["schedule_items"]
    if str(item.get("source_id", "")).startswith(f"{flown}#")
    and item["member_id"] == people["A"]
]
spans = {}
for item in zero_hops:
    spans.setdefault(item["source_id"].rsplit("#", 1)[1], []).append(
        (item["date"], item["period"])
    )
if len(spans["to_airport"]) != 1:
    fail(
        "a transfer told it takes no time is still shown once, and occupies "
        "nothing",
        spans["to_airport"],
    )
if spans["to_airport"][0] != spans["flight"][0]:
    fail(
        "a transfer that takes no time must not push the flight into the next "
        "half-day",
        {"to_airport": spans["to_airport"], "flight": spans["flight"][:1]},
    )
if len(spans["flight"]) != 4 or len(spans["from_airport"]) != 4:
    fail("each part occupies the half-days it was given", {
        k: len(v) for k, v in spans.items()
    })
# A wait at the airport occupies its half-days too: a night before an early
# flight is time the traveller is not available for anything else.
r = client.post(f"{BASE}/preview-itinerary", headers=H, json={
    **PAYLOAD,
    "leg_overrides": {
        flown: {
            "selected_mode": "flight", "mode_locked": True,
            "departure_airport_name": "Shenzhen SZX",
            "departure_airport_lat": 22.6393, "departure_airport_lng": 113.8106,
            "departure_airport_stay_half_days": 3,
            "arrival_airport_name": "Paris CDG",
            "arrival_airport_lat": 49.0097, "arrival_airport_lng": 2.5479,
            "manual_travel_half_days": 2,
            "departure_transfer_half_days": 0,
            "arrival_transfer_half_days": 1,
        },
    },
})
if r.status_code != 200:
    fail("an airport wait was rejected", r.text)
waits = [
    (item["date"], item["period"])
    for item in r.json()["itinerary_summary"]["schedule_items"]
    if str(item.get("source_id", "")).endswith("-stay")
    and item["member_id"] == people["A"]
]
if len(waits) != 3:
    fail(
        "a wait at the airport must occupy every half-day it lasts, or the "
        "night before an early flight looks free",
        waits,
    )
if len(set(waits)) != 3:
    fail("the half-days of one wait must be distinct", waits)

covered = sorted({slot for slots in spans.values() for slot in slots})
if len(covered) != 8:
    fail(
        "every half-day of the journey must be accounted for, or the days in "
        "between look free",
        covered,
    )


# --- 5h. saving the route saves what the route was planned from ---
# The dates, the endpoints and the transport preferences arrive in the same
# request as the route. Single-traveller planning has always written them; team
# planning wrote only the calculated summary, so a start date the reader had
# just changed came back as the old one on the next draw.
moved = {
    **PAYLOAD,
    "start_date": "2026-09-04",
    "title": "Split trip, moved",
    "region": "EU",
    "description": "keep this",
    "transport_mode_priority": ["drive", "flight"],
    "row_version": plan_now()["row_version"],
}
r = client.post(f"{BASE}/generate-itinerary", headers=H, json=moved)
if r.status_code != 200:
    fail("saving the route with changed plan dates failed", r.text)
saved = plan_now()
for field, expected in (
    ("start_date", "2026-09-04"),
    ("title", "Split trip, moved"),
    ("region", "EU"),
    ("description", "keep this"),
):
    if saved.get(field) != expected:
        fail(
            f"saving the route must save the {field} it was planned from, or "
            "the form shows the change and the plan does not have it",
            {field: saved.get(field)},
        )
if list(saved.get("transport_mode_priority") or []) != ["drive", "flight"]:
    fail("the transport preferences were not saved",
         saved.get("transport_mode_priority"))
if saved.get("planning_mode") != "team":
    fail(
        "saving a route must never change how the plan is planned",
        saved.get("planning_mode"),
    )

# Put the plan back where the rest of this file expects it.
client.post(f"{BASE}/generate-itinerary", headers=H,
            json={**PAYLOAD, "row_version": plan_now()["row_version"]})


# --- 6. the export says the same thing the plan says ---
# Every change above put the saved route out of date, which is the point; the
# export refuses a stale one, so it is recalculated first.
r = client.post(f"{BASE}/generate-itinerary", headers=H,
                json={**PAYLOAD, "row_version": plan_now()["row_version"]})
if r.status_code != 200:
    fail("could not recalculate before exporting", r.text)

r = client.get(f"{BASE}/export.md", headers=H)
if r.status_code != 200:
    fail("the plan could not be exported", r.text[:200])
document = r.text
for name in ("VJT", "PMI", "SMG", "ATG", "Stuttgart"):
    if name not in document:
        fail(f"{name} is missing from the export")
for name in ("Ayden", "Slluu", "Eric"):
    if name not in document:
        fail(f"{name} is missing from the export")
for day in AGREED.values():
    if day not in document:
        fail(f"the agreed day {day} is missing from the export")
if "2026-09-05" not in document:
    fail("the personal stop's own day is missing from the export")

# Every format describes the team now, so none of them may refuse.
for suffix in ("xlsx", "html", "ics"):
    r = client.get(f"{BASE}/export.{suffix}", headers=H)
    if r.status_code != 200:
        fail(f"export.{suffix} refused a team trip it can describe", r.text[:200])

print("PASS: two colleagues out, one home early, a third joining later and "
      "everybody home again - over the real API")
