"""Organization repository for local and future remote authorization modes."""

from __future__ import annotations

from typing import Optional

from .authorization_common import VALID_AUTHORIZATION_PROVIDERS, apply_update
from .base import BaseRepository, DEFAULT_ORGANIZATION_ID, generate_uuid, now_iso


class OrganizationRepository(BaseRepository):
    """Manage organizations and their authorization provider settings."""

    table_name = "organizations"
    _updatable = {
        "name",
        "slug",
        "authorization_provider",
        "authorization_duration_days",
        "signing_key_id",
        "signing_public_key",
    }

    def get_default(self) -> Optional[dict]:
        return self.get_by_id(DEFAULT_ORGANIZATION_ID)

    def get_by_slug(self, slug: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM organizations WHERE slug = ?", (slug,)
        ).fetchone()
        return dict(row) if row else None

    def list_all(self, include_inactive: bool = False) -> list[dict]:
        sql = "SELECT * FROM organizations"
        if not include_inactive:
            sql += " WHERE is_active = 1"
        rows = self.conn.execute(sql + " ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def create(self, data: dict) -> str:
        provider = data.get("authorization_provider", "offline")
        if provider not in VALID_AUTHORIZATION_PROVIDERS:
            raise ValueError(f"Unsupported authorization provider: {provider}")
        if not data.get("name") or not data.get("slug"):
            raise ValueError("Organization name and slug are required")

        timestamp = now_iso()
        organization_id = data.get("id") or generate_uuid()
        insert_data = {
            "id": organization_id,
            "name": data["name"],
            "slug": data["slug"],
            "authorization_provider": provider,
            "authorization_duration_days": data.get("authorization_duration_days", 90),
            "signing_key_id": data.get("signing_key_id"),
            "signing_public_key": data.get("signing_public_key"),
            "is_active": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        sql, params = self._build_insert(insert_data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return organization_id

    def update(self, organization_id: str, data: dict) -> bool:
        unknown = set(data) - self._updatable
        if unknown:
            raise ValueError(f"Unsupported organization fields: {sorted(unknown)}")
        provider = data.get("authorization_provider")
        if provider and provider not in VALID_AUTHORIZATION_PROVIDERS:
            raise ValueError(f"Unsupported authorization provider: {provider}")
        duration = data.get("authorization_duration_days")
        if duration is not None and int(duration) <= 0:
            raise ValueError("Authorization duration must be positive")
        return apply_update(self, organization_id, {**data, "updated_at": now_iso()})

    def deactivate(self, organization_id: str) -> bool:
        timestamp = now_iso()
        return apply_update(
            self,
            organization_id,
            {"is_active": 0, "deactivated_at": timestamp, "updated_at": timestamp},
        )

    def reactivate(self, organization_id: str) -> bool:
        return apply_update(
            self,
            organization_id,
            {"is_active": 1, "deactivated_at": None, "updated_at": now_iso()},
        )
