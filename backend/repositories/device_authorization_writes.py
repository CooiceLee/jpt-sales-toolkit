"""Create and update operations for device authorization repositories."""

from __future__ import annotations

import sqlite3

from .authorization_common import (
    VALID_ACTIVATION_STATES,
    VALID_ROLES,
    apply_update,
    build_device_record,
    json_text,
    validate_authorization_window,
)
from .base import DEFAULT_ORGANIZATION_ID, now_iso


class DeviceAuthorizationWrites:
    """Validated writes shared by the device authorization repository."""

    def create(self, data: dict) -> str:
        prepared = build_device_record(self.conn, data)
        try:
            self._insert(prepared)
            self.conn.commit()
        except sqlite3.IntegrityError:
            self.conn.rollback()
            active = self.get_active_for_user(
                prepared["user_id"], prepared["organization_id"]
            )
            if active:
                raise ValueError("User already has an active device authorization") from None
            active_device = self._get_reserved_device(
                prepared["device_fingerprint_hash"], prepared["organization_id"]
            )
            if active_device:
                raise ValueError(
                    "Device already has an active authorization in this organization"
                ) from None
            raise
        return prepared["id"]

    def update(self, authorization_id: str, data: dict) -> bool:
        unknown = set(data) - self._updatable
        if unknown:
            raise ValueError(f"Unsupported authorization fields: {sorted(unknown)}")
        update_data = dict(data)
        self._validate_update_values(update_data)
        if "payload_json" in update_data:
            update_data["payload_json"] = json_text(update_data["payload_json"])
        current = self.get_by_id(authorization_id)
        if current:
            validate_authorization_window(
                update_data.get("valid_from", current["valid_from"]),
                update_data.get("expires_at", current["expires_at"]),
            )
        update_data["updated_at"] = now_iso()
        try:
            return apply_update(self, authorization_id, update_data)
        except sqlite3.IntegrityError:
            self.conn.rollback()
            target = {**current, **update_data} if current else update_data
            active_device = self._get_reserved_device(
                target.get("device_fingerprint_hash", ""),
                target.get("organization_id", DEFAULT_ORGANIZATION_ID),
            )
            if active_device and active_device["id"] != authorization_id:
                raise ValueError(
                    "Device already has an active authorization in this organization"
                ) from None
            raise

    @staticmethod
    def _validate_update_values(data: dict) -> None:
        if "role" in data and data["role"] not in VALID_ROLES:
            raise ValueError(f"Unsupported role: {data['role']}")
        if (
            "activation_state" in data
            and data["activation_state"] not in VALID_ACTIVATION_STATES
        ):
            raise ValueError(f"Unsupported activation state: {data['activation_state']}")
