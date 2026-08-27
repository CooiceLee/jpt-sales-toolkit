"""An agreed visit time, entered the way the browser enters it, decides the route.

This is the workflow the module exists for: record what the customer agreed, and
get an itinerary built around it. It goes through the real HTTP endpoints with the
payload the frontend actually sends, because the pieces were all present and the
chain was broken in the browser - the preview request carried a field the endpoint
rejects, and there was nowhere to enter the time in the first place.
"""
import json, os, sys, tempfile
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
  VALUES (?,?,?,?,?,?,'auto',?,?,?,?,?,?,?,1,'Draft','legacy',?,?,?,?,1)""",
  (plan,"E2E trip",actor,"2026-09-14","2026-09-30","flight",
   '["flight","drive"]',"Shanghai",31.2304,121.4737,"Shanghai",31.2304,121.4737,
   stamp,actor,stamp,actor))
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
from backend.repositories import close_db; close_db()

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

say("3. 重新预览：路线是否围绕约定时间安排")
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
risks = {risk["kind"] for risk in r.json()["itinerary_summary"].get("risks") or []}
assert "cannot_reach_booked_visit" in risks, (
    f"a time the route cannot make must be reported: {risks}"
)

say("4. 保存路线")
r = client.post(f"/api/review/trip-plans/{plan}/generate-itinerary",
                json={**payload, "row_version": client.get(
                    f"/api/review/trip-plans/{plan}", headers=H).json()["row_version"]},
                headers=H)
assert r.status_code == 200, r.text[:300]
final = [x for x in r.json()["stops"] if x["id"] == paris][0]
assert (final["planned_date"], final["planned_start_period"]) == ("2026-09-16", "AM")
print("PASS: an agreed visit time is entered, saved and honoured by the route")
