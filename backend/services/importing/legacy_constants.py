"""Verified boundaries and semantics of the Europe squad legacy workbook."""

from __future__ import annotations

import uuid

LEGACY_SHEETS = ("潜在商业机会", "售前（技术问题）", "赢单", "售后")
LEGACY_RANGES = {
    "潜在商业机会": (3, 245),
    "售前（技术问题）": (3, 86),
    "赢单": (2, 147),
    "售后": (3, 71),
}
LEGACY_DATASET_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "jpt:legacy:europe-squad-progress"))

SHEET_CODES = {
    "潜在商业机会": "potential",
    "售前（技术问题）": "presales",
    "赢单": "won",
    "售后": "aftersales",
}

GREEN = {"FF00B050", "FF92D050"}
YELLOW = {"FFFFFF00"}
GRAY = {
    "FF7F7F7F", "FF939393", "FFA5A5A5", "FFC5CAD3", "FF808B9E",
    "FFBFBFBF", "FF595959", "FFD8D8D8",
}

CUSTOMER_CANONICAL_NAMES = {
    "opto": "Optoprim srl a socio unico",
    "opto大学": "Optoprim srl a socio unico",
    "optoprimsrlasociounico": "Optoprim srl a socio unico",
}

POTENTIAL_FIELDS = {
    "A": "source_ordinal", "B": "lead.title", "C": "lead.special_requirements",
    "D": "customer.display_name", "E": "contact.name", "F": "customer.country",
    "G": "customer.city", "H": "activity.method_raw", "I": "customer.industry",
    "J": "lead.quantity_text", "K": "lead.inquiry_date", "L": "lead.owner_username_token",
    "M": "activity.occurred_at", "N": "activity.next_action", "O": "preserved_unmapped",
    "P": "lead.quality_grade_hint", "Q": "activity.customer_feedback",
}
PRESALES_FIELDS = {
    "A": "source_ordinal", "B": "lead.owner_username_token", "C": "task.request_description",
    "D": "customer.display_name", "E": "contact.name", "F": "activity.method_raw",
    "G": "task.customer_decision_maker", "H": "lead.quantity_text", "I": "task.request_date",
    "J": "task.due_date", "K": "task.assignee_username_token", "L": "task.competitor",
    "M": "task.key_points", "N": "task.concerns", "O": "task.progress_text",
    "P": "task.next_action", "Q": "preserved_unmapped",
}
WON_FIELDS = {
    "A": "source_ordinal", "B": "lead.owner_username_token", "C": "lead.products_detail",
    "D": "lead.quantity_text", "E": "customer.display_name", "F": "contact.name",
    "G": "activity.method_raw", "H": "lead.deal_amount_raw", "I": "lead.po_date",
    "J": "lead.inquiry_date", "K": "lead.contract_cycle", "L": "lead.team_tokens",
    "M": "lead.fulfillment_progress", "N": "activity.customer_feedback",
    "O": "activity.problem", "P": "activity.response", "Q": "activity.next_action",
    "R": "activity.remarks",
}
AFTERSALES_FIELDS = {
    "A": "source_ordinal", "B": "lead.owner_username_token", "C": "task.issue_description",
    "D": "customer.display_name", "E": "contact.name", "F": "activity.method_raw",
    "G": "task.issue_date", "H": "task.assignee_username_token", "I": "task.progress_text",
    "J": "task.customer_satisfaction", "K": "task.lessons_learned", "L": "task.remarks",
    "M": "task.remarks_continuation",
}
