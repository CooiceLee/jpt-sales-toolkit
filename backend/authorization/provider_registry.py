"""Authorization-provider resolver for offline and future server modes."""

from __future__ import annotations

from .provider import AuthorizationProvider


class RemoteProviderUnavailable(AuthorizationProvider):
    """Fail-closed placeholder until the server authorization adapter is configured."""

    def status(self) -> dict:
        return {
            "mode": "remote",
            "activated": False,
            "device_id": None,
            "trust_required": False,
            "member": None,
            "authorization": None,
            "issuer": {
                "initialized": False,
                "trusted": False,
                "can_initialize": False,
                "fingerprint": None,
            },
            "reason": "remote_provider_not_configured",
        }

    def validate_user(self, user: dict) -> bool:
        return False


def resolve_authorization_provider() -> AuthorizationProvider:
    from ..repositories import OrganizationRepository
    from ..services.offline_authorization_service import OfflineAuthorizationService

    organization = OrganizationRepository().get_default()
    if organization and organization.get("authorization_provider") == "remote":
        return RemoteProviderUnavailable()
    return OfflineAuthorizationService()
