"""Customer and lead replicas used by an offline Tech installation."""

from __future__ import annotations

import json
from typing import Optional

from ..repositories.base import generate_uuid, now_iso
from ..repositories.lead_repository import LeadRepository
from .customer_service import normalize_name
from .lead_extra_fields import parse_extra_json
from .tech_task_exchange_contract import CUSTOMER_CONTEXT_FIELDS, LEAD_CONTEXT_FIELDS, project


class ReplicaContextMixin:
    """Create or refresh only the minimal customer/lead context in a task package."""

    def _ensure_replica_context(
        self, item: dict, package: dict, actor: dict, binding: Optional[dict]
    ) -> tuple[str, str]:
        lead_binding = binding or self.repo.find_context_binding(
            package["organization_id"],
            actor["id"],
            source_lead_id=item["source_lead_id"],
        )
        customer_binding = lead_binding or self.repo.find_context_binding(
            package["organization_id"],
            actor["id"],
            source_customer_id=item["source_customer_id"],
        )
        customer_id = customer_binding.get("local_customer_id") if customer_binding else None
        if not customer_id or not self._row("customers", customer_id):
            customer_id = self._create_replica_customer(item, package, actor)
        else:
            self._update_replica_customer(customer_id, item["customer_context"], actor["id"])
        lead_id = lead_binding.get("local_lead_id") if lead_binding else None
        if not lead_id or not self._row("leads", lead_id):
            lead_id = self._create_replica_lead(item, package, actor, customer_id)
        else:
            self._update_replica_lead(
                lead_id, customer_id, item["lead_context"], actor["id"]
            )
        return customer_id, lead_id

    def _create_replica_customer(self, item: dict, package: dict, actor: dict) -> str:
        customer_id = generate_uuid()
        customer = item["customer_context"]
        display_name = customer.get("display_name") or "Technical task customer"
        timestamp = now_iso()
        self.conn.execute(
            """INSERT INTO customers (
                id, display_name, normalized_name, industry, customer_type,
                country, city, region, language, company_size, company_description,
                extra_json, created_at, created_by, updated_at, updated_by, row_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                customer_id, display_name, normalize_name(display_name),
                customer.get("industry"), customer.get("customer_type"),
                customer.get("country"), customer.get("city"), customer.get("region"),
                customer.get("language"), customer.get("company_size"),
                customer.get("company_description"),
                json.dumps({
                    "tech_task_replica": True,
                    "source_customer_id": item["source_customer_id"],
                }),
                timestamp, package["source_user_id"], timestamp, actor["id"],
            ),
        )
        return customer_id

    def _create_replica_lead(
        self, item: dict, package: dict, actor: dict, customer_id: str
    ) -> str:
        lead_id = generate_uuid()
        lead = item["lead_context"]
        extra = {
            key: lead.get(key)
            for key in ("special_requirements", "potential_needs", "products_detail")
            if lead.get(key) not in (None, "")
        }
        extra.update({"tech_task_replica": True, "source_lead_id": item["source_lead_id"]})
        timestamp = now_iso()
        self.conn.execute(
            """INSERT INTO leads (
                id, display_id, customer_id, title, owner_id, sales_stage,
                fulfillment_status, service_status, quality_grade, urgency,
                product_category, product_series, power_range, wavelength,
                application, material, quantity_text, next_followup_date, inquiry_date,
                extra_json, created_at, created_by, updated_at, updated_by, row_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                lead_id, self._replica_display_id(lead.get("display_id")), customer_id,
                lead.get("title") or "Technical task", package["source_user_id"],
                lead.get("sales_stage") or "Following",
                lead.get("fulfillment_status") or "Not Started",
                lead.get("service_status") or "None", lead.get("quality_grade"),
                lead.get("urgency"), lead.get("product_category"),
                lead.get("product_series"), lead.get("power_range"),
                lead.get("wavelength"), lead.get("application"), lead.get("material"),
                lead.get("quantity_text"), lead.get("next_followup_date"),
                lead.get("inquiry_date"),
                json.dumps(extra, ensure_ascii=False, separators=(",", ":")), timestamp,
                package["source_user_id"], timestamp, actor["id"],
            ),
        )
        return lead_id

    def _replica_display_id(self, requested: Optional[str]) -> str:
        exists = requested and self.conn.execute(
            "SELECT 1 FROM leads WHERE display_id = ?", (requested,)
        ).fetchone()
        return LeadRepository(self.conn).generate_display_id() if exists or not requested else requested

    def _update_replica_customer(
        self, customer_id: str, context: dict, actor_id: str
    ) -> None:
        current = self._row("customers", customer_id)
        values = project(context, CUSTOMER_CONTEXT_FIELDS)
        if values.get("display_name"):
            values["normalized_name"] = normalize_name(values["display_name"])
        changed = {key: value for key, value in values.items() if current.get(key) != value}
        if changed:
            assignments = ", ".join(f"{key} = ?" for key in changed)
            self.conn.execute(
                f"""UPDATE customers SET {assignments}, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1 WHERE id = ?""",
                (*changed.values(), now_iso(), actor_id, customer_id),
            )

    def _update_replica_lead(
        self, lead_id: str, customer_id: str, context: dict, actor_id: str
    ) -> None:
        current = self._row("leads", lead_id)
        extra_fields = {
            "display_id", "special_requirements", "potential_needs", "products_detail"
        }
        values = project(context, LEAD_CONTEXT_FIELDS - extra_fields)
        values["customer_id"] = customer_id
        extra = parse_extra_json(current.get("extra_json"))
        for key in ("special_requirements", "potential_needs", "products_detail"):
            if key in context:
                if context[key] in (None, ""):
                    extra.pop(key, None)
                else:
                    extra[key] = context[key]
        values["extra_json"] = json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
        changed = {key: value for key, value in values.items() if current.get(key) != value}
        if changed:
            assignments = ", ".join(f"{key} = ?" for key in changed)
            self.conn.execute(
                f"""UPDATE leads SET {assignments}, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1 WHERE id = ?""",
                (*changed.values(), now_iso(), actor_id, lead_id),
            )
