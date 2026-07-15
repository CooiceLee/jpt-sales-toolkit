"""Business rules and audit trail for customer aliases."""

from __future__ import annotations

import json
from typing import Optional

from ..repositories.audit_repository import AuditRepository
from ..repositories.customer_alias_repository import CustomerAliasRepository, normalize_alias
from ..repositories.customer_repository import CustomerRepository


class CustomerAliasService:
    def __init__(self, customer_repo: Optional[CustomerRepository] = None):
        self.customer_repo = customer_repo or CustomerRepository()
        self.alias_repo = CustomerAliasRepository(self.customer_repo.conn)
        self.audit_repo = AuditRepository(self.customer_repo.conn)

    def list(self, customer_id: str, include_archived: bool = False) -> list[dict]:
        return self.alias_repo.list_for_customer(customer_id, include_archived)

    def create(self, customer_id: str, alias_name: str, actor_id: str) -> dict:
        name = self._validate_name(customer_id, alias_name)
        result = self.alias_repo.create(customer_id, name, actor_id)
        self._audit("create", result, actor_id)
        return result

    def update(self, customer_id: str, alias_id: str, alias_name: str, actor_id: str) -> dict:
        before = self.alias_repo.get_for_customer(customer_id, alias_id)
        if not before or before.get("archived_at"):
            raise ValueError("Active customer alias not found")
        name = self._validate_name(customer_id, alias_name, alias_id)
        result = self.alias_repo.update(customer_id, alias_id, name, actor_id)
        self._audit("update", result, actor_id, before)
        return result

    def archive(self, customer_id: str, alias_id: str, actor_id: str) -> dict:
        before = self.alias_repo.get_for_customer(customer_id, alias_id)
        if not before or before.get("archived_at"):
            raise ValueError("Active customer alias not found")
        result = self.alias_repo.set_archived(customer_id, alias_id, actor_id, True)
        self._audit("archive", result, actor_id, before)
        return result

    def restore(self, customer_id: str, alias_id: str, actor_id: str) -> dict:
        before = self.alias_repo.get_for_customer(customer_id, alias_id)
        if not before or not before.get("archived_at"):
            raise ValueError("Archived customer alias not found")
        self._validate_name(customer_id, before["alias_name"], alias_id)
        result = self.alias_repo.set_archived(customer_id, alias_id, actor_id, False)
        self._audit("restore", result, actor_id, before)
        return result

    def _validate_name(self, customer_id: str, value: str, alias_id: Optional[str] = None) -> str:
        name = str(value or "").strip()
        normalized = normalize_alias(name)
        if not normalized:
            raise ValueError("Alias name is required")
        customer = self.customer_repo.get_by_id(customer_id)
        if not customer or customer.get("archived_at"):
            raise ValueError("Active customer not found")
        if normalize_alias(customer.get("display_name")) == normalized:
            raise ValueError("Alias duplicates the customer display name")
        row = self.customer_repo.conn.execute(
            "SELECT id FROM customers WHERE normalized_name = ? AND archived_at IS NULL AND id != ?",
            (normalized, customer_id),
        ).fetchone()
        duplicate = self.customer_repo.conn.execute(
            """SELECT id, archived_at FROM customer_aliases WHERE customer_id = ?
               AND normalized_alias = ? AND id != ? LIMIT 1""",
            (customer_id, normalized, alias_id or ""),
        ).fetchone()
        owner = self.alias_repo.find_active_customer(normalized)
        current = self.alias_repo.get_for_customer(customer_id, alias_id) if alias_id else None
        if row or (owner and owner != customer_id):
            raise ValueError("Alias belongs to another active customer")
        if duplicate and (alias_id or duplicate["archived_at"] is None):
            raise ValueError("Customer alias already exists")
        if owner == customer_id and (not current or current.get("normalized_alias") != normalized):
            raise ValueError("Customer alias already exists")
        return name

    def _audit(self, event: str, after: dict, actor_id: str, before: Optional[dict] = None) -> None:
        self.audit_repo.log(
            entity_type="customer_alias",
            entity_id=after["id"],
            event_type=event,
            actor_id=actor_id,
            before_json=json.dumps(before, ensure_ascii=False) if before else None,
            after_json=json.dumps(after, ensure_ascii=False),
        )
