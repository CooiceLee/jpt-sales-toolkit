"""Signed single-device authorization repository."""

from __future__ import annotations

from .base import BaseRepository
from .device_authorization_lifecycle import DeviceAuthorizationLifecycle
from .device_authorization_queries import DeviceAuthorizationQueries
from .device_authorization_writes import DeviceAuthorizationWrites


class DeviceAuthorizationRepository(
    DeviceAuthorizationQueries,
    DeviceAuthorizationWrites,
    DeviceAuthorizationLifecycle,
    BaseRepository,
):
    """Manage signed, single-device, time-limited offline authorizations."""

    table_name = "device_authorizations"
    _updatable = {
        "role",
        "activation_state",
        "payload_json",
        "signature",
        "signature_algorithm",
        "signing_key_id",
        "valid_from",
        "expires_at",
        "authorization_version",
    }

    def _insert(self, data: dict) -> None:
        sql, params = self._build_insert(data)
        self.conn.execute(sql, params)
