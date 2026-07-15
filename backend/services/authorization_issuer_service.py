"""Leader-side issuer initialization and member package signing."""

from __future__ import annotations

from ..authorization import (
    build_device_request,
    initialize_issuer,
    issue_authorization,
    load_issuer_key,
    public_key_info,
)
from ..authorization.common import AuthorizationError
from ..config import get_settings
from ..repositories import (
    AuthorizationEventRepository,
    DeviceAuthorizationRepository,
    OrganizationRepository,
    UserRepository,
)
from ..repositories.issuer_initialization_transaction import persist_initialized_issuer


class AuthorizationIssuerService:
    def __init__(self):
        self.organizations = OrganizationRepository()
        self.users = UserRepository()
        self.authorizations = DeviceAuthorizationRepository()
        self.events = AuthorizationEventRepository()

    @property
    def key_path(self):
        return get_settings().runtime_config_dir / "authorization_issuer.pem"

    def initialize(self, passphrase: str, actor_id: str) -> dict:
        organization = self.organizations.get_default()
        if organization.get("signing_public_key"):
            raise AuthorizationError("Authorization issuer is already initialized")
        actor = self.users.get_by_id(actor_id)
        if not actor or not actor["is_active"] or actor["role"] != "leader":
            raise AuthorizationError("Only an active Leader can initialize the issuer")

        if self.key_path.exists():
            private_key = load_issuer_key(self.key_path, passphrase)
            key_info = public_key_info(private_key.public_key())
        else:
            key_info = initialize_issuer(self.key_path, passphrase)
            private_key = load_issuer_key(self.key_path, passphrase)

        package = issue_authorization(
            private_key,
            organization,
            actor,
            build_device_request(),
            self.users.list_all(),
            days=int(organization["authorization_duration_days"]),
        )
        persist_initialized_issuer(
            self.authorizations.conn, package, key_info, actor_id
        )
        return {"initialized": True, **key_info}

    def issue(
        self,
        member_id: str,
        device_request: dict,
        passphrase: str,
        actor_id: str,
        days: int = 90,
    ) -> dict:
        member = self.users.get_by_id(member_id)
        if not member or not member["is_active"]:
            raise AuthorizationError("Member is not active")
        private_key = load_issuer_key(self.key_path, passphrase)
        organization = self.organizations.get_default()
        policy_days = int(organization["authorization_duration_days"])
        if int(days) != policy_days:
            raise AuthorizationError(f"Authorization period is fixed at {policy_days} days")
        key_info = public_key_info(private_key.public_key())
        if key_info["public_key"] != organization.get("signing_public_key"):
            raise AuthorizationError("Issuer key does not match this organization")
        package = issue_authorization(
            private_key,
            organization,
            member,
            device_request,
            self.users.list_all(),
            days=policy_days,
        )
        payload = package["payload"]
        authorization_id = self._store_package(package, actor_id, "issued")
        self.events.create({
            "event_type": "authorization_issued", "actor_user_id": actor_id,
            "user_id": member_id, "device_authorization_id": authorization_id,
            "event_data_json": {"days": policy_days, "device": payload["device"]["name"]},
        })
        return package

    def _store_package(self, package: dict, actor_id: str, activation_state: str) -> str:
        payload = package["payload"]
        member = payload["member"]
        return self.authorizations.replace_active({
            "id": payload["package_id"],
            "user_id": member["id"],
            "device_fingerprint_hash": payload["device"]["id"],
            "role": member["role"],
            "activation_state": activation_state,
            "payload_json": payload,
            "signature": package["signature"]["value"],
            "signing_key_id": package["signature"]["key_id"],
            "issued_at": payload["issued_at"],
            "valid_from": payload["valid_from"],
            "expires_at": payload["expires_at"],
            "created_by": actor_id,
        }, reason=f"authorization_{activation_state}")
