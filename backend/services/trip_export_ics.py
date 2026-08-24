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


def _uid(model: dict, item: dict) -> str:
    value = "|".join(str(item.get(key) or "") for key in (
        "slot_key", "item_type", "source_id", "half_day_index",
    ))
    digest = sha256(f"{model['plan_id']}|{value}".encode()).hexdigest()[:24]
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


def render_trip_ics(model: dict, schedule_items: list[dict]) -> bytes:
    rows = model["timeline"]
    generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JPT//Sales Toolkit//ZH-CN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(model['title'])}",
    ]
    for item, row in zip(schedule_items, rows):
        start = date.fromisoformat(str(item["date"]))
        summary = f"[{item.get('period') or '-'}] {row.get('类型 / Type') or ''} · {item.get('title') or ''}"
        event = [
            "BEGIN:VEVENT", f"UID:{_uid(model, item)}", f"DTSTAMP:{generated_at}",
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
