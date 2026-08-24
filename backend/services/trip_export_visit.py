"""Reference-compatible customer visit rows for formal trip exports."""

from __future__ import annotations

from .trip_export_labels import product_role, product_status


CUSTOMER_PERSONNEL_HEADER = "客户人员 / Customer Personnel"
CHANNEL_PARTNER_COMPANIONS_HEADER = (
    "渠道代理公司陪同人员（如有） / Channel Partner Companions (if any)"
)


def _missing(label: str) -> str:
    return f"待补充 / To complete: {label}"


def _readable(item: dict, fields: tuple[tuple[str, str | None], ...]) -> str:
    parts = []
    for key, label in fields:
        value = item.get(key)
        if value in (None, ""):
            continue
        if key == "role":
            value = product_role(value)
        parts.append(f"{label}: {value}" if label else str(value))
    return "; ".join(parts)


def _equipment(briefing: dict, kind: str, label: str) -> str:
    rows = []
    for item in briefing.get("equipment") or []:
        if item.get("kind") != kind:
            continue
        text = " / ".join(
            str(value) for value in (
                item.get("model"), item.get("specification"), item.get("quantity"),
                item.get("owner_team"), item.get("notes"),
            ) if value
        )
        if text:
            rows.append(text)
    return "\n".join(rows) or _missing(label)


def _customer_personnel(briefing: dict) -> str:
    rows = []
    customer_fields = (
        ("name", None), ("title", "职务 / Title"), ("phone", "电话 / Phone"),
        ("email", "邮箱 / Email"), ("notes", "备注 / Notes"),
    )
    contact_fields = (
        ("name", None), ("position", "职务 / Position"),
        ("role", "角色 / Role"), ("phone", "电话 / Phone"),
        ("email", "邮箱 / Email"), ("notes", "备注 / Notes"),
    )
    for item in briefing.get("customer_team") or []:
        if text := _readable(item, customer_fields):
            rows.append(text)
    for item in briefing.get("contacts") or []:
        if text := _readable(item, contact_fields):
            rows.append(text)
    return "\n".join(rows) or _missing("Customer Personnel")


def _channel_partner_companions(briefing: dict) -> str:
    fields = (
        ("company_name", "公司 / Company"),
        ("name", None), ("position", "职务 / Position"), ("role", "角色 / Role"),
        ("phone", "电话 / Phone"), ("email", "邮箱 / Email"),
        ("notes", "备注 / Notes"),
    )
    rows = [
        text
        for item in briefing.get("channel_partner_companions") or []
        if (text := _readable(item, fields))
    ]
    return "\n".join(rows) or "无 / None"


def _topics(stop: dict, briefing: dict) -> str:
    rows = []
    for item in briefing.get("agenda_items") or []:
        parts = [str(item["topic"])] if item.get("topic") else []
        for key, label in (
            ("owner", "负责人 / Owner"), ("preparation", "准备事项 / Preparation"),
            ("expected_outcome", "预期结果 / Expected outcome"),
        ):
            if item.get(key):
                parts.append(f"{label}: {item[key]}")
        if parts:
            rows.append(" | ".join(parts))
    if not rows and stop.get("visit_purpose"):
        rows.append(str(stop["visit_purpose"]))
    return "\n".join(rows) or _missing("Visiting topic")


def _date(stop: dict, briefing: dict) -> str:
    start = " ".join(str(value) for value in (stop.get("planned_date"), stop.get("planned_start_period")) if value)
    end = " ".join(str(value) for value in (stop.get("planned_end_date"), stop.get("planned_end_period")) if value)
    value = start
    if end and end != start:
        value = f"{start} — {end}".strip(" —")
    return " | ".join((
        value or _missing("Recommended Visit Date"),
        f"确认状态 / Status: {product_status(stop.get('confirmation_status') or 'unconfirmed')}",
        f"时区 / Timezone: {briefing.get('timezone') or _missing('Timezone')}",
    ))


def formal_visit_row(stop: dict, number: int) -> dict:
    briefing = stop.get("briefing") or {}
    location = stop.get("visit_location") or {}
    return {
        "No.": number,
        "Company Name": stop.get("customer_name") or _missing("Company Name"),
        "Full Address": location.get("full_address") or _missing("Full Address"),
        "Recommended Visit Date": _date(stop, briefing),
        "Demo Laser": _equipment(briefing, "demo", "Demo Laser"),
        "PO Laser": _equipment(briefing, "po", "PO Laser"),
        "Other Equipment": _equipment(briefing, "other", "Other Equipment"),
        CUSTOMER_PERSONNEL_HEADER: _customer_personnel(briefing),
        CHANNEL_PARTNER_COMPANIONS_HEADER: _channel_partner_companions(briefing),
        "Visiting topic": _topics(stop, briefing),
    }
