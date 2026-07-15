"""Renew or recover the Leader device without weakening member activation."""

from __future__ import annotations

from ..authorization import (
    build_device_request,
    issue_authorization,
    load_issuer_key,
    public_key_info,
)
from ..authorization.common import AuthorizationError
from ..authorization.clock import AuthorizationClock
from ..authorization.common import utc_now
from ..config import get_settings
from ..repositories import (
    AuthorizationEventRepository,
    DeviceAuthorizationRepository,
    OrganizationRepository,
    UserCredentialRepository,
    UserRepository,
)
from .offline_authorization_service import OfflineAuthorizationService
from .password_service import verify_password


class LeaderAuthorizationRecoveryService:
    def __init__(self):
        self.users = UserRepository()
        self.credentials = UserCredentialRepository()
        self.organizations = OrganizationRepository()
        self.authorizations = DeviceAuthorizationRepository()
        self.events = AuthorizationEventRepository()

    def renew(self, actor_id: str, passphrase: str) -> dict:
        actor = self._active_leader(actor_id)
        return self._issue_local(actor, passphrase, "leader_authorization_renewed")

    def recover(self, username: str, password: str, passphrase: str) -> dict:
        user = self.users.get_by_username(username)
        if not user or not user["is_active"] or user["role"] != "leader":
            raise AuthorizationError("Leader recovery credentials are invalid")
        credential = self.credentials.get_by_user_id(user["id"], active_only=True)
        password_hash = credential["password_hash"] if credential else user["password_hash"]
        if not verify_password(password, password_hash):
            raise AuthorizationError("Leader recovery credentials are invalid")
        return self._issue_local(user, passphrase, "leader_authorization_recovered")

    def _issue_local(self, leader: dict, passphrase: str, event_type: str) -> dict:
        organization = self.organizations.get_default()
        if organization.get("authorization_provider") != "offline":
            raise AuthorizationError("Leader recovery requires offline authorization")
        key_path = get_settings().runtime_config_dir / "authorization_issuer.pem"
        private_key = load_issuer_key(key_path, passphrase)
        key_info = public_key_info(private_key.public_key())
        if key_info["public_key"] != organization.get("signing_public_key"):
            raise AuthorizationError("Issuer key does not match this organization")
        package = issue_authorization(
            private_key,
            organization,
            leader,
            build_device_request(),
            self.users.list_all(),
            days=int(organization["authorization_duration_days"]),
        )
        payload = package["payload"]
        authorization_id = self.authorizations.replace_active({
            "id": payload["package_id"],
            "user_id": leader["id"],
            "device_fingerprint_hash": payload["device"]["id"],
            "role": "leader",
            "activation_state": "activated",
            "payload_json": payload,
            "signature": package["signature"]["value"],
            "signing_key_id": package["signature"]["key_id"],
            "issued_at": payload["issued_at"],
            "valid_from": payload["valid_from"],
            "expires_at": payload["expires_at"],
            "created_by": leader["id"],
        }, reason=event_type)
        self.events.create({
            "event_type": event_type,
            "actor_user_id": leader["id"],
            "user_id": leader["id"],
            "device_authorization_id": authorization_id,
        })
        AuthorizationClock(get_settings().runtime_config_dir).reset(utc_now())
        return OfflineAuthorizationService().status()

    def _active_leader(self, user_id: str) -> dict:
        user = self.users.get_by_id(user_id)
        if not user or not user["is_active"] or user["role"] != "leader":
            raise AuthorizationError("Only an active Leader can renew this authorization")
        return user
