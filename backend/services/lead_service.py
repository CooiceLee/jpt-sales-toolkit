"""
Lead service - lead management business logic with permission checks.
"""

from __future__ import annotations

import json
from typing import Optional

from ..repositories import LeadRepository, ActivityRepository, AuditRepository, CustomerRepository
from ..repositories.base import ConflictError
from .lead_extra_fields import expose_extra_fields, merge_extra_fields
from .permission_policy import mask_lead_for_tech

# Collaborator allowed fields (from docs/v0.5-page-api-matrix.md)
COLLABORATOR_ALLOWED_FIELDS = {
    "title",
    "product_category",
    "product_series",
    "power_range",
    "wavelength",
    "application",
    "material",
    "quality_grade",
    "urgency",
    "estimated_value",
    "next_followup_date",
    "quotation_id",
    "quotation_date",
    "extra_json",
}

# Collaborator restricted fields
COLLABORATOR_RESTRICTED_FIELDS = {
    "owner_id",
    "archived_at",
    "row_version",
    "fulfillment_status",
    "service_status",
    "deal_amount",
    "po_number",
    "currency",
}

STAGE_ORDER = {
    "New": 1,
    "Assigned": 2,
    "Following": 3,
    "Quoted": 4,
    "Won": 5,
    "Lost": 6,
}

class InvalidLeadAssignmentError(ValueError):
    """Raised when a member cannot hold a commercial lead assignment."""


def mask_lead_for_role(lead: dict, actor_role: str) -> dict:
    """Remove sales-sensitive fields from task-scoped technical views."""
    if actor_role != "tech":
        return lead
    return mask_lead_for_tech(lead)


class LeadService:
    """Lead management service."""

    def __init__(
        self,
        lead_repo: Optional[LeadRepository] = None,
        activity_repo: Optional[ActivityRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        customer_repo: Optional[CustomerRepository] = None,
    ):
        self.lead_repo = lead_repo or LeadRepository()
        self.activity_repo = activity_repo or ActivityRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.customer_repo = customer_repo or CustomerRepository()

    def _enrich_with_customer(self, lead: dict) -> dict:
        """Add nested customer data to lead."""
        if not lead or not lead.get("customer_id"):
            return lead

        expose_extra_fields(lead)

        if lead.get("id"):
            lead["follow_ups_count"] = self.activity_repo.count_follow_ups_for_lead(lead["id"])

        customer = self.customer_repo.get_by_id(lead["customer_id"])
        if customer:
            # Get customer contacts
            contacts = self.customer_repo.get_contacts(lead["customer_id"])
            lead["customer"] = {
                "id": customer["id"],
                "display_name": customer.get("display_name"),
                "country": customer.get("country"),
                "city": customer.get("city"),
                "postal_code": customer.get("postal_code"),
                "address": customer.get("address"),
                "region": customer.get("region"),
                "industry": customer.get("industry"),
                "customer_type": customer.get("customer_type"),
                "language": customer.get("language"),
                "website": customer.get("website"),
                "company_size": customer.get("company_size"),
                "company_description": customer.get("company_description"),
                "lat": customer.get("lat"),
                "lng": customer.get("lng"),
                "row_version": customer.get("row_version"),
                "contacts": contacts or [],
            }
        return lead

    def _enrich_leads(self, leads: list[dict]) -> list[dict]:
        """Batch enrich leads with customer data."""
        if not leads:
            return leads

        for lead in leads:
            expose_extra_fields(lead)

        follow_up_counts = self.activity_repo.count_follow_ups_by_lead(
            [lead["id"] for lead in leads if lead.get("id")]
        )

        # Collect unique customer IDs
        customer_ids = {l["customer_id"] for l in leads if l.get("customer_id")}
        if not customer_ids:
            for lead in leads:
                lead["follow_ups_count"] = follow_up_counts.get(lead.get("id"), 0)
            return leads

        # Batch fetch customers
        customers = {}
        contacts_by_customer = {}
        for cid in customer_ids:
            c = self.customer_repo.get_by_id(cid)
            if c:
                customers[cid] = c
                contacts_by_customer[cid] = self.customer_repo.get_contacts(cid) or []

        # Enrich leads
        for lead in leads:
            lead["follow_ups_count"] = follow_up_counts.get(lead.get("id"), 0)
            cid = lead.get("customer_id")
            if cid and cid in customers:
                c = customers[cid]
                lead["customer"] = {
                    "id": c["id"],
                    "display_name": c.get("display_name"),
                    "country": c.get("country"),
                    "city": c.get("city"),
                    "postal_code": c.get("postal_code"),
                    "address": c.get("address"),
                    "region": c.get("region"),
                    "industry": c.get("industry"),
                    "customer_type": c.get("customer_type"),
                    "language": c.get("language"),
                    "website": c.get("website"),
                    "company_size": c.get("company_size"),
                    "company_description": c.get("company_description"),
                    "lat": c.get("lat"),
                    "lng": c.get("lng"),
                    "row_version": c.get("row_version"),
                    "contacts": contacts_by_customer.get(cid, []),
                }

        return leads

    def create(self, data: dict, actor_id: str) -> dict:
        """Create new lead."""
        self._validate_commercial_assignee(data.get("owner_id"), "owner")
        data = merge_extra_fields(data)
        lead_id = self.lead_repo.create(data, actor_id)

        # Log audit
        self.audit_repo.log(
            entity_type="lead",
            entity_id=lead_id,
            event_type="create",
            actor_id=actor_id,
            after_json=json.dumps(data),
        )

        # Create system activity
        self.activity_repo.create(
            lead_id=lead_id,
            actor_id=actor_id,
            action_type="system",
            summary="Lead created",
        )

        return self.get(lead_id)

    def get(self, lead_id: str) -> Optional[dict]:
        """Get lead by ID with customer and assignments."""
        lead = self.lead_repo.get_by_id(lead_id)
        if not lead:
            return None

        lead["assignments"] = self.lead_repo.get_assignments(lead_id)
        return self._enrich_with_customer(lead)

    def get_by_display_id(self, display_id: str) -> Optional[dict]:
        """Get lead by display_id with customer."""
        lead = self.lead_repo.get_by_display_id(display_id)
        if not lead:
            return None
        lead["assignments"] = self.lead_repo.get_assignments(lead["id"])
        return self._enrich_with_customer(lead)

    def update(
        self,
        lead_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
        row_version: int,
    ) -> dict:
        """
        Update lead with permission and conflict checks.

        Args:
            lead_id: Lead UUID
            data: Fields to update
            actor_id: Current user ID
            actor_role: 'leader', 'owner', 'collaborator', etc.
            row_version: Expected version for optimistic locking
        """
        before = self.lead_repo.get_by_id(lead_id)
        if not before:
            raise ValueError(f"Lead {lead_id} not found")

        if "owner_id" in data:
            self._validate_commercial_assignee(data["owner_id"], "owner")
        data = merge_extra_fields(data, before.get("extra_json"))

        if "owner_id" in data and actor_role != "leader":
            raise PermissionError("Only leaders can change owner")

        self._apply_auto_stage_progression(data, before)

        # Permission check for watcher (read-only)
        if actor_role == "watcher":
            raise PermissionError("Watchers cannot edit leads")

        # Permission check for collaborator
        if actor_role == "collaborator":
            self._check_collaborator_permissions(data, before)

        try:
            # Track field changes for activity
            changes = self._detect_changes(before, data)

            updated = self.lead_repo.update(lead_id, data, actor_id, row_version)

            # Log audit
            self.audit_repo.log(
                entity_type="lead",
                entity_id=lead_id,
                event_type="update",
                actor_id=actor_id,
                before_json=json.dumps(dict(before)),
                after_json=json.dumps(data),
            )

            # Create field_change activities
            for field, (old_val, new_val) in changes.items():
                self.activity_repo.create(
                    lead_id=lead_id,
                    actor_id=actor_id,
                    action_type="field_change",
                    summary=f"Changed {field}",
                    changed_field=field,
                    before_value=str(old_val) if old_val is not None else None,
                    after_value=str(new_val) if new_val is not None else None,
                )

            return updated

        except ConflictError:
            raise

    def archive(self, lead_id: str, actor_id: str) -> bool:
        """Archive lead (leader only)."""
        success = self.lead_repo.archive(lead_id, actor_id)

        if success:
            self.audit_repo.log(
                entity_type="lead",
                entity_id=lead_id,
                event_type="archive",
                actor_id=actor_id,
            )

            self.activity_repo.create(
                lead_id=lead_id,
                actor_id=actor_id,
                action_type="system",
                summary="Lead archived",
            )

        return success

    def list(
        self,
        actor_id: str,
        actor_role: str,
        limit: int = 100,
        offset: int = 0,
        owner_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        sales_stage: Optional[str] = None,
        tech_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        """List leads with permission filtering and customer data."""
        if actor_role == "leader":
            # Leader sees all
            leads = self.lead_repo.list(
                limit=limit,
                offset=offset,
                owner_id=owner_id,
                customer_id=customer_id,
                sales_stage=sales_stage,
                tech_id=tech_id,
                search=search,
            )
        elif actor_role == "tech":
            leads = self.lead_repo.list(
                limit=limit,
                offset=offset,
                owner_id=owner_id,
                customer_id=customer_id,
                sales_stage=sales_stage,
                tech_id=actor_id,
                search=search,
            )
        else:
            owner_filter = None
            tech_filter = tech_id if actor_role == "sales" else None
            # Others see only related leads (with same filtering options)
            leads = self.lead_repo.get_leads_for_user(
                user_id=actor_id,
                limit=limit,
                offset=offset,
                sales_stage=sales_stage,
                owner_id=owner_filter,
                tech_id=tech_filter,
                customer_id=customer_id,
                search=search,
            )

        return [mask_lead_for_role(lead, actor_role) for lead in self._enrich_leads(leads)]

    def add_assignment(
        self,
        lead_id: str,
        user_id: str,
        assignment_type: str,
        actor_id: str,
    ) -> str:
        """Add assignment (leader only for owner changes)."""
        if assignment_type not in {"owner", "collaborator", "watcher"}:
            raise ValueError(f"Invalid assignment type: {assignment_type}")

        self._validate_commercial_assignee(user_id, assignment_type)

        lead = self.lead_repo.get_by_id(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        if assignment_type == "owner":
            self.lead_repo.update(
                lead_id,
                {"owner_id": user_id},
                actor_id,
                lead["row_version"],
            )
            assignment = next(
                (
                    item for item in self.lead_repo.get_assignments(lead_id)
                    if item["assignment_type"] == "owner" and item["user_id"] == user_id
                ),
                None,
            )
            assignment_id = assignment["id"] if assignment else ""
        else:
            assignment_id = self.lead_repo.add_assignment(
                lead_id, user_id, assignment_type, actor_id
            )
            self.lead_repo.conn.commit()

        # Create activity
        self.activity_repo.create(
            lead_id=lead_id,
            actor_id=actor_id,
            action_type="assignment",
            summary=f"Added {assignment_type}: {user_id}",
            payload_json=json.dumps({
                "change_type": f"add_{assignment_type}",
                "target_user_id": user_id,
                "assignment_type": assignment_type,
            }),
        )

        return assignment_id

    def _validate_commercial_assignee(self, user_id: Optional[str], assignment_type: str) -> None:
        """Keep Tech accounts out of owner and collaborator relationships."""
        if not user_id or assignment_type not in {"owner", "collaborator"}:
            return
        member = self.lead_repo.conn.execute(
            "SELECT role, is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not member or not member["is_active"]:
            raise InvalidLeadAssignmentError("Lead assignee must be an active member")
        if member["role"] == "tech":
            raise InvalidLeadAssignmentError(
                "Technical users cannot be lead owners or collaborators"
            )

    def remove_assignment(
        self,
        lead_id: str,
        user_id: str,
        assignment_type: str,
        actor_id: str,
    ) -> bool:
        """Remove assignment."""
        success = self.lead_repo.remove_assignment(lead_id, user_id, assignment_type)
        self.lead_repo.conn.commit()

        if success:
            self.activity_repo.create(
                lead_id=lead_id,
                actor_id=actor_id,
                action_type="assignment",
                summary=f"Removed {assignment_type}: {user_id}",
                payload_json=json.dumps({
                    "change_type": f"remove_{assignment_type}",
                    "target_user_id": user_id,
                    "assignment_type": assignment_type,
                }),
            )

        return success

    def archive_assignment(self, lead_id: str, assignment_id: str, actor_id: str) -> bool:
        """Archive assignment by ID."""
        assignment = self.lead_repo.get_assignment_by_id(assignment_id)
        if not assignment or assignment["lead_id"] != lead_id:
            return False
        if assignment["assignment_type"] == "owner":
            raise PermissionError("Owner assignment cannot be removed directly; change owner instead")

        success = self.lead_repo.archive_assignment(lead_id, assignment_id, actor_id)
        self.lead_repo.conn.commit()
        if success:
            self.activity_repo.create(
                lead_id=lead_id,
                actor_id=actor_id,
                action_type="assignment",
                summary=f"Removed {assignment['assignment_type']}: {assignment['user_id']}",
                payload_json=json.dumps({
                    "change_type": f"remove_{assignment['assignment_type']}",
                    "target_user_id": assignment["user_id"],
                    "assignment_type": assignment["assignment_type"],
                }),
            )
        return success

    def _check_collaborator_permissions(self, data: dict, current: dict) -> None:
        """Check if collaborator is allowed to modify these fields."""
        for field in data.keys():
            if field in COLLABORATOR_RESTRICTED_FIELDS:
                raise PermissionError(f"Collaborators cannot modify {field}")

            # Special check for sales_stage transitions
            if field == "sales_stage":
                new_stage = data[field]
                if new_stage in ("Won", "Lost"):
                    raise PermissionError(
                        f"Collaborators cannot change stage to {new_stage}"
                    )

    def _apply_auto_stage_progression(self, data: dict, current: dict) -> None:
        """Advance sales_stage from deal evidence, without moving stages backward."""
        if "sales_stage" in data:
            # If manually setting sales_stage to Won, also initialize fulfillment_status
            if data["sales_stage"] == "Won" and not current.get("fulfillment_status"):
                data["fulfillment_status"] = "Not Started"
            return

        current_stage = current.get("sales_stage") or "New"
        if current_stage in {"Won", "Lost"}:
            return

        merged = {**dict(current), **data}
        suggested_stage = None

        if (
            self._has_value(merged.get("po_number"))
            or self._has_value(merged.get("po_date"))
            or self._has_positive_number(merged.get("deal_amount"))
        ):
            suggested_stage = "Won"
        elif (
            self._has_value(merged.get("quotation_id"))
            or self._has_value(merged.get("quotation_date"))
        ):
            suggested_stage = "Quoted"

        if not suggested_stage:
            return

        current_order = STAGE_ORDER.get(current_stage, 0)
        suggested_order = STAGE_ORDER.get(suggested_stage, 0)
        if suggested_order > current_order:
            data["sales_stage"] = suggested_stage

            # Critical: Initialize fulfillment_status when auto-advancing to Won
            # This ensures Won orders immediately appear in Fulfillment team's work list
            if suggested_stage == "Won" and not current.get("fulfillment_status"):
                data["fulfillment_status"] = "Not Started"

    @staticmethod
    def _has_value(value) -> bool:
        return value is not None and str(value).strip() != ""

    @staticmethod
    def _has_positive_number(value) -> bool:
        if value is None or value == "":
            return False
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False

    def _detect_changes(self, before: dict, after: dict) -> dict:
        """Detect field changes for activity logging."""
        changes = {}
        for field, new_value in after.items():
            old_value = before.get(field)
            if old_value != new_value:
                changes[field] = (old_value, new_value)
        return changes
