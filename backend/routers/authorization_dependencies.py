"""Dependency factories for authorization endpoint modules."""

from ..authorization import resolve_authorization_provider
from ..authorization.provider import AuthorizationProvider
from ..services.authorization_issuer_service import AuthorizationIssuerService
from ..services.first_run_setup_service import FirstRunSetupService
from ..services.leader_authorization_recovery_service import (
    LeaderAuthorizationRecoveryService,
)
from ..services.member_authorization_service import MemberAuthorizationService
from ..services.offline_authorization_service import OfflineAuthorizationService


def get_offline_service() -> OfflineAuthorizationService:
    return OfflineAuthorizationService()


def get_authorization_provider() -> AuthorizationProvider:
    return resolve_authorization_provider()


def get_member_service() -> MemberAuthorizationService:
    return MemberAuthorizationService()


def get_issuer_service() -> AuthorizationIssuerService:
    return AuthorizationIssuerService()


def get_first_run_service() -> FirstRunSetupService:
    return FirstRunSetupService()


def get_recovery_service() -> LeaderAuthorizationRecoveryService:
    return LeaderAuthorizationRecoveryService()
