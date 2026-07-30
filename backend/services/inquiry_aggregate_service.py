"""Atomic save orchestration for the multi-entity inquiry editor."""

from __future__ import annotations

import sqlite3
from typing import Optional

from ..repositories import (
    ActivityRepository,
    AuditRepository,
    CustomerRepository,
    DataQualityIssueRepository,
    LeadRepository,
)
from .customer_service import CustomerService
from .lead_service import LeadService, mask_lead_for_role


class InquiryNotFoundError(ValueError):
    """Raised when the aggregate root or one of its owned records is missing."""


class InquiryAggregateService:
    """Persist customer, contact and lead edits in one SQLite transaction."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.customer_repo = CustomerRepository(conn)
        self.lead_repo = LeadRepository(conn)
        audit_repo = AuditRepository(conn)
        self.customer_service = CustomerService(self.customer_repo, audit_repo)
        self.lead_service = LeadService(
            lead_repo=self.lead_repo,
            activity_repo=ActivityRepository(conn),
            audit_repo=audit_repo,
            customer_repo=self.customer_repo,
            quality_issue_repo=DataQualityIssueRepository(conn),
        )

    def save(
        self,
        lead_id: str,
        actor: dict,
        *,
        customer: Optional[dict] = None,
        contact: Optional[dict] = None,
        lead: Optional[dict] = None,
    ) -> dict:
        """Apply all supplied patches atomically and return a fresh lead snapshot."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            current_lead = self.lead_repo.get_by_id(lead_id)
            if not current_lead:
                raise InquiryNotFoundError(f"Lead {lead_id} not found")
            actor_role = self._actor_role(current_lead, actor)
            if actor_role == "none":
                raise PermissionError("Access denied")
            if actor_role == "tech":
                raise PermissionError("Technical users cannot edit inquiry sales fields")
            if actor_role == "watcher":
                raise PermissionError("Watchers cannot modify inquiries")

            customer_id = current_lead["customer_id"]
            self._save_customer(customer_id, customer, actor["id"])
            self._save_contact(customer_id, contact, actor["id"])
            self._save_lead(lead_id, lead, actor["id"], actor_role)
            updated = self.lead_service.get(lead_id, actor["id"], actor["role"])
            if not updated:
                raise InquiryNotFoundError(f"Lead {lead_id} not found after save")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return mask_lead_for_role(updated, actor_role)

    def _save_customer(
        self,
        customer_id: str,
        patch: Optional[dict],
        actor_id: str,
    ) -> None:
        if not patch:
            return
        data = dict(patch)
        row_version = data.pop("row_version")
        if not data:
            return
        self.customer_service.update(
            customer_id,
            data,
            actor_id,
            row_version,
            commit=False,
        )

    def _save_contact(
        self,
        customer_id: str,
        patch: Optional[dict],
        actor_id: str,
    ) -> None:
        if not patch:
            return
        data = dict(patch)
        contact_id = data.pop("contact_id", None)
        updated_at = data.pop("updated_at", None)
        if not data:
            return
        if not contact_id:
            self.customer_service.add_contact(
                customer_id,
                data,
                actor_id,
                commit=False,
            )
            return

        current = self.customer_repo.get_contact_by_id(contact_id)
        if not current or current["customer_id"] != customer_id:
            raise InquiryNotFoundError("Contact is not part of this inquiry customer")
        if updated_at is None:
            raise ValueError("Contact version is required")
        self.customer_service.update_contact(
            contact_id,
            data,
            actor_id,
            expected_updated_at=updated_at,
            commit=False,
        )

    def _save_lead(
        self,
        lead_id: str,
        patch: Optional[dict],
        actor_id: str,
        actor_role: str,
    ) -> None:
        if not patch:
            return
        data = dict(patch)
        row_version = data.pop("row_version")
        if not data:
            return
        required = {"owner_id", "title", "sales_stage", "fulfillment_status", "service_status"}
        invalid_nulls = sorted(key for key in required if key in data and data[key] is None)
        if invalid_nulls:
            raise ValueError(f"Fields cannot be null: {', '.join(invalid_nulls)}")
        self.lead_service.update(
            lead_id,
            data,
            actor_id,
            actor_role,
            row_version,
            commit=False,
        )

    def _actor_role(self, lead: dict, actor: dict) -> str:
        if actor["role"] == "leader":
            return "leader"
        if actor["role"] == "tech":
            return "tech"
        if lead["owner_id"] == actor["id"]:
            return "owner"
        for assignment in self.lead_repo.get_assignments(lead["id"]):
            if assignment["user_id"] == actor["id"]:
                return assignment["assignment_type"]
        return "none"
