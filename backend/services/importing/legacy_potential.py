"""Potential-opportunity sheet to canonical entities."""

from __future__ import annotations

import re

from .keys import stable_external_key
from .legacy_builder import CanonicalBuilder
from .legacy_constants import POTENTIAL_FIELDS
from .legacy_utils import activity_method, date_value, potential_stage, quality_grade, text

SHEET = "潜在商业机会"


def convert_potential(builder: CanonicalBuilder) -> None:
    sheet = builder.workbook.sheets[SHEET]
    builder.source_counts[SHEET] = 243
    for row_number in range(3, 246):
        row = sheet.row(row_number)
        ref = builder.source_ref(SHEET, row_number)
        title, customer_name = text(row, 2), text(row, 4)
        if not title:
            builder.add_issue("blocker", "missing_required_field", ref,
                              "Potential opportunity is missing business title", "title")
        if not customer_name:
            builder.add_issue("blocker", "missing_required_field", ref,
                              "Potential opportunity is missing customer name", "customer_key")

        customer_key = builder.ensure_customer(
            customer_name, ref, country=text(row, 6), city=text(row, 7),
            industry=text(row, 9),
        )
        contact_key = builder.ensure_contact(customer_key, text(row, 5), ref)
        owner_token, owner_raw, members = builder.choose_owner([text(row, 12)], ref)
        if text(row, 12) and not owner_token:
            builder.add_issue("warning", "unresolved_member", ref,
                              "Commercial owner name needs username confirmation", "owner_username_token",
                              text(row, 12))

        inquiry_date, inquiry_raw, inquiry_disposition = date_value(builder.workbook, row, 11)
        follow_date, follow_raw, follow_disposition = date_value(builder.workbook, row, 13)
        for field, raw, disposition in (
            ("inquiry_date", inquiry_raw, inquiry_disposition),
            ("occurred_at", follow_raw, follow_disposition),
        ):
            if raw and disposition == "preserved_unparsed":
                builder.add_issue("warning", "unparsed_date", ref,
                                  f"Date was preserved because it is incomplete or ambiguous: {raw}", field, raw)

        next_action, remarks = text(row, 14), text(row, 17)
        stage = potential_stage(next_action, remarks, bool(follow_date or next_action))
        fulfillment = "Not Started"
        if stage == "Won":
            fulfillment = "Completed" if re.search(r"已发货|完结|已完成", next_action + remarks) else "In Progress"
        lead = builder.add_lead(
            ref, customer_key=customer_key, primary_contact_key=contact_key, title=title or None,
            owner_username_token=owner_token, owner_name_raw=owner_raw or text(row, 12),
            sales_stage=stage, fulfillment_status=fulfillment,
            special_requirements=text(row, 3) or None, quantity_text=text(row, 10) or None,
            inquiry_date=inquiry_date, inquiry_date_raw=inquiry_raw or None,
            quality_grade=quality_grade(text(row, 16)), potential_needs=next_action or None,
            lost_reason_text=remarks if stage == "Lost" else None,
        )
        builder.add_assignments(lead["external_key"], owner_token, members, ref)
        builder.register_searchable_lead(
            lead, f"{title} {text(row, 3)} {next_action} {remarks}", text(row, 5), SHEET,
        )

        target_keys = [key for key in (customer_key, contact_key, lead["external_key"]) if key]
        if follow_date or next_action or remarks:
            method, method_raw = activity_method(text(row, 8))
            activity_key = stable_external_key(builder.dataset_id, "ACT", SHEET, row_number)
            activity = builder.add_entity("activities", {
                "external_key": activity_key, "source_ref": ref,
                "lead_key": lead["external_key"], "activity_type": "follow_up",
                "actor_username_token": owner_token, "actor_name_raw": owner_raw or text(row, 12),
                "occurred_at": follow_date, "occurred_at_raw": follow_raw or None,
                "method": method, "method_detail": method_raw or None, "status": "completed",
                "content": next_action or remarks or text(row, 3), "customer_feedback": remarks or None,
                "next_action": next_action or None, "visibility": "all",
            })
            target_keys.append(activity["external_key"])
        disposition = "mapped_with_issues" if not title or not customer_name else "mapped"
        builder.add_trace(
            SHEET, row, disposition, POTENTIAL_FIELDS, target_keys,
            raw_dates={"K": inquiry_raw, "M": follow_raw},
        )
