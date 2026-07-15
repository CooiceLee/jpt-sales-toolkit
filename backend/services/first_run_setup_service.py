"""One-time local Leader setup for a new installation."""

from __future__ import annotations

from uuid import uuid4

from ..authorization import (
    build_device_request,
    initialize_issuer,
    issue_authorization,
    load_issuer_key,
    public_key_info,
)
from ..config import get_settings
from ..repositories import OrganizationRepository, UserRepository
from ..repositories.issuer_initialization_transaction import persist_initialized_issuer
from .offline_authorization_service import OfflineAuthorizationService
from .password_service import hash_password


class FirstRunSetupService:
    def __init__(self):
        self.users = UserRepository()
        self.organizations = OrganizationRepository()

    def bootstrap(self, data: dict) -> dict:
        if self.users.list_all():
            raise ValueError("First-run setup is no longer available")
        username = str(data["username"]).strip()
        display_name = str(data["display_name"]).strip()
        if not username or any(char.isspace() for char in username):
            raise ValueError("Username cannot be empty or contain spaces")
        if not display_name:
            raise ValueError("Display name cannot be empty")
        member = {
            "id": str(uuid4()), "username": username, "display_name": display_name,
            "role": "leader", "region": data.get("region") or None, "is_active": True,
        }
        password_hash = hash_password(data["password"])
        key_path = get_settings().runtime_config_dir / "authorization_issuer.pem"
        if key_path.exists():
            private_key = load_issuer_key(key_path, data["issuer_passphrase"])
            key_info = public_key_info(private_key.public_key())
        else:
            key_info = initialize_issuer(key_path, data["issuer_passphrase"])
            private_key = load_issuer_key(key_path, data["issuer_passphrase"])
        organization = self.organizations.get_default()
        if organization.get("signing_public_key"):
            raise ValueError("First-run setup is no longer available")
        package = issue_authorization(
            private_key, organization, member, build_device_request(), [member], days=90
        )
        persist_initialized_issuer(
            self.users.conn, package, key_info, member["id"],
            bootstrap_member=member, password_hash=password_hash,
        )
        return {
            "username": username,
            "status": OfflineAuthorizationService().status(),
        }
