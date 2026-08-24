"""
Customer service - customer management business logic.
"""

from __future__ import annotations

import json
from typing import Optional

from ..repositories import CustomerRepository, AuditRepository
from ..repositories.customer_alias_repository import CustomerAliasRepository
from .country_service import CountryService
from .customer_fuzzy_search import rank_merge_candidates
from .customer_merge_service import CustomerMergeService
from .trip_plan_invalidation import (
    ROUTE_LOCATION_FIELDS,
    invalidate_customer_route_dependencies,
)


def normalize_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""
    return name.lower().strip().replace(",", "").replace(".", "")


def extract_domain(email: str) -> Optional[str]:
    """Extract domain from email."""
    if not email or "@" not in email:
        return None
    return email.split("@")[-1].lower().strip()


def is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    if not email:
        return False
    email = email.strip()
    # Basic check: contains @ and has parts before and after
    if "@" not in email:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    if not local or not domain:
        return False
    # Domain should have at least one dot
    if "." not in domain:
        return False
    # Domain parts should not be empty
    domain_parts = domain.split(".")
    if any(not part for part in domain_parts):
        return False
    return True


class CustomerService:
    """Customer management service."""

    def __init__(
        self,
        customer_repo: Optional[CustomerRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
    ):
        self.customer_repo = customer_repo or CustomerRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.alias_repo = CustomerAliasRepository(self.customer_repo.conn)
        self.country_service = CountryService()

    def create(
        self,
        data: dict,
        actor_id: str,
        *,
        commit: bool = True,
    ) -> dict:
        """Create new customer."""
        # Normalize name
        if "display_name" in data:
            data["normalized_name"] = normalize_name(data["display_name"])
        self.country_service.normalize_customer_payload(data)

        customer_id = self.customer_repo.create(data, actor_id, commit=commit)

        # Log audit
        self.audit_repo.log(
            entity_type="customer",
            entity_id=customer_id,
            event_type="create",
            actor_id=actor_id,
            after_json=json.dumps(data),
            commit=commit,
        )

        return self.get(customer_id)

    def get(self, customer_id: str) -> Optional[dict]:
        """Get customer by ID with related data."""
        customer = self.customer_repo.get_by_id(customer_id)
        if not customer:
            return None

        # Add related data
        customer["domains"] = self.customer_repo.get_domains(customer_id)
        customer["contacts"] = self.customer_repo.get_contacts(customer_id)
        customer["aliases"] = self.alias_repo.list_for_customer(customer_id)

        return customer

    def update(
        self,
        customer_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
        *,
        commit: bool = True,
    ) -> dict:
        """Update customer with conflict detection."""
        # Get current state for audit
        before = self.customer_repo.get_by_id(customer_id)

        # Normalize name if changed
        if "display_name" in data:
            data["normalized_name"] = normalize_name(data["display_name"])
        self.country_service.normalize_customer_payload(data)

        try:
            updated = self.customer_repo.update(
                customer_id,
                data,
                actor_id,
                row_version,
                commit=False,
            )

            # Log audit
            self.audit_repo.log(
                entity_type="customer",
                entity_id=customer_id,
                event_type="update",
                actor_id=actor_id,
                before_json=json.dumps(dict(before)) if before else None,
                after_json=json.dumps(data),
                commit=False,
            )
            if before and self._coordinate_payload_changed(before, updated, data):
                self.audit_repo.log(
                    entity_type="customer_coordinate",
                    entity_id=customer_id,
                    event_type="coordinate_update",
                    actor_id=actor_id,
                    before_json=json.dumps(self._coordinate_snapshot(before)),
                    after_json=json.dumps(self._coordinate_snapshot(updated)),
                    commit=False,
                )

            if before and self._route_location_payload_changed(before, updated, data):
                invalidate_customer_route_dependencies(
                    self.customer_repo.conn,
                    [customer_id],
                    actor_id,
                    "customer_location_changed",
                )

            if commit:
                self.customer_repo.conn.commit()

            return updated

        except Exception:
            if commit:
                self.customer_repo.conn.rollback()
            raise

    def _coordinate_snapshot(self, customer: dict) -> dict:
        fields = (
            "lat",
            "lng",
            "address",
            "city",
            "country",
            "region",
            "normalized_address",
            "geocode_source",
            "geocode_confidence",
            "geocode_locked",
        )
        return {field: customer.get(field) for field in fields}

    def _coordinate_payload_changed(self, before: dict, after: dict, payload: dict) -> bool:
        coordinate_fields = set(self._coordinate_snapshot(before))
        if not coordinate_fields.intersection(payload):
            return False
        return self._coordinate_snapshot(before) != self._coordinate_snapshot(after)

    @staticmethod
    def _route_location_payload_changed(before: dict, after: dict, payload: dict) -> bool:
        changed_fields = ROUTE_LOCATION_FIELDS.intersection(payload)
        return any(before.get(field) != after.get(field) for field in changed_fields)

    def archive(self, customer_id: str, actor_id: str) -> bool:
        """Archive customer."""
        success = self.customer_repo.archive(customer_id, actor_id)

        if success:
            self.audit_repo.log(
                entity_type="customer",
                entity_id=customer_id,
                event_type="archive",
                actor_id=actor_id,
            )

        return success

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        country: Optional[str] = None,
        region: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        """List customers with filters."""
        return self.customer_repo.list_active(
            limit=limit,
            offset=offset,
            country=country,
            region=region,
            search=search,
        )

    def fuzzy_merge_candidates(self, query: str, limit: int = 12) -> list[dict]:
        """Rank active customers by display name and active aliases."""
        return rank_merge_candidates(
            self.customer_repo.list_merge_candidate_records(),
            query,
            limit,
        )

    def merge_customers(
        self,
        source_customer_id: str,
        target_customer_id: str,
        actor_id: str,
        source_row_version: Optional[int] = None,
        target_row_version: Optional[int] = None,
    ) -> dict:
        """Merge duplicate source customer into target customer."""
        return CustomerMergeService(self.customer_repo).merge(
            source_customer_id, target_customer_id, actor_id,
            source_row_version, target_row_version,
        )

    def match(self, email: Optional[str], company_name: Optional[str]) -> list[dict]:
        """
        Find potential customer matches.

        Returns list of candidates with match_type and confidence.
        """
        candidates = []

        # 1. Match by email
        if email:
            customer_id = self.customer_repo.find_by_email(email)
            if customer_id:
                customer = self.get(customer_id)
                if customer:
                    candidates.append({
                        **customer,
                        "match_type": "email",
                        "confidence": "high",
                    })

        # 2. Match by domain
        if email:
            domain = extract_domain(email)
            if domain:
                customer_id = self.customer_repo.find_by_domain(domain)
                if customer_id and not any(c["id"] == customer_id for c in candidates):
                    customer = self.get(customer_id)
                    if customer:
                        candidates.append({
                            **customer,
                            "match_type": "domain",
                            "confidence": "high",
                        })

        # 3. Match by normalized name
        if company_name:
            normalized = normalize_name(company_name)
            if normalized:
                customer_id = self.customer_repo.find_by_normalized_name(normalized)
                match_type = "name"
                if not customer_id:
                    customer_id = self.alias_repo.find_active_customer(normalized)
                    match_type = "alias"
                if customer_id and not any(c["id"] == customer_id for c in candidates):
                    customer = self.get(customer_id)
                    if customer:
                        candidates.append({
                            **customer,
                            "match_type": match_type,
                            "confidence": "medium",
                        })

        return candidates

    def add_domain(self, customer_id: str, domain: str, is_primary: bool = False) -> str:
        """Add domain to customer."""
        return self.customer_repo.add_domain(customer_id, domain, is_primary)

    def add_contact(
        self,
        customer_id: str,
        contact_data: dict,
        actor_id: str,
        *,
        commit: bool = True,
    ) -> str:
        """Add contact to customer with validation."""
        # Validate contact data
        self._validate_contact_data(customer_id, contact_data)
        self._prepare_contact_payload(contact_data, contact_data)

        contact_id = self.customer_repo.add_contact(
            customer_id,
            contact_data,
            commit=commit,
        )
        self.audit_repo.log(
            entity_type="customer_contact",
            entity_id=contact_id,
            event_type="create",
            actor_id=actor_id,
            after_json=json.dumps(contact_data),
            commit=commit,
        )
        return contact_id

    def update_contact(
        self,
        contact_id: str,
        contact_data: dict,
        actor_id: str,
        *,
        expected_updated_at: Optional[str] = None,
        commit: bool = True,
    ) -> dict:
        """Update customer contact with validation."""
        before = self.customer_repo.get_contact_by_id(contact_id)
        if not before:
            raise ValueError(f"Contact {contact_id} not found")

        # Validate the resulting full contact, not only the partial patch payload.
        validation_data = {
            key: before.get(key)
            for key in ("name", "position", "email", "phone", "whatsapp", "is_primary")
        }
        validation_data.update(contact_data)
        self._validate_contact_data(before["customer_id"], validation_data, contact_id)
        self._prepare_contact_payload(contact_data, validation_data)

        updated = self.customer_repo.update_contact(
            contact_id,
            contact_data,
            expected_updated_at=expected_updated_at,
            commit=commit,
        )
        self.audit_repo.log(
            entity_type="customer_contact",
            entity_id=contact_id,
            event_type="update",
            actor_id=actor_id,
            before_json=json.dumps(dict(before)) if before else None,
            after_json=json.dumps(contact_data),
            commit=commit,
        )
        return updated

    def archive_contact(self, contact_id: str, actor_id: str) -> bool:
        """Archive customer contact."""
        before = self.customer_repo.get_contact_by_id(contact_id)
        success = self.customer_repo.archive_contact(contact_id)
        if success:
            self.audit_repo.log(
                entity_type="customer_contact",
                entity_id=contact_id,
                event_type="archive",
                actor_id=actor_id,
                before_json=json.dumps(dict(before)) if before else None,
            )
        return success

    def _prepare_contact_payload(self, payload: dict, resolved_data: dict) -> None:
        """Normalize contact payload before writing to the NOT NULL contact schema."""
        if "name" in payload:
            payload["name"] = str(payload.get("name") or "").strip()
        if "email" in payload:
            normalized_email = str(payload.get("email") or "").strip().lower()
            # SQLite treats multiple NULL values as distinct for the
            # UNIQUE(customer_id, email) constraint.  Persisting a missing
            # address as "" incorrectly makes the second name-only contact a
            # duplicate of the first one.
            payload["email"] = normalized_email or None

        resolved_name = str(resolved_data.get("name") or "").strip()
        resolved_email = str(resolved_data.get("email") or "").strip()
        if not resolved_name and resolved_email:
            payload["name"] = resolved_email

    def _validate_contact_data(
        self,
        customer_id: str,
        contact_data: dict,
        exclude_contact_id: Optional[str] = None
    ) -> None:
        """
        Validate customer contact data.

        Args:
            customer_id: Customer ID
            contact_data: Contact data to validate
            exclude_contact_id: Contact ID to exclude from duplicate checks (for updates)

        Raises:
            ValueError: If validation fails
        """
        # Check required fields
        name = str(contact_data.get("name") or "").strip()
        email = str(contact_data.get("email") or "").strip()

        # At least one of name or email must be provided
        if not name and not email:
            raise ValueError("Contact must have either a name or an email address")

        # Email format validation
        if email and not is_valid_email(email):
            raise ValueError(f"Invalid email format: {email}")

        # Check for duplicate email within same customer
        if email:
            existing_contacts = self.customer_repo.get_contacts(customer_id)
            for contact in existing_contacts:
                # Skip the contact being updated
                if exclude_contact_id and contact["id"] == exclude_contact_id:
                    continue

                # Check for duplicate email
                if str(contact.get("email") or "").lower() == email.lower():
                    raise ValueError(
                        f"A contact with email '{email}' already exists for this customer"
                    )

        # Validate is_primary constraint
        if contact_data.get("is_primary"):
            # Repository will handle clearing other primary contacts
            pass
