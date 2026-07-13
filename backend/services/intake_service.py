"""
Intake service - combined endpoint for email parsing and lead creation.
"""

from __future__ import annotations

from typing import Optional

from ..repositories import get_transaction
from .customer_service import CustomerService
from .email_parser import parse_inquiry_email
from .lead_service import LeadService


class IntakeService:
    """Intake service for one-screen lead creation."""

    def __init__(
        self,
        customer_service: Optional[CustomerService] = None,
        lead_service: Optional[LeadService] = None,
    ):
        self.customer_service = customer_service or CustomerService()
        self.lead_service = lead_service or LeadService()

    def parse_email(self, raw_email: str) -> dict:
        """Parse an inquiry using the single structured parser implementation."""
        return parse_inquiry_email(raw_email)

    def match_customers(
        self,
        email: Optional[str],
        company_name: Optional[str],
    ) -> list[dict]:
        """Find potential customer matches."""
        return self.customer_service.match(email, company_name)

    def submit(
        self,
        is_new_customer: bool,
        customer_id: Optional[str],
        customer_data: Optional[dict],
        lead_data: dict,
        contact_data: Optional[dict],
        owner_id: str,
        actor_id: str,
        collaborator_ids: Optional[list[str]] = None,
        watcher_ids: Optional[list[str]] = None,
    ) -> dict:
        """
        Atomic submission of customer + lead + assignments.

        Returns dict with customer_id, lead_id, display_id.
        """
        with get_transaction():
            # Create or use existing customer
            if is_new_customer:
                if not customer_data:
                    raise ValueError("customer_data required for new customer")
                customer = self.customer_service.create(customer_data, actor_id)
                final_customer_id = customer["id"]
            else:
                if not customer_id:
                    raise ValueError("customer_id required for existing customer")
                final_customer_id = customer_id

            self._save_contact(final_customer_id, contact_data, actor_id)

            # Create lead
            lead_data["customer_id"] = final_customer_id
            lead_data["owner_id"] = owner_id
            lead_data["sales_stage"] = lead_data.get("sales_stage", "New")

            lead = self.lead_service.create(lead_data, actor_id)

            # Add collaborators
            if collaborator_ids:
                for user_id in collaborator_ids:
                    self.lead_service.add_assignment(
                        lead["id"], user_id, "collaborator", actor_id
                    )

            # Add watchers
            if watcher_ids:
                for user_id in watcher_ids:
                    self.lead_service.add_assignment(
                        lead["id"], user_id, "watcher", actor_id
                    )

            return {
                "customer_id": final_customer_id,
                "lead_id": lead["id"],
                "display_id": lead["display_id"],
            }

    def _save_contact(self, customer_id: str, data: Optional[dict], actor_id: str) -> None:
        """Create or update the confirmed intake contact without duplicates."""
        if not data or not (data.get("name") or data.get("email")):
            return
        allowed = {"name", "position", "email", "phone", "whatsapp", "is_primary"}
        contact_data = {key: value for key, value in data.items() if key in allowed}
        email = (contact_data.get("email") or "").strip().lower()
        name = (contact_data.get("name") or "").strip().casefold()
        contacts = self.customer_service.customer_repo.get_contacts(customer_id)
        existing = next(
            (item for item in contacts if email and (item.get("email") or "").lower() == email),
            None,
        )
        if not existing and name:
            existing = next(
                (item for item in contacts if (item.get("name") or "").strip().casefold() == name),
                None,
            )
        if existing:
            self.customer_service.update_contact(existing["id"], contact_data, actor_id)
        else:
            self.customer_service.add_contact(customer_id, contact_data, actor_id)
