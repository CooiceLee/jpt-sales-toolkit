"""An agreed visit time, entered the way the browser enters it, decides the route.

This is the workflow the module exists for: record what the customer agreed, and
get an itinerary built around it. It goes through the real HTTP endpoints with the
payload the frontend actually sends, because the pieces were all present and the
chain was broken in the browser - the preview request carried a field the endpoint
rejects, and there was nowhere to enter the time in the first place.
"""
import json, os, sys, tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.environ["JPT_DATA_DIR"] = tempfile.mkdtemp(prefix="jpt_e2e_")

from backend.config import init_settings
from backend.repositories.base import generate_uuid, get_db, now_iso
from backend.services.password_service import hash_password
from backend.startup_upgrade import initialize_database_safely
settings = init_settings(ROOT)
initialize_database_safely(settings)

conn = get_db(); stamp = now_iso(); actor = generate_uuid()
conn.execute("INSERT INTO users (id,username,password_hash,display_name,role,"
             "is_active,created_at) VALUES (?,'e2e',?,'E2E','leader',1,?)",
             (actor, hash_password("pw123456"), stamp))
conn.execute("UPDATE organizations SET signing_public_key=NULL")
plan = generate_uuid()
conn.execute("""INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,
  travel_mode,route_order_mode,transport_mode_priority,origin_name,origin_lat,
  origin_lng,destination_name,destination_lat,destination_lng,avoid_weekends,
  status,planning_mode,created_at,created_by,updated_at,updated_by,row_version)
  VALUES (?,?,?,?,?,?,'auto',?,?,?,?,?,?,?,1,'Draft','team',?,?,?,?,1)""",
  (plan,"E2E trip",actor,"2026-09-14","2026-09-30","flight",
   '["flight","drive"]',"Shanghai",31.2304,121.4737,"Shanghai",31.2304,121.4737,
   stamp,actor,stamp,actor))
conn.execute("""INSERT INTO trip_plan_members (id,plan_id,user_id,created_at,
  created_by,updated_at,updated_by,row_version) VALUES (?,?,?,?,?,?,?,1)""",
  (generate_uuid(),plan,actor,stamp,actor,stamp,actor))
stops = {}
for name, lat, lng in (("Frankfurt",50.1109,8.6821), ("Paris",48.8566,2.3522)):
    cid, sid = generate_uuid(), generate_uuid()
    conn.execute("INSERT INTO customers (id,display_name,normalized_name,lat,lng,"
                 "created_at,updated_at,row_version) VALUES (?,?,?,?,?,?,?,1)",
                 (cid,name,name.lower(),lat,lng,stamp,stamp))
    conn.execute("""INSERT INTO trip_plan_stops (id,plan_id,customer_id,sequence_no,
      duration_half_days,stay_days,preferred_period,schedule_locked,
      confirmation_status,created_at,created_by,updated_at,updated_by,row_version)
      VALUES (?,?,?,?,2,1,'auto',0,'unconfirmed',?,?,?,?,1)""",
      (sid,plan,cid,len(stops)+1,stamp,actor,stamp,actor))
    stops[name] = sid
conn.commit()
from backend.repositories import close_db
close_db()

from fastapi.testclient import TestClient
from backend.app_v2 import create_app
client = TestClient(create_app())
token = client.post("/api/auth/login",
                    json={"username":"e2e","password":"pw123456"}).json()["token"]
H = {"Authorization": f"Bearer {token}"}

def say(step): pass  # step titles are only useful when run by hand

say("1. 预览路线（模拟前端真实 payload，含 planning_mode 修复）")
payload = {"title":"E2E trip","start_date":"2026-09-14","end_date":"2026-09-30",
  "region":None,"origin_name":"Shanghai","origin_lat":31.2304,"origin_lng":121.4737,
  "destination_name":"Shanghai","destination_lat":31.2304,"destination_lng":121.4737,
  "avoid_weekends":True,"holiday_dates":[],"description":None,"travel_mode":"auto",
  "route_order_mode":"auto","transport_mode_priority":["flight","drive"],
  "departure_window_start":None,"departure_window_end":None,
  "return_window_start":None,"return_window_end":None,"stop_durations":{}}
r = client.post(f"/api/review/trip-plans/{plan}/preview-itinerary", json=payload, headers=H)
assert r.status_code == 200, (
    "the payload the frontend sends must be accepted; a field the endpoint does "
    f"not declare fails every preview: {r.text[:300]}"
)

say("2. 录入约定时间：Paris 必须是 2026-09-16 上午（客户已确认）")
paris = stops["Paris"]
cur = client.get(f"/api/review/trip-plans/{plan}", headers=H).json()
rv = [s for s in cur["stops"] if s["id"]==paris][0]["row_version"]
r = client.patch(f"/api/review/trip-plans/{plan}/stops/{paris}",
    json={"row_version":rv,"planned_date":"2026-09-16","planned_start_period":"AM",
          "schedule_locked":True,"preferred_period":"auto",
          "confirmation_status":"confirmed"}, headers=H)
assert r.status_code == 200, r.text[:300]
stop = [x for x in r.json()["stops"] if x["id"] == paris][0]
assert stop["planned_date"] == "2026-09-16"
assert stop["planned_start_period"] == "AM"
assert bool(stop["schedule_locked"]) is True

say("3. 重新预览：路线围绕约定时间安排，其他停靠让路")
r = client.post(f"/api/review/trip-plans/{plan}/preview-itinerary", json=payload, headers=H)
assert r.status_code == 200, (
    "an agreed time the estimate cannot meet is a risk, not a refusal: "
    f"{r.text[:300]}"
)
kept = [x for x in r.json()["stops"] if x["id"] == paris][0]
assert (kept["planned_date"], kept["planned_start_period"]) == ("2026-09-16", "AM"), (
    f"the route moved the agreed visit: {kept['planned_date']} "
    f"{kept['planned_start_period']}"
)
# Paris was entered second. The appointment is the fixed point, so the route is
# built around it and the stop with no agreed time is the one that gives way.
other = [x for x in r.json()["stops"] if x["id"] == stops["Frankfurt"]][0]
assert other["planned_date"] > "2026-09-16", (
    f"the unbooked visit should move behind the appointment, sits on "
    f"{other['planned_date']}"
)
risks = {risk["kind"] for risk in r.json()["itinerary_summary"].get("risks") or []}
assert "cannot_reach_booked_visit" not in risks, (
    f"the route can reach this appointment, so it must not be reported: {risks}"
)

say("3b. 无论怎样排都赶不上的约定时间：保留原时间并报风险")
cur = client.get(f"/api/review/trip-plans/{plan}", headers=H).json()
rv = [s for s in cur["stops"] if s["id"] == paris][0]["row_version"]
# The first morning of the trip: the flight out of Shanghai has not landed yet.
r = client.patch(f"/api/review/trip-plans/{plan}/stops/{paris}",
    json={"row_version": rv, "planned_date": "2026-09-14",
          "planned_start_period": "AM", "schedule_locked": True,
          "preferred_period": "auto", "confirmation_status": "confirmed"}, headers=H)
assert r.status_code == 200, r.text[:300]
r = client.post(f"/api/review/trip-plans/{plan}/preview-itinerary", json=payload, headers=H)
assert r.status_code == 200, r.text[:300]
missed = [x for x in r.json()["stops"] if x["id"] == paris][0]
assert (missed["planned_date"], missed["planned_start_period"]) == ("2026-09-14", "AM"), (
    "an appointment that cannot be made must stay where the customer put it, "
    f"got {missed['planned_date']} {missed['planned_start_period']}"
)
risks = {risk["kind"] for risk in r.json()["itinerary_summary"].get("risks") or []}
assert "cannot_reach_booked_visit" in risks, (
    f"a time the route cannot make must be reported: {risks}"
)

say("3c. 恢复 2026-09-16 上午的约定时间")
cur = client.get(f"/api/review/trip-plans/{plan}", headers=H).json()
rv = [s for s in cur["stops"] if s["id"] == paris][0]["row_version"]
r = client.patch(f"/api/review/trip-plans/{plan}/stops/{paris}",
    json={"row_version": rv, "planned_date": "2026-09-16",
          "planned_start_period": "AM", "schedule_locked": True,
          "preferred_period": "auto", "confirmation_status": "confirmed"}, headers=H)
assert r.status_code == 200, r.text[:300]

say("4. 保存路线")
r = client.post(f"/api/review/trip-plans/{plan}/generate-itinerary",
                json={**payload, "row_version": client.get(
                    f"/api/review/trip-plans/{plan}", headers=H).json()["row_version"]},
                headers=H)
assert r.status_code == 200, r.text[:300]
final = [x for x in r.json()["stops"] if x["id"] == paris][0]
assert (final["planned_date"], final["planned_start_period"]) == ("2026-09-16", "AM")
# The first save is where the end of the visit is written for the first time.
# Deriving it must not read as changing what the customer agreed to.
assert final["confirmation_status"] == "confirmed", (
    "the first save after an agreed time was entered downgraded it: "
    f"{final['confirmation_status']}"
)
assert final["planned_end_date"], "the end of the visit should now be recorded"

say("5. 已确认的约定时间不因别处改动而被降级")
# Confirm the agreed visit, then change the plan around it.
cur = client.get(f"/api/review/trip-plans/{plan}", headers=H).json()
rv = [s for s in cur["stops"] if s["id"] == paris][0]["row_version"]
r = client.patch(f"/api/review/trip-plans/{plan}/stops/{paris}", headers=H,
                 json={"row_version": rv, "confirmation_status": "confirmed"})
assert r.status_code == 200, r.text[:200]

conn = get_db()
extra_customer, extra_stop = generate_uuid(), generate_uuid()
conn.execute("INSERT INTO customers (id,display_name,normalized_name,lat,lng,"
             "created_at,updated_at,row_version) VALUES (?,'Munich','munich',"
             "48.1351,11.5820,?,?,1)", (extra_customer, stamp, stamp))
conn.commit()
close_db()

r = client.post(f"/api/review/trip-plans/{plan}/stops", headers=H,
                json={"customer_id": extra_customer})
assert r.status_code == 200, r.text[:200]
after_add = [s for s in r.json()["stops"] if s["id"] == paris][0]
assert after_add["confirmation_status"] == "confirmed", (
    "adding a customer elsewhere must not ask the customer to confirm again: "
    f"{after_add['confirmation_status']}"
)

def version():
    return client.get(f"/api/review/trip-plans/{plan}", headers=H).json()["row_version"]

r = client.post(f"/api/review/trip-plans/{plan}/generate-itinerary", headers=H,
                json={**payload, "row_version": version()})
assert r.status_code == 200, r.text[:300]
after_save = [s for s in r.json()["stops"] if s["id"] == paris][0]
assert after_save["confirmation_status"] == "confirmed", (
    "saving the route must not downgrade a time that did not move: "
    f"{after_save['confirmation_status']}"
)
assert (after_save["planned_date"], after_save["planned_start_period"]) == (
    "2026-09-16", "AM"
)

say("6. 计算移动了已确认的时间，才应要求重新确认")
# The case that warrants asking the customer again is the calculation moving a
# visit they had confirmed - not the user typing a new agreed date, which is
# them recording what the customer just told them.
frankfurt = stops["Frankfurt"]
# Release the Paris appointment first. An agreed time anchors the whole route
# to itself, so while it stands the other visits keep their days no matter
# what the trip dates say - which is the point of steps 3 to 5, not this one.
rv = [s for s in client.get(f"/api/review/trip-plans/{plan}", headers=H).json()["stops"]
      if s["id"] == paris][0]["row_version"]
r = client.patch(f"/api/review/trip-plans/{plan}/stops/{paris}", headers=H,
                 json={"row_version": rv, "schedule_locked": False,
                       "planned_time_accepted": False})
assert r.status_code == 200, r.text[:300]
rv = [s for s in client.get(f"/api/review/trip-plans/{plan}", headers=H).json()["stops"]
      if s["id"] == frankfurt][0]["row_version"]
r = client.patch(f"/api/review/trip-plans/{plan}/stops/{frankfurt}", headers=H,
                 json={"row_version": rv, "schedule_locked": False,
                       "confirmation_status": "confirmed"})
assert r.status_code == 200, r.text[:300]
before_move = [s for s in r.json()["stops"] if s["id"] == frankfurt][0]
assert before_move["confirmation_status"] == "confirmed"
assert before_move["planned_date"], "the visit needs a saved date to be moved from"

# Push the whole trip later, so an unlocked visit lands on a different day.
r = client.post(f"/api/review/trip-plans/{plan}/generate-itinerary", headers=H,
                json={**payload, "start_date": "2026-09-28",
                      "end_date": "2026-10-20", "row_version": version()})
assert r.status_code == 200, r.text[:300]
moved = [s for s in r.json()["stops"] if s["id"] == frankfurt][0]
assert moved["planned_date"] != before_move["planned_date"], (
    "the visit should have moved with the trip"
)
assert moved["confirmation_status"] == "needs_reconfirmation", (
    "a confirmed visit the route moved must be reconfirmed: "
    f"{moved['confirmation_status']}"
)

say("7. 约定时间保存后，结束时间必须跟着走")
# The UI sends only the start, because the end follows from the start and the
# length of the visit. Left behind, the stop reads as finishing before it began.
rv = [s for s in client.get(f"/api/review/trip-plans/{plan}", headers=H).json()["stops"]
      if s["id"] == paris][0]["row_version"]
r = client.patch(f"/api/review/trip-plans/{plan}/stops/{paris}", headers=H,
                 json={"row_version": rv, "planned_date": "2026-09-22",
                       "planned_start_period": "PM", "schedule_locked": True,
                       "planned_time_accepted": True})
assert r.status_code == 200, r.text[:300]
moved_end = [s for s in r.json()["stops"] if s["id"] == paris][0]
assert moved_end["planned_date"] == "2026-09-22"
assert moved_end["planned_end_date"] >= moved_end["planned_date"], (
    "a visit cannot end before it starts: "
    f"{moved_end['planned_date']} -> {moved_end['planned_end_date']}"
)
# The end is the start advanced by the visit's own length in half-days.
half_days = int(moved_end["duration_half_days"] or 2)
expected_day, expected_period = date(2026, 9, 22), "PM"
for _ in range(half_days - 1):
    if expected_period == "AM":
        expected_period = "PM"
    else:
        expected_day, expected_period = expected_day + timedelta(days=1), "AM"
assert (moved_end["planned_end_date"], moved_end["planned_end_period"]) == (
    expected_day.isoformat(), expected_period
), (
    f"{half_days} half-days from 2026-09-22 PM should end "
    f"{expected_day.isoformat()} {expected_period}, got "
    f"{moved_end['planned_end_date']} {moved_end['planned_end_period']}"
)
assert bool(moved_end["schedule_locked"]) is True

print("PASS: an agreed visit time is entered, saved and honoured by the route")
