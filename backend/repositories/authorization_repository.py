"""Compatibility exports for the split authorization repositories."""

from .authorization_event_repository import AuthorizationEventRepository
from .device_authorization_repository import DeviceAuthorizationRepository
from .organization_repository import OrganizationRepository
from .user_credential_repository import UserCredentialRepository

__all__ = [
    "OrganizationRepository",
    "UserCredentialRepository",
    "DeviceAuthorizationRepository",
    "AuthorizationEventRepository",
]
