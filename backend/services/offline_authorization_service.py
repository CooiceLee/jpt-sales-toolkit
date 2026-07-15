"""Installed offline authorization status, activation, and login guard."""

from __future__ import annotations

import hmac
from typing import Optional

from ..authorization import build_device_request, device_fingerprint, verify_authorization
from ..authorization.provider import AuthorizationProvider
from ..authorization.common import AuthorizationError
from ..repositories import (
    DeviceAuthorizationRepository,
    OrganizationRepository,
    UserRepository,
)
from ..repositories.offline_activation_transaction import activate_verified_package
from .offline_authorization_status import build_installation_status
from .password_service import hash_password


class OfflineAuthorizationService(AuthorizationProvider):
    """Manage the one installed member authorization on this device."""

    def __init__(self):
        self.organizations = OrganizationRepository()
        self.users = UserRepository()
        self.authorizations = DeviceAuthorizationRepository()

    def status(self) -> dict:
        organization = self.organizations.get_default()
        current_device = device_fingerprint()
        active = self.authorizations.get_active_for_device(current_device)
        member = self.users.get_by_id(active["user_id"]) if active else None
        return build_installation_status(
            organization, current_device, active, member, bool(self.users.list_all())
        )

    def create_device_request(self) -> dict:
        self._ensure_offline_provider()
        return build_device_request()

    def activate(
        self,
        package: dict,
        password: str,
        issuer_fingerprint: Optional[str] = None,
    ) -> dict:
        organization = self.organizations.get_default()
        self._ensure_offline_provider(organization)
        verified = verify_authorization(
            package,
            device_fingerprint(),
            trusted_public_key=organization.get("signing_public_key"),
        )
        self._verify_first_trust(organization, verified, issuer_fingerprint)
        payload = verified["payload"]
        if payload["organization"]["id"] != organization["id"]:
            raise AuthorizationError("Authorization belongs to a different organization")
        member = payload["member"]
        if not member.get("is_active", True):
            raise AuthorizationError("Member authorization is inactive")

        password_hash = hash_password(password)
        activate_verified_package(
            self.authorizations.conn, package, verified, password_hash
        )
        return self.status()

    def validate_user(self, user: dict) -> bool:
        status = self.status()
        if status["mode"] == "legacy":
            return True
        member = status.get("member") or {}
        return bool(
            status["mode"] == "offline"
            and status["activated"]
            and member.get("id") == user.get("id")
            and member.get("role") == user.get("role")
        )

    def _ensure_offline_provider(self, organization: Optional[dict] = None) -> None:
        current = organization or self.organizations.get_default()
        if current.get("authorization_provider") != "offline":
            raise AuthorizationError("This installation uses remote authorization")

    @staticmethod
    def _verify_first_trust(organization: dict, verified: dict, provided: Optional[str]) -> None:
        if organization.get("signing_public_key"):
            return
        normalized = "".join(char for char in str(provided or "").lower() if char in "0123456789abcdef")
        valid_codes = {verified["key_id"].lower(), verified["fingerprint"].lower()}
        if not normalized or not any(
            hmac.compare_digest(normalized, expected) for expected in valid_codes
        ):
            raise AuthorizationError("Leader verification code does not match this authorization")
