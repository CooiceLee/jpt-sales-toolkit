"""Won sheet conversion; sales stage comes from sheet semantics, not color."""

from __future__ import annotations

from .keys import member_token, split_member_names, stable_external_key
from .legacy_builder import CanonicalBuilder, representative_fill
from .legacy_constants import WON_FIELDS
from .legacy_utils import amount_value, date_value, text

SHEET = "赢单"


def convert_won(builder: CanonicalBuilder) -> None:
    sheet = builder.workbook.sheets[SHEET]
    builder.source_counts[SHEET] = 146
    for row_number in range(2, 148):
        row, ref = sheet.row(row_number), builder.source_ref(SHEET, row_number)
        product, customer_name = text(row, 3), text(row, 5)
        if not product:
            builder.add_issue("blocker", "missing_required_field", ref,
                              "Won row is missing contract/product content", "title")
        if not customer_name:
            builder.add_issue("blocker", "missing_required_field", ref,
                              "Won row is missing customer name", "customer_key")
        customer_key = builder.ensure_customer(customer_name, ref)
        contact_key = builder.ensure_contact(customer_key, text(row, 6), ref)
        owner_values = _owner_values(text(row, 2), text(row, 12))
        owner_token, owner_raw, members = builder.choose_owner(owner_values, ref)
        if not owner_token:
            builder.add_issue("warning", "unresolved_member", ref,
                              "Won opportunity owner needs username confirmation",
                              "owner_username_token", text(row, 2) or text(row, 12))

        contract_date, contract_raw, contract_disposition = date_value(builder.workbook, row, 9)
        start_date, start_raw, start_disposition = date_value(builder.workbook, row, 10)
        _warn_dates(builder, ref, (("po_date", contract_raw, contract_disposition),
                                   ("inquiry_date", start_raw, start_disposition)))
        amount, currency, amount_raw = amount_value(text(row, 8))
        _, style_class = representative_fill(row, 18)
        fulfillment = "In Progress" if style_class == "yellow" else "Completed"
        builder.won_fulfillment_rows[fulfillment] += 1

        lead, match_method, confidence = builder.match_lead(
            customer_key, product, text(row, 6), {"潜在商业机会", "售前（技术问题）"},
        )
        values = {
            "customer_key": customer_key, "primary_contact_key": contact_key,
            "owner_username_token": owner_token, "owner_name_raw": owner_raw or text(row, 2),
            "sales_stage": "Won", "fulfillment_status": fulfillment,
            "products_detail": product or None, "quantity_text": text(row, 4) or None,
            "deal_amount": amount, "deal_amount_raw": amount_raw or None, "currency": currency,
            "po_date": contract_date, "po_date_raw": contract_raw or None,
            "inquiry_date": start_date, "inquiry_date_raw": start_raw or None,
            "contract_cycle": text(row, 11) or None,
            "fulfillment_progress": text(row, 13) or None,
            "fulfillment_evidence": "yellow_fill_and_progress" if style_class == "yellow" else "won_sheet_completed_band",
        }
        if lead is None:
            lead = builder.add_lead(ref, title=product or None, **values)
        else:
            values["owner_username_token"] = lead.get("owner_username_token") or owner_token
            values["owner_name_raw"] = lead.get("owner_name_raw") or owner_raw or text(row, 2)
            builder.merge_lead(lead, ref, **values)
        owner_token = lead.get("owner_username_token")
        builder.add_assignments(lead["external_key"], owner_token, members, ref)
        builder.register_searchable_lead(lead, product, text(row, 6), SHEET)

        target_keys = [key for key in (customer_key, contact_key, lead["external_key"]) if key]
        notes = _activity_text(row)
        if notes:
            activity_key = stable_external_key(builder.dataset_id, "ACT", SHEET, row_number)
            activity = builder.add_entity("activities", {
                "external_key": activity_key, "source_ref": ref,
                "lead_key": lead["external_key"], "activity_type": "comment",
                "actor_username_token": owner_token, "actor_name_raw": owner_raw or None,
                "occurred_at": contract_date, "occurred_at_raw": contract_raw or None,
                "content": notes, "visibility": "all",
                "customer_feedback": text(row, 14) or None, "problem": text(row, 15) or None,
                "response": text(row, 16) or None, "next_action": text(row, 17) or None,
                "remarks": text(row, 18) or None,
            })
            target_keys.append(activity["external_key"])
        builder.add_trace(
            SHEET, row, "mapped" if product and customer_name else "mapped_with_issues",
            WON_FIELDS, target_keys, raw_dates={"I": contract_raw, "J": start_raw},
            match_method=match_method, confidence=confidence,
        )


def _owner_values(primary: str, team: str) -> list[str]:
    primary_members = split_member_names(primary)
    primary_known = any(member_token(name)[1] in {"leader", "sales"} for name in primary_members)
    return [primary if primary_known else "", team]


def _activity_text(row) -> str:
    labels = ((14, "客户反馈"), (15, "存在问题"), (16, "应对措施"),
              (17, "下一步计划"), (18, "备注"))
    return "\n".join(f"{label}: {text(row, column)}" for column, label in labels if text(row, column))


def _warn_dates(builder: CanonicalBuilder, ref: dict, dates: tuple[tuple[str, str, str], ...]) -> None:
    for field, raw, disposition in dates:
        if raw and disposition == "preserved_unparsed":
            builder.add_issue("warning", "unparsed_date", ref,
                              f"Date was preserved because it is incomplete or ambiguous: {raw}", field, raw)
