"""Non-mutating customer merge inventory and conflict preview."""

from __future__ import annotations

from typing import Optional

from ..repositories.base import ConflictError


MERGEABLE_FIELDS = (
    "website", "industry", "customer_type", "company_size", "language", "country",
    "city", "postal_code", "address", "region", "lat", "lng", "normalized_address",
    "geocode_source", "geocode_confidence", "geocode_locked", "company_description",
)


class CustomerMergePreview:
    def __init__(self, conn):
        self.conn = conn

    def build(
        self,
        source_id: str,
        target_id: str,
        source_version: Optional[int],
        target_version: Optional[int],
    ) -> dict:
        if source_id == target_id:
            raise ValueError("Source and target customer must be different")
        if source_version is None or target_version is None:
            raise ValueError("Source and target row versions are required")
        self._require_lifecycle("customer_aliases")
        self._require_lifecycle("customer_domains")
        source = self._active_customer(source_id, "Source")
        target = self._active_customer(target_id, "Target")
        self._assert_version(source, source_version)
        self._assert_version(target, target_version)

        relations = {
            "leads": self._rows("leads", source_id),
            "trip_plan_stops": self._rows("trip_plan_stops", source_id),
            "contacts": self._rows("customer_contacts", source_id),
            "domains": self._rows("customer_domains", source_id),
            "aliases": self._rows("customer_aliases", source_id),
        }
        target_identity = {
            "contacts": self._rows("customer_contacts", target_id),
            "domains": self._rows("customer_domains", target_id),
            "aliases": self._rows("customer_aliases", target_id),
        }
        field_updates = {}
        field_conflicts = []
        for field in MERGEABLE_FIELDS:
            source_value, target_value = source.get(field), target.get(field)
            if target_value in (None, "") and source_value not in (None, ""):
                field_updates[field] = source_value
            elif source_value not in (None, "") and target_value not in (None, "") and source_value != target_value:
                field_conflicts.append({
                    "field": field, "source": source_value, "target": target_value,
                    "resolution": "keep_target",
                })
        if source.get("extra_json") not in (None, "") and source.get("extra_json") != target.get("extra_json"):
            field_conflicts.append({
                "field": "extra_json", "source": source.get("extra_json"),
                "target": target.get("extra_json"), "resolution": "preserved_in_audit_manifest",
            })
        return {
            "source_customer": source,
            "target_customer": target,
            "source_relations": relations,
            "target_identity": target_identity,
            "counts": {name: len(rows) for name, rows in relations.items()},
            "field_updates": field_updates,
            "field_conflicts": field_conflicts,
            "contact_conflicts": self._contact_conflicts(relations["contacts"], target_identity["contacts"]),
            "domain_conflicts": self._value_conflicts(relations["domains"], target_identity["domains"], "domain"),
            "alias_conflicts": self._value_conflicts(relations["aliases"], target_identity["aliases"], "normalized_alias"),
        }

    def _active_customer(self, customer_id: str, label: str) -> dict:
        row = self.conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not row or row["archived_at"]:
            raise ValueError(f"{label} customer not found")
        return dict(row)

    def _rows(self, table: str, customer_id: str) -> list[dict]:
        rows = self.conn.execute(f"SELECT * FROM {table} WHERE customer_id = ?", (customer_id,)).fetchall()
        return [dict(row) for row in rows]

    def _require_lifecycle(self, table: str) -> None:
        columns = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if not {"archived_at", "updated_at", "updated_by"}.issubset(columns):
            raise RuntimeError(f"{table} lifecycle migration is required")

    @staticmethod
    def _assert_version(customer: dict, expected: int) -> None:
        if customer["row_version"] != expected:
            raise ConflictError(
                current_version=customer["row_version"], your_version=expected,
                current_data={"id": customer["id"], "updated_at": customer["updated_at"]},
            )

    @staticmethod
    def _value_conflicts(source: list[dict], target: list[dict], field: str) -> list[dict]:
        target_values = {str(row.get(field) or "").lower() for row in target}
        return [row for row in source if str(row.get(field) or "").lower() in target_values]

    @staticmethod
    def _contact_conflicts(source: list[dict], target: list[dict]) -> list[dict]:
        target_by_email = {str(row.get("email") or "").lower(): row for row in target if row.get("email")}
        result = []
        for row in source:
            other = target_by_email.get(str(row.get("email") or "").lower())
            if other:
                result.append({"source": row, "target": other})
        return result
