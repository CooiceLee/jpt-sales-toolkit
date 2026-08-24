"""Shared read model for distributable trip-plan exports."""

from __future__ import annotations

from typing import Callable

from .trip_export_labels import (
    product_basis, product_category, product_mode, product_region, product_status,
)
from .trip_export_visit import (
    CHANNEL_PARTNER_COMPANIONS_HEADER,
    CUSTOMER_PERSONNEL_HEADER,
    formal_visit_row,
)


VISIT_HEADERS = [
    "No.", "Company Name", "Full Address", "Recommended Visit Date",
    "Demo Laser", "PO Laser", "Other Equipment", CUSTOMER_PERSONNEL_HEADER,
    CHANNEL_PARTNER_COMPANIONS_HEADER, "Visiting topic",
]
TIMELINE_HEADERS = [
    "序号 / No.", "日期 / Date", "时段 / Period", "类型 / Type",
    "分类 / Category", "地点 / Place", "地址 / Address", "事项 / Item", "目的 / Purpose",
    "交通 / Mode", "距离 / Distance km", "时长 / Time hours",
    "确认状态 / Status", "备注 / Notes",
]
LEG_HEADERS = [
    "序号 / No.", "出发地 / From", "目的地 / To", "交通方式 / Mode",
    "距离 / Distance km", "预计时长 / Time hours", "开始 / Start",
    "结束 / End", "占用半天数 / Half-days", "确认依据 / Basis",
    "备注 / Notes",
]


def _text(value) -> str:
    return "" if value is None else str(value)


def _first(*values):
    return next((value for value in values if value is not None), None)


def _missing_to_product_text(value) -> str:
    text = _text(value)
    if text.startswith("MISSING:"):
        return f"待补充 / To complete: {text.split(':', 1)[1].strip()}"
    return text


def _address(stop: dict) -> str:
    location = stop.get("visit_location") or {}
    if location.get("full_address"):
        return _text(location["full_address"])
    return ", ".join(
        _text(location.get(key, stop.get(key)))
        for key in ("address", "city", "postal_code", "country")
        if location.get(key, stop.get(key))
    )


def _slot(value: dict, prefix: str = "planned_start") -> str:
    return " ".join(
        _text(value.get(key))
        for key in (f"{prefix}_date", f"{prefix}_period")
        if value.get(key)
    )


def _timeline_rows(plan: dict) -> list[dict]:
    stops = {stop.get("id"): stop for stop in plan.get("stops") or []}
    legs = {leg.get("leg_key"): leg for leg in plan.get("legs") or []}
    rows = []
    type_labels = {"customer": "客户拜访 / Customer visit", "free": "个人安排 / Personal stop", "leg": "交通 / Travel"}
    for item in plan.get("schedule_items") or []:
        stop = stops.get(item.get("source_id"), {})
        leg = legs.get(item.get("source_id"), {})
        kind = item.get("item_type")
        place = (
            (stop.get("visit_location") or {}).get("label")
            or stop.get("location_name") or stop.get("customer_name")
            or item.get("title")
        )
        rows.append(dict(zip(TIMELINE_HEADERS, (
            item.get("schedule_index"), item.get("date"), item.get("period"),
            type_labels.get(kind, _text(kind)), product_category(stop.get("category")),
            place, _address(stop),
            item.get("title"), stop.get("visit_purpose"),
            product_mode(item.get("selected_mode") or leg.get("selected_mode") or leg.get("mode")),
            _first(item.get("distance_km"), leg.get("distance_km")),
            _first(item.get("time_hours"), leg.get("time_hours")),
            product_status(item.get("confirmation_status")), stop.get("notes") or leg.get("notes"),
        ))))
    return rows


def _leg_rows(plan: dict, confirmation: Callable[[dict], str]) -> list[dict]:
    rows = []
    for leg in plan.get("legs") or []:
        rows.append(dict(zip(LEG_HEADERS, (
            leg.get("sequence_no"), leg.get("from_label") or leg.get("from"),
            leg.get("to_label") or leg.get("to"),
            product_mode(leg.get("selected_mode") or leg.get("mode")), leg.get("distance_km"),
            leg.get("time_hours"), _slot(leg), _slot(leg, "planned_end"),
            leg.get("travel_half_days"), product_basis(confirmation(leg)), leg.get("notes"),
        ))))
    return rows


def build_trip_export_model(
    plan: dict,
    leg_confirmation: Callable[[dict], str],
) -> dict:
    """Build one format-neutral export model from an authorized fresh plan."""
    visits = []
    customer_stops = [
        stop for stop in plan.get("stops") or [] if stop.get("stop_kind") != "free"
    ]
    for number, stop in enumerate(customer_stops, start=1):
        row = formal_visit_row(stop, number)
        visits.append({key: _missing_to_product_text(row.get(key)) for key in VISIT_HEADERS})
    summary = plan.get("itinerary_summary") or {}
    metadata = [
        ("行程名称 / Trip", plan.get("title")),
        ("日期 / Date", f"{plan.get('start_date') or '-'} — {plan.get('end_date') or '-'}"),
        ("地区 / Region", product_region(plan.get("region"))),
        ("负责人 / Owner", plan.get("owner_name")),
        ("出发 / Origin", plan.get("origin_name")),
        ("出发窗口 / Departure", f"{plan.get('departure_window_start') or '-'} — {plan.get('departure_window_end') or '-'}"),
        ("返回 / Return", plan.get("destination_name")),
        ("返回窗口 / Return window", f"{plan.get('return_window_start') or '-'} — {plan.get('return_window_end') or '-'}"),
        ("预计结束 / Calculated end", " ".join(_text(value) for value in (summary.get("calculated_end_date"), summary.get("calculated_end_period")) if value)),
        ("总里程 / Distance km", summary.get("total_distance_km")),
        ("预计交通时长 / Travel hours", summary.get("total_travel_hours")),
        ("行程说明 / Notes", plan.get("description")),
    ]
    return {
        "plan_id": plan.get("id"), "title": plan.get("title") or "出差计划",
        "metadata": metadata, "visits": visits,
        "timeline": _timeline_rows(plan),
        "legs": _leg_rows(plan, leg_confirmation),
    }
