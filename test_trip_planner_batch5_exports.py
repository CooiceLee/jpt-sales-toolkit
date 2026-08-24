"""Batch 5 formal trip export acceptance tests.

The existing Batch 4 fixture supplies realistic visit briefings and always
redirects the application to a temporary desktop profile.
"""

from __future__ import annotations

import html
import io
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

import test_trip_planner_batch4 as fixture


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
EXPECTED_SHEETS = ["拜访计划", "完整日程", "交通行程"]
REFERENCE_HEADERS = [
    "No.",
    "Company Name",
    "Full Address",
    "Recommended Visit Date",
    "Demo Laser",
    "PO Laser",
    "客户人员 / Customer Personnel",
    "渠道代理公司陪同人员（如有） / Channel Partner Companions (if any)",
    "Visiting topic",
]


def _xlsx_text(content: bytes) -> tuple[list[str], dict[str, str], str]:
    """Return workbook sheet names, visible text by sheet, and style XML."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        required = {
            "[Content_Types].xml",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/styles.xml",
        }
        assert required <= names
        assert not any(name.startswith("xl/externalLinks/") for name in names)
        for name in names:
            if not name.endswith(".rels"):
                continue
            root = ET.fromstring(archive.read(name))
            for rel in root.findall("r:Relationship", REL_NS):
                target = rel.attrib.get("Target", "")
                assert not target.startswith(("http://", "https://")), (name, target)

        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root.findall("m:si", NS)]

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rels = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rel_root}
        sheets = []
        texts: dict[str, str] = {}
        rel_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        for sheet in workbook.find("m:sheets", NS):
            sheet_name = sheet.attrib["name"]
            sheets.append(sheet_name)
            target = rels[sheet.attrib[rel_key]].lstrip("/")
            path = target if target.startswith("xl/") else f"xl/{target}"
            root = ET.fromstring(archive.read(path))
            values = []
            for cell in root.findall(".//m:c", NS):
                kind = cell.attrib.get("t")
                if kind == "inlineStr":
                    values.append("".join(cell.itertext()))
                else:
                    value = cell.findtext("m:v", default="", namespaces=NS)
                    if kind == "s" and value:
                        value = shared[int(value)]
                    values.append(value)
            texts[sheet_name] = "\n".join(values)

            pane = root.find("m:sheetViews/m:sheetView/m:pane", NS)
            assert pane is not None and pane.attrib.get("state") == "frozen", sheet_name
            assert root.find("m:autoFilter", NS) is not None, sheet_name
            page_setup = root.find("m:pageSetup", NS)
            assert page_setup is not None
            assert page_setup.attrib.get("orientation") == "landscape", sheet_name
        return sheets, texts, archive.read("xl/styles.xml").decode("utf-8")


def _unfold_ics(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        elif line:
            lines.append(line)
    return lines


def _events(text: str) -> list[list[str]]:
    events: list[list[str]] = []
    active: list[str] | None = None
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            active = []
        elif line == "END:VEVENT":
            assert active is not None
            events.append(active)
            active = None
        elif active is not None:
            active.append(line)
    return events


def _prepare_plan(client: TestClient, ctx: dict) -> dict:
    plan = fixture._create_plan(client, ctx, "德国法国客户拜访 <script>alert(1)</script>")
    plan = fixture._add_stop(client, ctx, plan, "rayxion")
    stop = plan["stops"][0]
    briefing = fixture._require(
        client.get(
            fixture._briefing_url(plan["id"], stop["id"]),
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    saved = fixture._require(
        client.put(
            fixture._briefing_url(plan["id"], stop["id"]),
            headers=ctx["headers"]["owner"],
            json=fixture._full_briefing_payload(
                briefing["row_version"], briefing["stop_row_version"], ctx
            ),
        ),
        200,
    )
    confirm = fixture._writable_briefing(saved)
    confirm["confirmation_status"] = "confirmed"
    fixture._require(
        client.put(
            fixture._briefing_url(plan["id"], stop["id"]),
            headers=ctx["headers"]["owner"],
            json=confirm,
        ),
        200,
    )
    plan = fixture._require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    plan = fixture._require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/free-stops",
            headers=ctx["headers"]["owner"],
            json={
                "category": "hotel",
                "location_name": "里昂休息站 & 行前准备",
                "address": "10 Rest Avenue",
                "city": "Lyon",
                "country": "France",
                "lat": 45.764,
                "lng": 4.8357,
                "duration_half_days": 1,
                "visit_purpose": "休息并准备下一次拜访",
            },
        ),
        200,
    )
    durations = {
        stop["id"]: {"half_days": 1, "preferred_period": "auto", "locked": False}
        for stop in plan["stops"]
    }
    return fixture._require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"]["owner"],
            json=fixture._route_payload(plan, durations),
        ),
        200,
    )


def check_exports(client: TestClient, ctx: dict) -> None:
    plan = _prepare_plan(client, ctx)
    base = f"/api/review/trip-plans/{plan['id']}/export"
    before = fixture._snapshot()
    responses = {
        extension: client.get(
            f"{base}.{extension}", headers=ctx["headers"]["owner"]
        )
        for extension in ("xlsx", "html", "ics")
    }
    assert fixture._snapshot() == before, "downloads must not write business data"
    for extension, response in responses.items():
        assert response.status_code == 200, (extension, response.text)
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition.lower()
        assert f".{extension}" in disposition.lower()
    artifact_dir = os.getenv("JPT_BATCH5_ARTIFACT_DIR")
    if artifact_dir:
        output = Path(artifact_dir)
        output.mkdir(parents=True, exist_ok=True)
        for extension, response in responses.items():
            (output / f"batch5-trip-export.{extension}").write_bytes(response.content)

    xlsx = responses["xlsx"]
    assert xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    sheets, texts, style_xml = _xlsx_text(xlsx.content)
    assert sheets == EXPECTED_SHEETS
    for header in REFERENCE_HEADERS:
        assert header in texts["拜访计划"], header
    for value in (
        "RAYXION (레이시온)",
        "99 Demo Avenue",
        "CW 2000W",
        "FC 500W",
        "Yeo-hun Son",
        "Kim Sungkyu",
        "Anna Becker",
        "Introduce JPT and RAYXION",
    ):
        assert value in texts["拜访计划"], value
    assert "Aydan Tech" not in texts["拜访计划"]
    for value in ("客户拜访", "个人安排", "交通", "里昂休息站"):
        assert value in texts["完整日程"], value
    assert plan["destination_name"] in texts["交通行程"]
    assert 'wrapText="1"' in style_xml
    joined_workbook_text = "\n".join(texts.values())
    assert "MISSING" not in joined_workbook_text
    assert "待补充" in joined_workbook_text
    assert "FF8B2347" in style_xml.upper(), "XLSX must keep the JPT wine accent"
    for internal_value in (
        "needs_reconfirmation",
        "unconfirmed",
        "heuristic_estimate_confirm_manually",
        "User ID:",
        "Contact ID:",
    ):
        assert internal_value not in joined_workbook_text, internal_value
    for product_text in ("需重新确认", "未确认", "自驾", "估算"):
        assert product_text in joined_workbook_text, product_text

    html_response = responses["html"]
    assert html_response.headers["content-type"].startswith("text/html")
    page = html_response.text
    assert re.search(r"<html[^>]+lang=[\"']zh-CN[\"']", page, re.I)
    assert "@media print" in page
    assert "<style" in page and "<script" not in page.lower()
    assert "window.print()" in page
    assert not re.search(r"(?:src|href)=[\"'](?:https?:)?//", page, re.I)
    assert "<script>alert(1)</script>" not in page
    assert html.escape("<script>alert(1)</script>") in page
    for title in EXPECTED_SHEETS:
        assert title in page, title
    assert "里昂休息站 &amp; 行前准备" in page
    assert "MISSING" not in page
    assert "待补充" in page
    assert "#8b2347" in page.lower(), "HTML must keep the JPT wine accent"
    for internal_value in (
        "needs_reconfirmation",
        "unconfirmed",
        "heuristic_estimate_confirm_manually",
        "User ID:",
        "Contact ID:",
    ):
        assert internal_value not in page, internal_value

    ics = responses["ics"]
    assert ics.headers["content-type"].startswith("text/calendar")
    calendar = ics.text
    assert calendar.startswith("BEGIN:VCALENDAR")
    assert calendar.rstrip().endswith("END:VCALENDAR")
    events = _events(calendar)
    assert len(events) == len(plan["schedule_items"])
    uids = []
    for event in events:
        uid = next(line[4:] for line in event if line.startswith("UID:"))
        uids.append(uid)
        assert any(line.startswith("DTSTAMP:") for line in event)
        assert any(line.startswith("DTSTART;VALUE=DATE:") for line in event)
        assert any(line.startswith("DTEND;VALUE=DATE:") for line in event)
        summary = next(line for line in event if line.startswith("SUMMARY:"))
        assert "AM" in summary or "PM" in summary
        assert not any(re.search(r"DTSTART.*T\d{6}", line) for line in event)
    assert len(uids) == len(set(uids))
    assert "RAYXION" in calendar
    assert "里昂休息站" in calendar
    assert plan["destination_name"] in calendar
    for internal_value in (
        "needs_reconfirmation",
        "unconfirmed",
        "heuristic_estimate_confirm_manually",
    ):
        assert internal_value not in calendar, internal_value
    repeated = client.get(f"{base}.ics", headers=ctx["headers"]["owner"])
    repeated_uids = [
        next(line[4:] for line in event if line.startswith("UID:"))
        for event in _events(repeated.text)
    ]
    assert repeated_uids == uids, "calendar UIDs must be stable"

    for extension in responses:
        assert client.get(
            f"{base}.{extension}", headers=ctx["headers"]["other"]
        ).status_code == 404

    stale = fixture._require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"]["owner"],
            json={"row_version": plan["row_version"], "travel_mode": "ground_public"},
        ),
        200,
    )
    assert stale["itinerary_summary"]["stale"] is True
    for extension in responses:
        blocked = client.get(
            f"{base}.{extension}", headers=ctx["headers"]["owner"]
        )
        assert blocked.status_code == 400, (extension, blocked.text)
        assert "out of date" in blocked.text.lower()


def run() -> None:
    try:
        with TestClient(fixture.app) as client:
            check_exports(client, fixture._seed(client))
        print(
            "PASS: Batch 5 XLSX, offline HTML, calendar, permissions, "
            "stale-route guards, and zero-write downloads"
        )
    finally:
        fixture.close_db()
        shutil.rmtree(fixture.TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
