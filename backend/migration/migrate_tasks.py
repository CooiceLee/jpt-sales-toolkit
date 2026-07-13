"""
Step 5: Migrate legacy after_sales[] and sample fields to tasks tables.

- after_sales[] -> after_sales_tasks
- sample_* fields -> pre_sales_tasks (one task per inquiry if any sample field exists)
"""

from __future__ import annotations

import json

from .base import MigrationContext, generate_uuid, now_iso, empty_to_none


def migrate_after_sales_tasks(ctx: MigrationContext, inquiries: list[dict]) -> None:
    """Migrate after_sales[] to after_sales_tasks table."""
    for inquiry in inquiries:
        legacy_id = inquiry.get("inquiry_id", "")
        lead_id = ctx.legacy_id_map.get(legacy_id)

        if not lead_id:
            continue

        after_sales = inquiry.get("after_sales", [])
        for af in after_sales:
            # Resolve assignee from technician
            tech_legacy_id = af.get("technician")
            assignee_mapping = ctx.legacy_user_map.get(tech_legacy_id or "", {})
            assignee_id = assignee_mapping.get("user_id")

            # Resolve created_by
            created_by_legacy = af.get("_updated_by") or af.get("_created_by")
            created_by_mapping = ctx.legacy_user_map.get(created_by_legacy or "", {})
            created_by = created_by_mapping.get("user_id")

            # Map issue_type
            issue_type = af.get("issue_type", "Other")
            if issue_type not in ("Technical", "Quality", "Delivery", "Other"):
                issue_type = "Other"

            # Map status
            status = af.get("status", "Open")
            if status not in ("Open", "In Progress", "Resolved", "Closed"):
                status = "Open"

            created_at = af.get("issue_date") or af.get("_created_at") or now_iso()
            if "T" not in created_at:
                created_at = f"{created_at}T00:00:00"

            ctx.conn.execute(
                """
                INSERT INTO after_sales_tasks (
                    id, lead_id, assignee_id, issue_type, status,
                    issue_description, solution, created_at, created_by,
                    updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generate_uuid(),
                    lead_id,
                    assignee_id,
                    issue_type,
                    status,
                    empty_to_none(af.get("issue_description")) or "Migrated issue",
                    empty_to_none(af.get("solution")),
                    created_at,
                    created_by,
                    now_iso(),
                    created_by,
                ),
            )
            ctx.stats["after_sales_tasks_created"] += 1


def get_field_value(inquiry: dict, field_name: str):
    """Extract field value from legacy inquiry structure."""
    fields = inquiry.get("fields", {})
    field_data = fields.get(field_name, {})
    if isinstance(field_data, dict):
        return empty_to_none(field_data.get("value"))
    return empty_to_none(field_data)


def migrate_pre_sales_tasks(ctx: MigrationContext, inquiries: list[dict]) -> None:
    """Migrate sample_* fields to pre_sales_tasks table."""
    sample_fields = [
        "sample_requested",
        "sample_request_date",
        "pre_sales_owner",
        "sample_params",
        "sample_report_link",
        "sample_result",
        "sample_confirmed_date",
    ]

    for inquiry in inquiries:
        legacy_id = inquiry.get("inquiry_id", "")
        lead_id = ctx.legacy_id_map.get(legacy_id)

        if not lead_id:
            continue

        # Check if any sample field exists
        has_sample_data = any(
            get_field_value(inquiry, field) for field in sample_fields
        )

        if not has_sample_data:
            continue

        # Resolve assignee from pre_sales_owner
        owner_legacy_id = get_field_value(inquiry, "pre_sales_owner")
        assignee_mapping = ctx.legacy_user_map.get(owner_legacy_id or "", {})
        assignee_id = assignee_mapping.get("user_id")

        # Resolve created_by
        created_by_legacy = get_field_value(inquiry, "created_by")
        created_by_mapping = ctx.legacy_user_map.get(created_by_legacy or "", {})
        created_by = created_by_mapping.get("user_id")

        # Build request_json
        request_json = {
            "sample_requested": get_field_value(inquiry, "sample_requested"),
            "sample_params": get_field_value(inquiry, "sample_params"),
        }
        request_json = {k: v for k, v in request_json.items() if v is not None}

        # Build result_json
        result_json = {
            "result": get_field_value(inquiry, "sample_result"),
            "report_link": get_field_value(inquiry, "sample_report_link"),
            "sample_confirmed_date": get_field_value(inquiry, "sample_confirmed_date"),
        }
        result_json = {k: v for k, v in result_json.items() if v is not None}

        # Determine status from sample_result
        sample_result = get_field_value(inquiry, "sample_result")
        if sample_result in ("Success", "Completed"):
            status = "Completed"
        elif sample_result in ("Failed", "Cancelled"):
            status = "Cancelled"
        elif sample_result == "Pending":
            status = "In Progress"
        else:
            status = "Open"

        created_at = get_field_value(inquiry, "sample_request_date") or now_iso()
        if created_at and "T" not in created_at:
            created_at = f"{created_at}T00:00:00"

        ctx.conn.execute(
            """
            INSERT INTO pre_sales_tasks (
                id, lead_id, assignee_id, status, request_json, result_json,
                created_at, created_by, updated_at, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generate_uuid(),
                lead_id,
                assignee_id,
                status,
                json.dumps(request_json) if request_json else None,
                json.dumps(result_json) if result_json else None,
                created_at,
                created_by,
                now_iso(),
                created_by,
            ),
        )
        ctx.stats["pre_sales_tasks_created"] += 1


def migrate_tasks(ctx: MigrationContext, inquiries: list[dict]) -> None:
    """Run both task migrations."""
    migrate_after_sales_tasks(ctx, inquiries)
    migrate_pre_sales_tasks(ctx, inquiries)
    ctx.conn.commit()
