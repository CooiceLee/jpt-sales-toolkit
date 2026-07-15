"""Lifecycle operations for device authorization repositories."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .authorization_common import apply_update, build_device_record, utc_naive
from .base import now_iso
from .device_authorization_transaction import replace_active_authorization


class DeviceAuthorizationLifecycle:
    """Deactivation and replacement behavior for device authorizations."""

    def deactivate(self, authorization_id: str, reason: str = "deactivated") -> bool:
        timestamp = now_iso()
        return apply_update(
            self,
            authorization_id,
            {
                "is_active": 0,
                "deactivated_at": timestamp,
                "deactivation_reason": reason,
                "updated_at": timestamp,
            },
        )

    def reactivate(self, authorization_id: str) -> bool:
        current = self.get_by_id(authorization_id)
        if not current:
            return False
        if utc_naive(current["expires_at"]) <= datetime.utcnow():
            raise ValueError("Expired device authorization cannot be reactivated")
        try:
            return apply_update(
                self,
                authorization_id,
                {
                    "is_active": 1,
                    "deactivated_at": None,
                    "deactivation_reason": None,
                    "updated_at": now_iso(),
                },
            )
        except sqlite3.IntegrityError:
            self.conn.rollback()
            self._raise_reactivation_conflict(authorization_id, current)
            raise

    def _raise_reactivation_conflict(self, authorization_id: str, current: dict) -> None:
        active_user = self.get_active_for_user(
            current["user_id"], current["organization_id"]
        )
        if active_user and active_user["id"] != authorization_id:
            raise ValueError("User already has an active device authorization") from None
        active_device = self._get_reserved_device(
            current["device_fingerprint_hash"], current["organization_id"]
        )
        if active_device and active_device["id"] != authorization_id:
            raise ValueError(
                "Device already has an active authorization in this organization"
            ) from None

    def replace_active(self, data: dict, reason: str = "device_replaced") -> str:
        """Atomically deactivate a user's old device and insert its replacement."""
        prepared = build_device_record(self.conn, data)
        current = self.get_active_for_user(prepared["user_id"], prepared["organization_id"])
        try:
            return replace_active_authorization(
                self.conn, current, prepared, reason, self._insert
            )
        except sqlite3.IntegrityError:
            active_device = self._get_reserved_device(
                prepared["device_fingerprint_hash"], prepared["organization_id"]
            )
            if active_device and active_device["user_id"] != prepared["user_id"]:
                raise ValueError(
                    "Device already has an active authorization in this organization"
                ) from None
            raise
