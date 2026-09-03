"""The workbook visits are carried into the field in and reported back from.

It is a contract, not a view: every row says which plan and which stop it
belongs to, which version of that stop it was written from, and what each
writable field held at that moment. What comes back can then be compared with
what went out, so a result is only taken from a field somebody actually
changed.
"""

from __future__ import annotations

from uuid import uuid4

from .trip_export_labels import product_role, product_status
from .trip_export_visit import (
    _channel_partner_companions, _customer_personnel, _equipment, _topics,
)

FORMAT_VERSION = "JPT-TRIP-WORKING-1.0"

# Everything the people going need in front of them, read-only. Whoever walks
# into the meeting has to know what to bring and who else is coming, so the
# workbook carries the whole of the preparation and not a summary of it.
CONTEXT_HEADERS = [
    "序号 / No.", "客户 / Customer", "计划日期 / Planned date",
    "计划时段 / Planned period", "地点 / Place", "拜访目的 / Visit purpose",
    "客户人员 / Customer personnel",
    "渠道代理陪同 / Channel partner companions",
    "JPT 参会人员 / JPT participants",
    "演示设备 / Demo laser", "PO 设备 / PO laser", "其他设备 / Other equipment",
    "议题 / Topics",
]

# The twelve fields the field team writes, in the order they are filled in.
RESULT_COLUMNS = (
    ("结果状态 / Result status", "result_status"),
    ("实际拜访日期 / Actually visited on", "actual_visit_date"),
    ("实际时段 / Half-day", "actual_visit_period"),
    ("会议记录 / Meeting notes", "result_notes"),
    ("客户需求 / Customer needs", "visit_customer_needs"),
    ("竞争对手 / Competitor", "visit_competitor"),
    ("预算 / Budget", "visit_budget"),
    ("决策人 / Decision maker", "visit_decision_maker"),
    ("下一步行动 / Next action", "visit_next_action"),
    ("跟进截止 / Follow-up due", "visit_followup_due_date"),
    ("需要样品 / Sample needed", "visit_sample_needed"),
    ("需要报价 / Quote needed", "visit_quote_needed"),
)
RESULT_HEADERS = [header for header, _ in RESULT_COLUMNS]
RESULT_FIELDS = tuple(field for _, field in RESULT_COLUMNS)

# What each dropdown offers. "Not answered" is a choice of its own: a blank
# cell means the same thing, and neither means "no".
NOT_ANSWERED = "未填写 / Not answered"
ANSWER_CHOICES = (NOT_ANSWERED, "是 / Yes", "否 / No")
PERIOD_CHOICES = (NOT_ANSWERED, "AM", "PM")
STATUS_CHOICES = ("已计划 / Planned", "已拜访 / Visited",
                  "需要跟进 / Follow-up Needed", "已跳过 / Skipped")
DROPDOWNS = {
    "结果状态 / Result status": STATUS_CHOICES,
    "实际时段 / Half-day": PERIOD_CHOICES,
    "需要样品 / Sample needed": ANSWER_CHOICES,
    "需要报价 / Quote needed": ANSWER_CHOICES,
}
DATE_COLUMNS = ("实际拜访日期 / Actually visited on", "跟进截止 / Follow-up due")

# Which visit a row is about travels in the row itself. A row number cannot
# carry that: sorting, an inserted row or a swapped pair would leave the result
# under a different visit's number, and the import would file it against the
# wrong customer.
TOKEN_HEADER = "标识 / Row token"

# The file says which workbook it is and which row is which. It does not say
# which visit a token belongs to, nor what the row was exported holding: the
# issuing installation keeps that, because a file cannot vouch for itself.
# Anyone can unprotect a hidden sheet and rewrite it, and an import that
# believed it would file a result against another customer or hide a conflict.
KEY_HEADERS = ["行 / Row", TOKEN_HEADER]


def _answer(value) -> str:
    if value is None:
        return NOT_ANSWERED
    return "是 / Yes" if value else "否 / No"


def _period(value) -> str:
    return value if value in ("AM", "PM") else NOT_ANSWERED


def _printed(field: str, stop: dict):
    """What the workbook shows for one writable field."""
    value = stop.get(field)
    if field in ("visit_sample_needed", "visit_quote_needed"):
        return _answer(value)
    if field == "actual_visit_period":
        return _period(value)
    if field == "result_status":
        return next(
            (choice for choice in STATUS_CHOICES
             if choice.endswith(f"/ {value}")),
            STATUS_CHOICES[0],
        )
    return value if value not in (None, "") else ""


def _participants(briefing: dict) -> str:
    """Who from JPT is going, with what they are there to do."""
    lines = []
    for item in briefing.get("participants") or []:
        parts = [str(item.get("display_name") or "").strip()]
        if item.get("role"):
            parts.append(f"角色 / Role: {product_role(item['role'])}")
        for key, label in (
            ("responsibility", "负责 / Responsibility"), ("notes", "备注 / Notes"),
        ):
            if item.get(key):
                parts.append(f"{label}: {item[key]}")
        text = "; ".join(part for part in parts if part)
        if text:
            lines.append(text)
    return "\n".join(lines) or "无 / None"


def _place(stop: dict) -> str:
    location = stop.get("visit_location") or {}
    return location.get("full_address") or location.get("label") or ""


def visits_of(plan: dict) -> list[dict]:
    """The customer visits, in itinerary order.

    A hotel or an airport wait has no result to report, so it is not carried
    into the field workbook at all.
    """
    stops = [
        stop for stop in plan.get("stops") or []
        if stop.get("stop_kind") != "free"
    ]
    return sorted(stops, key=lambda stop: (stop.get("sequence_no") or 0))


WORKING_HEADERS = CONTEXT_HEADERS + RESULT_HEADERS + [TOKEN_HEADER]


def build_working_model(
    plan: dict, generated_at: str, workbook_id: str, token=None
) -> dict:
    """The field workbook: what to show, what may be written, what went out."""
    token = token or (lambda stop: uuid4().hex)
    rows, keys, manifest = [], [], []
    for number, stop in enumerate(visits_of(plan), start=1):
        row_token = token(stop)
        briefing = stop.get("briefing") or {}
        row = dict(zip(CONTEXT_HEADERS, (
            number,
            stop.get("customer_name") or "",
            stop.get("planned_date") or "",
            stop.get("planned_start_period") or "",
            _place(stop),
            stop.get("visit_purpose") or "",
            _customer_personnel(briefing),
            _channel_partner_companions(briefing),
            _participants(briefing),
            _equipment(briefing, "demo", "Demo Laser"),
            _equipment(briefing, "po", "PO Laser"),
            _equipment(briefing, "other", "Other Equipment"),
            _topics(stop, briefing),
        )))
        row.update({
            header: _printed(field, stop) for header, field in RESULT_COLUMNS
        })
        row[TOKEN_HEADER] = row_token
        rows.append(row)
        keys.append({"行 / Row": number, TOKEN_HEADER: row_token})
        manifest.append({
            "row_token": row_token,
            "stop_id": stop.get("id") or "",
            "row_version": int(stop.get("row_version") or 0),
            "baseline": {
                field: row[header] for header, field in RESULT_COLUMNS
            },
        })
    return {
        "format": FORMAT_VERSION,
        "workbook_id": workbook_id,
        "plan_id": plan.get("id"),
        "title": plan.get("title") or "出差计划",
        "generated_at": generated_at,
        "status": product_status(plan.get("status")),
        "headers": WORKING_HEADERS,
        "rows": rows,
        "keys": keys,
        # Never written into the file. Persisted where the file cannot reach.
        "manifest": manifest,
    }
