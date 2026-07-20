"""Pre-sales technical sheet to canonical leads and one task per assignee."""

from __future__ import annotations

from .keys import stable_external_key
from .legacy_builder import CanonicalBuilder
from .legacy_constants import PRESALES_FIELDS
from .legacy_utils import date_value, pre_sales_status, text

SHEET = "售前（技术问题）"


def convert_presales(builder: CanonicalBuilder) -> None:
    sheet = builder.workbook.sheets[SHEET]
    builder.source_counts[SHEET] = 84
    for row_number in range(3, 87):
        row, ref = sheet.row(row_number), builder.source_ref(SHEET, row_number)
        description, customer_name = text(row, 3), text(row, 4)
        if not description:
            builder.add_issue("blocker", "missing_required_field", ref,
                              "Pre-sales task is missing request description", "request_description")
        if not customer_name:
            builder.add_issue("blocker", "missing_required_field", ref,
                              "Pre-sales row is missing customer name", "customer_key")
        customer_key = builder.ensure_customer(customer_name, ref)
        contact_key = builder.ensure_contact(customer_key, text(row, 5), ref)
        owner_token, owner_raw, owner_members = builder.choose_owner([text(row, 2)], ref)
        request_date, request_raw, request_disposition = date_value(builder.workbook, row, 9)
        due_date, due_raw, due_disposition = date_value(builder.workbook, row, 10)
        _warn_dates(builder, ref, (("request_date", request_raw, request_disposition),
                                   ("due_date", due_raw, due_disposition)))

        lead, match_method, confidence = builder.match_lead(
            customer_key, description, text(row, 5), {"潜在商业机会"},
        )
        if lead is None:
            lead = builder.add_lead(
                ref, customer_key=customer_key, primary_contact_key=contact_key,
                title=description or None, owner_username_token=owner_token,
                owner_name_raw=owner_raw or text(row, 2), sales_stage="Following",
                fulfillment_status="Not Started", inquiry_date=request_date,
                inquiry_date_raw=request_raw or None, quantity_text=text(row, 8) or None,
            )
        else:
            owner_token = lead.get("owner_username_token") or owner_token
            builder.merge_lead(
                lead, ref, sales_stage="Following" if lead.get("sales_stage") in {"New", "Assigned"} else lead.get("sales_stage"),
                primary_contact_key=lead.get("primary_contact_key") or contact_key,
                owner_username_token=owner_token,
            )
        if text(row, 2) and not owner_token:
            builder.add_issue("warning", "unresolved_member", ref,
                              "Sales owner needs username confirmation", "owner_username_token", text(row, 2),
                              lead["external_key"])
        builder.add_assignments(lead["external_key"], owner_token, owner_members, ref)
        builder.register_searchable_lead(lead, description, text(row, 5), SHEET)

        assignees = builder.member_names(text(row, 11), ref)
        if not assignees:
            assignees = [{"raw_name": text(row, 11), "username_token": None, "role_hint": "unknown"}]
            builder.add_issue("warning", "missing_assignee", ref,
                              "Pre-sales task has no technical assignee", "assignee_username_token",
                              entity_key=lead["external_key"])
        target_keys = [key for key in (customer_key, contact_key, lead["external_key"]) if key]
        group_key = stable_external_key(builder.dataset_id, "PTG", SHEET, row_number)
        for assignee in assignees:
            if assignee["role_hint"] == "unknown" and assignee["raw_name"]:
                builder.add_issue("warning", "unresolved_member", ref,
                                  "Technical assignee needs username confirmation", "assignee_username_token",
                                  assignee["raw_name"], lead["external_key"])
            task_key = stable_external_key(
                builder.dataset_id, "PRE", SHEET, row_number,
                assignee["username_token"] or "unassigned",
            )
            task = builder.add_entity("pre_sales_tasks", {
                "external_key": task_key, "source_ref": ref, "task_group_key": group_key,
                "lead_key": lead["external_key"],
                "assignee_username_token": assignee["username_token"],
                "assignee_name_raw": assignee["raw_name"] or None,
                "status": pre_sales_status(text(row, 15), text(row, 16)),
                "request_description": description or None, "request_date": request_date,
                "request_date_raw": request_raw or None, "due_date": due_date,
                "due_date_raw": due_raw or None, "customer_decision_maker": text(row, 7) or None,
                "quantity_text": text(row, 8) or None, "competitor": text(row, 12) or None,
                "key_points": text(row, 13) or None, "concerns": text(row, 14) or None,
                "progress_text": text(row, 15) or None, "next_action": text(row, 16) or None,
                "supplemental_notes": text(row, 17) or None,
            })
            target_keys.append(task["external_key"])
        builder.add_trace(
            SHEET, row, "mapped" if description and customer_name else "mapped_with_issues",
            PRESALES_FIELDS, target_keys, raw_dates={"I": request_raw, "J": due_raw},
            match_method=match_method, confidence=confidence,
        )


def _warn_dates(builder: CanonicalBuilder, ref: dict, dates: tuple[tuple[str, str, str], ...]) -> None:
    for field, raw, disposition in dates:
        if raw and disposition == "preserved_unparsed":
            builder.add_issue("warning", "unparsed_date", ref,
                              f"Date was preserved because it is incomplete or ambiguous: {raw}", field, raw)
