"""Stable machine contract for JPT-XLSX-1.0 Excel tables."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from .exceptions import UnsupportedWorkbookError
from .workbook import column_index

MACHINE_FIELD = re.compile(r"^[a-z][a-z0-9_]*$")
RANGE = re.compile(r"^\$?([A-Z]+)\$?([1-9][0-9]*):\$?([A-Z]+)\$?([1-9][0-9]*)$")


@dataclass(frozen=True)
class TableSpec:
    entity_name: str
    key_field: str
    required_fields: tuple[str, ...]


TABLE_SPECS = {
    "tbl_customers": TableSpec("customers", "customer_key",
                               ("action", "customer_key", "display_name")),
    "tbl_customer_aliases": TableSpec(
        "aliases", "alias_key", ("action", "alias_key", "customer_key", "alias_name")),
    "tbl_contacts": TableSpec(
        "contacts", "contact_key", ("action", "contact_key", "customer_key", "name")),
    "tbl_leads": TableSpec(
        "leads", "lead_key",
        ("action", "lead_key", "customer_key", "title", "owner_username", "sales_stage")),
    "tbl_lead_assignments": TableSpec(
        "assignments", "assignment_key",
        ("action", "assignment_key", "lead_key", "member_username", "assignment_type")),
    "tbl_activities": TableSpec(
        "activities", "activity_key",
        ("action", "activity_key", "lead_key", "activity_type", "actor_username",
         "occurred_at", "content", "visibility")),
    "tbl_pre_sales_tasks": TableSpec(
        "pre_sales_tasks", "task_key",
        ("action", "task_key", "lead_key", "assignee_username", "status",
         "request_description")),
    "tbl_after_sales_tasks": TableSpec(
        "after_sales_tasks", "task_key",
        ("action", "task_key", "lead_key", "assignee_username", "issue_type", "status",
         "issue_description")),
}

TOKEN_RENAMES = {
    "owner_username": "owner_username_token",
    "assignee_username": "assignee_username_token",
    "member_username": "member_username_token",
    "actor_username": "actor_username_token",
}


def machine_field(header: object) -> Optional[str]:
    text = str(header or "").strip()
    for separator in ("｜", "|"):
        if separator in text:
            text = text.rsplit(separator, 1)[1].strip()
            break
    return text if MACHINE_FIELD.fullmatch(text) else None


def range_bounds(reference: str) -> tuple[int, int, int, int]:
    match = RANGE.fullmatch(reference.upper())
    if not match:
        raise UnsupportedWorkbookError(f"Invalid Excel table range: {reference}")
    start_column = column_index(f"{match.group(1)}{match.group(2)}")
    end_column = column_index(f"{match.group(3)}{match.group(4)}")
    start_row, end_row = int(match.group(2)), int(match.group(4))
    if start_column > end_column or start_row > end_row:
        raise UnsupportedWorkbookError(f"Reversed Excel table range: {reference}")
    return start_column, start_row, end_column, end_row
