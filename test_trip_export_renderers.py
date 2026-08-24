"""Focused format checks for the formal trip export renderers."""

from __future__ import annotations

import io
from xml.etree import ElementTree
from zipfile import ZipFile

from backend.services.trip_export_html import render_trip_html
from backend.services.trip_export_ics import render_trip_ics
from backend.services.trip_export_model import build_trip_export_model
from backend.services.trip_export_xlsx import render_trip_xlsx


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

    ics = render_trip_ics(model, plan["schedule_items"]).decode()
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == len(plan["schedule_items"])
    assert ics.count("DTSTAMP:") == len(plan["schedule_items"])
    assert "DTSTART;VALUE=DATE:20260929" in ics and "[PM]" in ics
    assert "T090000" not in ics and "Rome" in ics and "Shanghai" in ics
    print("PASS: formal trip XLSX, offline HTML, and all-day ICS renderers")


if __name__ == "__main__":
    run()
