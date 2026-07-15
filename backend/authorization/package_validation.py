"""Stable facade for strict offline authorization package validation."""

from .package_claims import VALID_ROLES, member_claims, organization_claims
from .package_policy import (
    AUTHORIZATION_DURATION_DAYS,
    AUTHORIZATION_VERSION,
    normalize_now,
    validate_duration,
    validate_payload,
    validate_signature,
)


__all__ = [
    "AUTHORIZATION_DURATION_DAYS",
    "AUTHORIZATION_VERSION",
    "VALID_ROLES",
    "member_claims",
    "normalize_now",
    "organization_claims",
    "validate_duration",
    "validate_payload",
    "validate_signature",
]
