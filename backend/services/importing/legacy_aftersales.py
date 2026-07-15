"""After-sales sheet conversion with continuation-row preservation."""

from __future__ import annotations

from .keys import member_token, split_member_names, stable_external_key
from .legacy_builder import CanonicalBuilder
from .legacy_constants import AFTERSALES_FIELDS
from .legacy_utils import (activity_method, after_sales_status, date_value,
                           issue_type, text)

SHEET = "售后"


def convert_aftersales(builder: CanonicalBuilder) -> None:
    sheet = builder.workbook.sheets[SHEET]
    builder.source_counts[SHEET] = 69
    for row_number in range(3, 72):
        row, ref = sheet.row(row_number), builder.source_ref(SHEET, row_number)
        description, customer_name = text(row, 3), text(row, 4)
        if not description:
            builder.add_issue("blocker", "missing_required_field", ref,
                              "After-sales task is missing issue description", "issue_description")
        if not customer_name:
            builder.add_issue("blocker", "missing_required_field", ref,
                              "After-sales row is missing customer name", "customer_key")
        customer_key = builder.ensure_customer(customer_name, ref)
        contact_key = builder.ensure_contact(customer_key, text(row, 5), ref)
        owner_values = _owner_values(text(row, 2))
        owner_token, owner_raw, owner_members = builder.choose_owner(owner_values, ref)
        issue_date, issue_raw, issue_disposition = date_value(builder.workbook, row, 7)
        if issue_raw and issue_disposition == "preserved_unparsed":
            builder.add_issue("warning", "unparsed_date", ref,
                              f"Date was preserved because it is incomplete or ambiguous: {issue_raw}",
                              "issue_date", issue_raw)

        progress = text(row, 9)
        if row_number == 71 and text(sheet.row(72), 9):
            progress = "\n".join(value for value in (progress, text(sheet.row(72), 9)) if value)
        remarks = "\n".join(value for value in (text(row, 12), text(row, 13)) if value)
        lead, match_method, confidence = builder.match_lead(
            customer_key, description, text(row, 5),
            {"潜在商业机会", "售前（技术问题）", "赢单"},
        )
        if lead is None:
            lead = builder.add_lead(
                ref, customer_key=customer_key, primary_contact_key=contact_key,
                title=description or None, owner_username_token=owner_token,
                owner_name_raw=owner_raw or text(row, 2), sales_stage="Won",
                fulfillment_status="Completed", products_detail=description or None,
            )
        else:
            builder.merge_lead(
                lead, ref, sales_stage="Won", fulfillment_status="Completed",
                primary_contact_key=lead.get("primary_contact_key") or contact_key,
                owner_username_token=lead.get("owner_username_token") or owner_token,
                owner_name_raw=lead.get("owner_name_raw") or owner_raw or text(row, 2),
            )
        owner_token = lead.get("owner_username_token")
        builder.add_assignments(lead["external_key"], owner_token, owner_members, ref)
        builder.register_searchable_lead(lead, description, text(row, 5), SHEET)

        assignees = builder.member_names(text(row, 8), ref)
        if not assignees:
            assignees = [{"raw_name": text(row, 8), "username_token": None, "role_hint": "unknown"}]
            builder.add_issue("warning", "missing_assignee", ref,
                              "After-sales task has no technical assignee", "assignee_username_token",
                              entity_key=lead["external_key"])
        target_keys = [key for key in (customer_key, contact_key, lead["external_key"]) if key]
        group_key = stable_external_key(builder.dataset_id, "ATG", SHEET, row_number)
        method, method_raw = activity_method(text(row, 6))
        for assignee in assignees:
            if assignee["role_hint"] == "unknown" and assignee["raw_name"]:
                builder.add_issue("warning", "unresolved_member", ref,
                                  "After-sales assignee needs username confirmation", "assignee_username_token",
                                  assignee["raw_name"], lead["external_key"])
            task_key = stable_external_key(
                builder.dataset_id, "AFT", SHEET, row_number,
                assignee["username_token"] or "unassigned",
            )
            task = builder.add_entity("after_sales_tasks", {
                "external_key": task_key, "source_ref": ref, "task_group_key": group_key,
                "lead_key": lead["external_key"],
                "assignee_username_token": assignee["username_token"],
                "assignee_name_raw": assignee["raw_name"] or None,
                "issue_type": issue_type(description),
                "status": after_sales_status(progress, remarks),
                "issue_description": description or None, "issue_date": issue_date,
                "issue_date_raw": issue_raw or None, "contact_method": method,
                "contact_method_raw": method_raw or None, "progress_text": progress or None,
                "customer_satisfaction": text(row, 10) or None,
                "lessons_learned": text(row, 11) or None, "remarks": remarks or None,
            })
            target_keys.append(task["external_key"])
        builder.add_trace(
            SHEET, row, "mapped" if description and customer_name else "mapped_with_issues",
            AFTERSALES_FIELDS, target_keys, raw_dates={"G": issue_raw},
            match_method=match_method, confidence=confidence,
        )
        if row_number == 71 and text(sheet.row(72), 9):
            builder.add_trace(
                SHEET, sheet.row(72), "merged_continuation", {"I": "task.progress_text"},
                target_keys, match_method="adjacent_continuation", confidence="high",
            )


def _owner_values(primary: str) -> list[str]:
    members = split_member_names(primary)
    return [primary] if any(member_token(name)[1] in {"leader", "sales"} for name in members) else []
