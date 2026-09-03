"""RFC 5545 calendar export without invented clock times."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256


def _escape(value) -> str:
    return str(value or "").replace("\r", "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    lines, current = [], ""
    limit = 73
    for char in line:
        if current and len((current + char).encode("utf-8")) > limit:
            lines.append(current)
            current = " " + char
            limit = 74
        else:
            current += char
    lines.append(current)
    return lines


def _uid(model: dict, key: str) -> str:
    """The lasting name of one event.

    Built from what the plan records, so a visit that moves, is renamed, is
    travelled to differently or is attended by somebody else keeps its event
    rather than leaving the old one behind and adding a second.
    """
    digest = sha256(f"{model['plan_id']}|{key}".encode()).hexdigest()[:24]
    return f"{digest}@jpt-sales-toolkit"


def _description(row: dict) -> str:
    parts = []
    for label in (
        "类型 / Type", "分类 / Category", "地点 / Place", "地址 / Address", "目的 / Purpose",
        "交通 / Mode", "距离 / Distance km", "时长 / Time hours",
        "确认状态 / Status", "备注 / Notes",
    ):
        if row.get(label) not in (None, ""):
            parts.append(f"{label}: {row[label]}")
    return "\n".join(parts)


SNAPSHOT_NOTE = (
    "本文件是该出差计划在导出时刻的完整快照。计划有变更时请先删除上次导入的"
    "本日历，再导入新文件；本文件不包含删除或改派记录。 / "
    "A complete snapshot of this trip plan at the time of export. When the plan "
    "changes, remove the calendar imported last time before importing the new "
    "file: cancellations and reassignments are not carried in it."
)


def render_trip_ics(model: dict) -> bytes:
    """A complete snapshot of the trip, as a calendar.

    Every traveller's place in the itinerary is an event that says whose it is.
    Two colleagues on one flight are two events at the same hour, which is what
    each of their days actually contains.

    It is a snapshot, not a feed. An event keeps its name when the visit moves,
    is renamed, is travelled to differently, or when colleagues split up or
    start travelling together - so importing again updates those. What a
    snapshot cannot express is something that is no longer there: a visit
    deleted, shortened, or reassigned to somebody else leaves the event it used
    to have with no instruction to remove it. Saying so in the file is honest;
    claiming the import always tidies up after itself would not be.
    """
    # One entry per traveller, not the merged lines the documents print: a
    # calendar keeps one event per name, and naming events per traveller means
    # colleagues splitting up or starting to travel together changes how the
    # document groups them without changing whose event is whose.
    rows = model.get("calendar") or model["timeline"]
    generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JPT//Sales Toolkit//ZH-CN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(model['title'])}",
        f"X-WR-CALDESC:{_escape(SNAPSHOT_NOTE)}",
    ]
    for row in rows:
        key = row.get("_key") or ""
        start = date.fromisoformat(str(row["日期 / Date"]))
        travellers = row.get("出行人 / Travellers") or ""
        summary = " · ".join(part for part in (
            f"[{row.get('时段 / Period') or '-'}]",
            row.get("类型 / Type") or "",
            row.get("事项 / Item") or "",
            travellers,
        ) if part)
        event = [
            "BEGIN:VEVENT", f"UID:{_uid(model, key)}", f"DTSTAMP:{generated_at}",
            f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(start + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_escape(summary)}", f"DESCRIPTION:{_escape(_description(row))}",
        ]
        if row.get("地点 / Place"):
            event.append(f"LOCATION:{_escape(row['地点 / Place'])}")
        event.extend(("TRANSP:TRANSPARENT", "END:VEVENT"))
        lines.extend(event)
    lines.append("END:VCALENDAR")
    return ("\r\n".join(part for line in lines for part in _fold(line)) + "\r\n").encode("utf-8")
