"""Turn visible lead rows into one review-map group per customer."""

from __future__ import annotations


def _new_group(core, row: dict, country_code: str | None, region: str | None) -> dict:
    return {
        "customer_id": row["customer_id"],
        "customer_name": row["display_name"],
        "country": row.get("country"),
        "country_code": country_code,
        "country_name": core._country_name(country_code),
        "city": row.get("city"),
        "postal_code": row.get("postal_code"),
        "address": row.get("address"),
        "normalized_address": row.get("normalized_address"),
        "region": region,
        "raw_lat": row.get("lat"),
        "raw_lng": row.get("lng"),
        "geocode_source": row.get("geocode_source"),
        "geocode_confidence": row.get("geocode_confidence"),
        "geocode_locked": bool(row.get("geocode_locked")),
        "customer_row_version": row.get("customer_row_version"),
        "can_edit": bool(row.get("actor_can_edit")),
        "leads": [],
        "owners": {},
        "stages": set(),
        "total_won": 0.0,
    }


def _lead(row: dict) -> dict:
    return {
        "id": row["lead_id"],
        "display_id": row["display_id"],
        "title": row["title"],
        "sales_stage": row["sales_stage"],
        "service_status": row["service_status"],
        "owner_id": row["owner_id"],
        "owner_name": row.get("owner_name"),
        "estimated_value": float(row["estimated_value"]) if row.get("estimated_value") else 0,
        "deal_amount": float(row["deal_amount"]) if row.get("deal_amount") else 0,
        "currency": row.get("currency"),
        "product_category": row.get("product_category"),
        "application": row.get("application"),
        "next_followup_date": row.get("next_followup_date"),
        "updated_at": row["lead_updated_at"],
    }


def _append_row(group: dict, row: dict) -> None:
    group["can_edit"] = bool(group["can_edit"] or row.get("actor_can_edit"))
    group["leads"].append(_lead(row))
    group["stages"].add(row["sales_stage"])
    if row.get("owner_id"):
        group["owners"][row["owner_id"]] = row.get("owner_name") or row["owner_id"]
    if row["sales_stage"] == "Won" and row.get("deal_amount"):
        group["total_won"] += float(row["deal_amount"])


def group_map_rows(rows: list[dict], core, region_filter: str | None) -> dict[str, dict]:
    grouped = {}
    for row in rows:
        country_code = core._normalize_country(row.get("country"))
        region = row.get("region") or core._country_region(country_code)
        if region_filter and region != region_filter:
            continue
        customer_id = row["customer_id"]
        group = grouped.setdefault(
            customer_id, _new_group(core, row, country_code, region)
        )
        _append_row(group, row)
    return grouped
