"""Canonical entity storage and customer/lead identity helpers."""

from __future__ import annotations

from typing import Any, Optional

from .keys import clean_text, normalize_text, stable_external_key
from .legacy_constants import CUSTOMER_CANONICAL_NAMES, SHEET_CODES


class EntityStoreMixin:
    def source_ref(self, sheet: str, row: int) -> dict:
        return {"sheet": sheet, "row": row,
                "record_key": f"{SHEET_CODES[sheet]}:{row:04d}"}

    def add_issue(self, severity: str, code: str, ref: dict, message: str,
                  field: Optional[str] = None, raw_value: Any = None,
                  entity_key: Optional[str] = None) -> None:
        issue = {"severity": severity, "code": code, "source_ref": ref, "message": message}
        if field:
            issue["field"] = field
        if raw_value not in (None, ""):
            issue["raw_value"] = raw_value
        if entity_key:
            issue["entity_key"] = entity_key
        self.issues.append(issue)

    def add_entity(self, kind: str, entity: dict) -> dict:
        key = entity["external_key"]
        existing = self._indexes[kind].get(key)
        if existing:
            refs = existing.setdefault("source_refs", [existing["source_ref"]])
            if entity["source_ref"] not in refs:
                refs.append(entity["source_ref"])
            return existing
        self.entities[kind].append(entity)
        self._indexes[kind][key] = entity
        return entity

    def ensure_customer(self, name: Any, ref: dict, **fields: Any) -> Optional[str]:
        raw_name = clean_text(name)
        if not raw_name:
            return None
        canonical_name = CUSTOMER_CANONICAL_NAMES.get(normalize_text(raw_name), raw_name)
        normalized = normalize_text(canonical_name)
        existing = self._customer_by_name.get(normalized)
        if existing is None:
            key = stable_external_key(self.dataset_id, "CUS", normalized)
            entity = {"external_key": key, "source_ref": ref, "display_name": canonical_name}
            entity.update({key: clean_text(value) for key, value in fields.items() if clean_text(value)})
            existing = self.add_entity("customers", entity)
            self._customer_by_name[normalized] = existing
        else:
            for field, value in fields.items():
                if clean_text(value) and not existing.get(field):
                    existing[field] = clean_text(value)
        if raw_name != existing["display_name"]:
            self.ensure_alias(existing["external_key"], raw_name, ref)
        return existing["external_key"]

    def ensure_alias(self, customer_key: str, alias_name: str, ref: dict) -> str:
        key = stable_external_key(self.dataset_id, "ALS", customer_key, normalize_text(alias_name))
        self.add_entity("aliases", {
            "external_key": key, "source_ref": ref, "customer_key": customer_key,
            "alias_name": clean_text(alias_name),
        })
        return key

    def ensure_contact(self, customer_key: Optional[str], name: Any, ref: dict) -> Optional[str]:
        contact_name = clean_text(name)
        if not customer_key or not contact_name or contact_name in {"/", "?", "？"}:
            return None
        key = stable_external_key(self.dataset_id, "CON", customer_key, normalize_text(contact_name))
        self.add_entity("contacts", {
            "external_key": key, "source_ref": ref, "customer_key": customer_key,
            "name": contact_name,
        })
        return key

    def add_lead(self, ref: dict, **fields: Any) -> dict:
        key = fields.pop("external_key", None) or stable_external_key(
            self.dataset_id, "LEAD", ref["sheet"], ref["row"])
        return self.add_entity("leads", {"external_key": key, "source_ref": ref, **fields})

    @staticmethod
    def merge_lead(lead: dict, ref: dict, **fields: Any) -> dict:
        refs = lead.setdefault("source_refs", [lead["source_ref"]])
        if ref not in refs:
            refs.append(ref)
        for field, value in fields.items():
            if value not in (None, ""):
                lead[field] = value
        return lead
