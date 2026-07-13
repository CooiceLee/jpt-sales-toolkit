"""
Customer service - customer management business logic.
"""

from __future__ import annotations

import json
from typing import Optional

from ..repositories import CustomerRepository, AuditRepository
from ..repositories.base import ConflictError, now_iso, generate_uuid
from .country_service import CountryService


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
        self.country_service = CountryService()

    def create(self, data: dict, actor_id: str) -> dict:
        """Create new customer."""
        # Normalize name
        if "display_name" in data:
            data["normalized_name"] = normalize_name(data["display_name"])
        self.country_service.normalize_customer_payload(data)

        customer_id = self.customer_repo.create(data, actor_id)

        # Log audit
        self.audit_repo.log(
            entity_type="customer",
            entity_id=customer_id,
            event_type="create",
            actor_id=actor_id,
            after_json=json.dumps(data),
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

        return customer

    def update(
        self,
        customer_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
    ) -> dict:
        """Update customer with conflict detection."""
        # Get current state for audit
        before = self.customer_repo.get_by_id(customer_id)

        # Normalize name if changed
        if "display_name" in data:
            data["normalized_name"] = normalize_name(data["display_name"])
        self.country_service.normalize_customer_payload(data)

        try:
            updated = self.customer_repo.update(customer_id, data, actor_id, row_version)

            # Log audit
            self.audit_repo.log(
                entity_type="customer",
                entity_id=customer_id,
                event_type="update",
                actor_id=actor_id,
                before_json=json.dumps(dict(before)) if before else None,
                after_json=json.dumps(data),
            )
            if before and self._coordinate_payload_changed(before, updated, data):
                self.audit_repo.log(
                    entity_type="customer_coordinate",
                    entity_id=customer_id,
                    event_type="coordinate_update",
                    actor_id=actor_id,
                    before_json=json.dumps(self._coordinate_snapshot(before)),
                    after_json=json.dumps(self._coordinate_snapshot(updated)),
                )

            return updated

        except ConflictError:
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

    def merge_customers(
        self,
        source_customer_id: str,
        target_customer_id: str,
        actor_id: str,
        source_row_version: Optional[int] = None,
        target_row_version: Optional[int] = None,
    ) -> dict:
        """Merge duplicate source customer into target customer."""
        if source_customer_id == target_customer_id:
            raise ValueError("Source and target customer must be different")

        source = self.customer_repo.get_by_id(source_customer_id)
        target = self.customer_repo.get_by_id(target_customer_id)
        if not source or source.get("archived_at"):
            raise ValueError("Source customer not found")
        if not target or target.get("archived_at"):
            raise ValueError("Target customer not found")

        if source_row_version is not None and source["row_version"] != source_row_version:
            raise ConflictError(
                current_version=source["row_version"],
                your_version=source_row_version,
                current_data={"id": source_customer_id, "updated_at": source["updated_at"]},
            )
        if target_row_version is not None and target["row_version"] != target_row_version:
            raise ConflictError(
                current_version=target["row_version"],
                your_version=target_row_version,
                current_data={"id": target_customer_id, "updated_at": target["updated_at"]},
            )

        conn = self.customer_repo.conn
        now = now_iso()
        moved_contacts = 0
        archived_contacts = 0
        moved_domains = 0
        skipped_domains = 0
        moved_aliases = 0
        skipped_aliases = 0
        target_updates = {}

        mergeable_fields = (
            "website",
            "industry",
            "customer_type",
            "company_size",
            "language",
            "country",
            "city",
            "postal_code",
            "address",
            "region",
            "lat",
            "lng",
            "normalized_address",
            "geocode_source",
            "geocode_confidence",
            "geocode_locked",
            "company_description",
        )
        for field in mergeable_fields:
            if not target.get(field) and source.get(field) not in (None, ""):
                target_updates[field] = source.get(field)

        try:
            lead_cursor = conn.execute(
                """
                UPDATE leads
                SET customer_id = ?, updated_at = ?, updated_by = ?, row_version = row_version + 1
                WHERE customer_id = ? AND archived_at IS NULL
                """,
                (target_customer_id, now, actor_id, source_customer_id),
            )

            contacts = conn.execute(
                """
                SELECT * FROM customer_contacts
                WHERE customer_id = ? AND archived_at IS NULL
                ORDER BY is_primary DESC, created_at ASC
                """,
                (source_customer_id,),
            ).fetchall()
            for contact in contacts:
                email = (contact["email"] or "").strip().lower()
                duplicate = None
                if email:
                    duplicate = conn.execute(
                        """
                        SELECT id FROM customer_contacts
                        WHERE customer_id = ?
                          AND lower(email) = ?
                          AND archived_at IS NULL
                        LIMIT 1
                        """,
                        (target_customer_id, email),
                    ).fetchone()
                if duplicate:
                    conn.execute(
                        """
                        UPDATE customer_contacts
                        SET archived_at = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (now, now, contact["id"]),
                    )
                    archived_contacts += 1
                else:
                    conn.execute(
                        """
                        UPDATE customer_contacts
                        SET customer_id = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (target_customer_id, now, contact["id"]),
                    )
                    moved_contacts += 1

            domains = conn.execute(
                "SELECT * FROM customer_domains WHERE customer_id = ?",
                (source_customer_id,),
            ).fetchall()
            for domain in domains:
                duplicate = conn.execute(
                    """
                    SELECT id FROM customer_domains
                    WHERE customer_id = ? AND lower(domain) = lower(?)
                    LIMIT 1
                    """,
                    (target_customer_id, domain["domain"]),
                ).fetchone()
                if duplicate:
                    conn.execute("DELETE FROM customer_domains WHERE id = ?", (domain["id"],))
                    skipped_domains += 1
                else:
                    conn.execute(
                        "UPDATE customer_domains SET customer_id = ? WHERE id = ?",
                        (target_customer_id, domain["id"]),
                    )
                    moved_domains += 1

            alias_candidates = [(source.get("display_name") or "").strip()]
            existing_aliases = conn.execute(
                "SELECT alias_name FROM customer_aliases WHERE customer_id = ?",
                (source_customer_id,),
            ).fetchall()
            alias_candidates.extend(row["alias_name"] for row in existing_aliases if row["alias_name"])

            for alias_name in alias_candidates:
                normalized_alias = normalize_name(alias_name)
                if not normalized_alias:
                    continue
                duplicate = conn.execute(
                    """
                    SELECT 1 FROM customer_aliases
                    WHERE customer_id = ? AND normalized_alias = ?
                    LIMIT 1
                    """,
                    (target_customer_id, normalized_alias),
                ).fetchone()
                if duplicate or normalize_name(target.get("display_name")) == normalized_alias:
                    skipped_aliases += 1
                    continue
                conn.execute(
                    """
                    INSERT INTO customer_aliases (id, customer_id, alias_name, normalized_alias, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (generate_uuid(), target_customer_id, alias_name, normalized_alias, now),
                )
                moved_aliases += 1

            conn.execute("DELETE FROM customer_aliases WHERE customer_id = ?", (source_customer_id,))

            conn.execute(
                """
                UPDATE customers
                SET archived_at = ?, updated_at = ?, updated_by = ?, row_version = row_version + 1
                WHERE id = ? AND archived_at IS NULL
                """,
                (now, now, actor_id, source_customer_id),
            )
            target_sets = ["updated_at = ?", "updated_by = ?", "row_version = row_version + 1"]
            target_params = [now, actor_id]
            for field, value in target_updates.items():
                target_sets.append(f"{field} = ?")
                target_params.append(value)
            target_params.append(target_customer_id)
            conn.execute(
                f"""
                UPDATE customers
                SET {", ".join(target_sets)}
                WHERE id = ? AND archived_at IS NULL
                """,
                target_params,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        result = {
            "source_customer_id": source_customer_id,
            "target_customer_id": target_customer_id,
            "moved_leads": lead_cursor.rowcount,
            "moved_contacts": moved_contacts,
            "archived_duplicate_contacts": archived_contacts,
            "moved_domains": moved_domains,
            "skipped_duplicate_domains": skipped_domains,
            "moved_aliases": moved_aliases,
            "skipped_aliases": skipped_aliases,
            "target_updates": target_updates,
        }
        self.audit_repo.log(
            entity_type="customer",
            entity_id=target_customer_id,
            event_type="merge_customer",
            actor_id=actor_id,
            before_json=json.dumps({
                "source": dict(source),
                "target": dict(target),
            }),
            after_json=json.dumps(result),
        )
        return result

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
                if customer_id and not any(c["id"] == customer_id for c in candidates):
                    customer = self.get(customer_id)
                    if customer:
                        candidates.append({
                            **customer,
                            "match_type": "name",
                            "confidence": "medium",
                        })

        return candidates

    def add_domain(self, customer_id: str, domain: str, is_primary: bool = False) -> str:
        """Add domain to customer."""
        return self.customer_repo.add_domain(customer_id, domain, is_primary)

    def add_contact(self, customer_id: str, contact_data: dict, actor_id: str) -> str:
        """Add contact to customer with validation."""
        # Validate contact data
        self._validate_contact_data(customer_id, contact_data)
        self._prepare_contact_payload(contact_data, contact_data)

        contact_id = self.customer_repo.add_contact(customer_id, contact_data)
        self.audit_repo.log(
            entity_type="customer_contact",
            entity_id=contact_id,
            event_type="create",
            actor_id=actor_id,
            after_json=json.dumps(contact_data),
        )
        return contact_id

    def update_contact(self, contact_id: str, contact_data: dict, actor_id: str) -> dict:
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

        updated = self.customer_repo.update_contact(contact_id, contact_data)
        self.audit_repo.log(
            entity_type="customer_contact",
            entity_id=contact_id,
            event_type="update",
            actor_id=actor_id,
            before_json=json.dumps(dict(before)) if before else None,
            after_json=json.dumps(contact_data),
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
            payload["email"] = str(payload.get("email") or "").strip().lower()

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
        name = contact_data.get("name", "").strip()
        email = contact_data.get("email", "").strip()

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
                if contact.get("email", "").lower() == email.lower():
                    raise ValueError(
                        f"A contact with email '{email}' already exists for this customer"
                    )

        # Validate is_primary constraint
        if contact_data.get("is_primary"):
            # Repository will handle clearing other primary contacts
            pass
