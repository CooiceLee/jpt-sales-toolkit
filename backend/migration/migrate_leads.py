"""
Step 3: Migrate legacy inquiries to leads table.

Each legacy Inquiry becomes one Lead.
- legacy_inquiry_id preserves the original ID
- display_id is regenerated with JPT-{YYMM}-{NNNN} rule
- owner_id resolved from assigned_sales via legacy_user_map
"""

from __future__ import annotations

import json
from datetime import datetime

from .base import (
    MigrationContext,
    generate_uuid,
    now_iso,
    safe_numeric,
    safe_date,
    empty_to_none,
)


STAGE_MAP = {
    "Inquiry": ("New", "Not Started", "None"),
    "Following": ("Following", "Not Started", "None"),
    "Sampling": ("Following", "Not Started", "None"),
    "Quoting": ("Quoted", "Not Started", "None"),
    "Closed Won": ("Won", "Not Started", "None"),
    "Fulfillment": ("Won", "In Progress", "None"),
    "After-sales": ("Won", "Completed", "Open"),
    "Closed Lost": ("Lost", "Not Started", "None"),
}

PRODUCTION_STATUS_MAP = {
    "Not Started": "Not Started",
    "In Production": "In Progress",
    "Completed": "Completed",
    "Shipped": "Completed",
}


def get_field_value(inquiry: dict, field_name: str):
    """Extract field value from legacy inquiry structure."""
    fields = inquiry.get("fields", {})
    field_data = fields.get(field_name, {})
    if isinstance(field_data, dict):
        return empty_to_none(field_data.get("value"))
    return empty_to_none(field_data)


def generate_display_id(ctx: MigrationContext, created_at: str) -> str:
    """Generate display_id in JPT-{YYMM}-{NNNN} format."""
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.utcnow()

    period_ym = dt.strftime("%y%m")

    # Get or create sequence
    row = ctx.conn.execute(
        "SELECT next_value FROM display_sequences WHERE period_ym = ?",
        (period_ym,),
    ).fetchone()

    if row:
        next_val = row[0]
        ctx.conn.execute(
            "UPDATE display_sequences SET next_value = ? WHERE period_ym = ?",
            (next_val + 1, period_ym),
        )
    else:
        next_val = 1
        ctx.conn.execute(
            "INSERT INTO display_sequences (period_ym, next_value) VALUES (?, ?)",
            (period_ym, 2),
        )

    return f"JPT-{period_ym}-{next_val:04d}"


def map_stages(inquiry: dict) -> tuple[str, str, str]:
    """Map legacy stage to new three-part status."""
    stage = get_field_value(inquiry, "stage") or "Inquiry"
    sales_stage, fulfillment_status, service_status = STAGE_MAP.get(
        stage, ("New", "Not Started", "None")
    )

    # Override fulfillment from production_status if present
    production_status = get_field_value(inquiry, "production_status")
    if production_status and production_status in PRODUCTION_STATUS_MAP:
        fulfillment_status = PRODUCTION_STATUS_MAP[production_status]

    # Set service_status if after_sales records exist
    after_sales = inquiry.get("after_sales", [])
    if after_sales:
        # Check if any are still open
        has_open = any(
            af.get("status") in ("Open", "In Progress")
            for af in after_sales
        )
        service_status = "Open" if has_open else "Resolved"

    return sales_stage, fulfillment_status, service_status


def build_extra_json(inquiry: dict) -> str:
    """Build extra_json from legacy fields not in main schema."""
    extra = {}
    extra_fields = [
        "special_requirements",
        "potential_needs",
        "products_detail",
        "assistant",
        "expected_delivery",
        "actual_delivery",
        "logistics_info",
    ]

    for field_name in extra_fields:
        value = get_field_value(inquiry, field_name)
        if value:
            extra[field_name] = value

    return json.dumps(extra) if extra else None


def migrate_leads(
    ctx: MigrationContext,
    inquiries: list[dict],
    inquiry_to_customer: dict[str, str],
) -> None:
    """Migrate all inquiries to leads."""
    for inquiry in inquiries:
        legacy_id = inquiry.get("inquiry_id", "")
        customer_id = inquiry_to_customer.get(legacy_id)

        if not customer_id:
            ctx.add_warning(legacy_id, "customer_id", "no_customer_match", "")
            continue

        # Resolve owner
        assigned_sales = get_field_value(inquiry, "assigned_sales")
        owner_mapping = ctx.legacy_user_map.get(assigned_sales or "", {})
        owner_id = owner_mapping.get("user_id")

        if not owner_id:
            # Fallback to created_by
            created_by = get_field_value(inquiry, "created_by")
            owner_mapping = ctx.legacy_user_map.get(created_by or "", {})
            owner_id = owner_mapping.get("user_id")

        if not owner_id:
            ctx.add_warning(legacy_id, "owner_id", "no_owner_found", assigned_sales)
            # Use first available user as fallback
            if ctx.legacy_user_map:
                owner_id = list(ctx.legacy_user_map.values())[0]["user_id"]
            else:
                continue

        created_at = inquiry.get("created_at") or now_iso()
        display_id = generate_display_id(ctx, created_at)
        sales_stage, fulfillment_status, service_status = map_stages(inquiry)

        lead_id = generate_uuid()

        # Validate numeric fields
        estimated_value = safe_numeric(get_field_value(inquiry, "estimated_value"))
        deal_amount = safe_numeric(get_field_value(inquiry, "deal_amount"))

        # Build title
        title = get_field_value(inquiry, "product_category") or "Inquiry"
        application = get_field_value(inquiry, "application")
        if application:
            title = f"{title} - {application}"

        ctx.conn.execute(
            """
            INSERT INTO leads (
                id, display_id, customer_id, legacy_inquiry_id, title,
                source_channel, original_email, owner_id,
                sales_stage, fulfillment_status, service_status,
                quality_grade, urgency, estimated_value,
                product_category, product_series, power_range, wavelength,
                application, material,
                currency, deal_amount, quotation_id, quotation_date,
                po_number, po_date, next_followup_date, inquiry_date,
                extra_json, created_at, created_by, updated_at, updated_by
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            (
                lead_id,
                display_id,
                customer_id,
                legacy_id,
                title,
                get_field_value(inquiry, "source_channel"),
                get_field_value(inquiry, "original_email"),
                owner_id,
                sales_stage,
                fulfillment_status,
                service_status,
                get_field_value(inquiry, "quality_rating"),
                get_field_value(inquiry, "urgency"),
                estimated_value,
                get_field_value(inquiry, "product_category"),
                get_field_value(inquiry, "product_series"),
                get_field_value(inquiry, "power_range"),
                get_field_value(inquiry, "wavelength"),
                application,
                get_field_value(inquiry, "material"),
                get_field_value(inquiry, "currency"),
                deal_amount,
                get_field_value(inquiry, "quotation_id"),
                safe_date(get_field_value(inquiry, "quotation_date")),
                get_field_value(inquiry, "po_number"),
                safe_date(get_field_value(inquiry, "po_date")),
                safe_date(get_field_value(inquiry, "next_followup_date")),
                safe_date(get_field_value(inquiry, "inquiry_date")),
                build_extra_json(inquiry),
                created_at,
                owner_id,
                now_iso(),
                owner_id,
            ),
        )

        # Create owner assignment record
        ctx.conn.execute(
            """
            INSERT INTO lead_assignments (id, lead_id, user_id, assignment_type, created_at, created_by)
            VALUES (?, ?, ?, 'owner', ?, ?)
            """,
            (generate_uuid(), lead_id, owner_id, now_iso(), owner_id),
        )

        ctx.legacy_id_map[legacy_id] = lead_id
        ctx.stats["leads_created"] += 1

    ctx.conn.commit()
