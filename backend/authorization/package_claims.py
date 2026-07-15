"""Organization, member, and team-directory authorization claims."""

from __future__ import annotations

from typing import Any

from .common import AuthorizationError
from .validation_primitives import (
    require_dict,
    require_exact_fields,
    require_non_empty_string,
)


VALID_ROLES = frozenset({"leader", "sales", "tech"})
ORGANIZATION_FIELDS = {"id", "name", "slug"}
MEMBER_FIELDS = {"id", "username", "display_name", "role", "region", "is_active"}


def member_claims(member: Any) -> dict:
    require_dict(member, "Member")
    is_active = member.get("is_active", True)
    if type(is_active) is int and is_active in (0, 1):
        is_active = bool(is_active)
    claims = {
        "id": member.get("id"),
        "username": member.get("username"),
        "display_name": member.get("display_name") or member.get("username"),
        "role": member.get("role"),
        "region": member.get("region"),
        "is_active": is_active,
    }
    validate_member(claims, "Member")
    return claims


def organization_claims(organization: Any) -> dict:
    require_dict(organization, "Organization")
    claims = {field: organization.get(field) for field in ORGANIZATION_FIELDS}
    validate_organization(claims)
    return claims


def validate_organization(organization: Any) -> dict:
    require_dict(organization, "Authorization organization")
    require_exact_fields(organization, ORGANIZATION_FIELDS, "Authorization organization")
    for field in ORGANIZATION_FIELDS:
        require_non_empty_string(organization[field], f"Organization {field}")
    return organization


def validate_member(member: Any, label: str) -> dict:
    require_dict(member, label)
    require_exact_fields(member, MEMBER_FIELDS, label)
    for field in ("id", "username", "display_name"):
        require_non_empty_string(member[field], f"{label} {field}")
    if not isinstance(member["role"], str) or member["role"] not in VALID_ROLES:
        raise AuthorizationError(f"{label} role is not supported")
    if member["region"] is not None and not isinstance(member["region"], str):
        raise AuthorizationError(f"{label} region must be text or null")
    if type(member["is_active"]) is not bool:
        raise AuthorizationError(f"{label} is_active must be a boolean")
    return member


def validate_directory(directory: Any) -> list[dict]:
    if not isinstance(directory, list) or not directory:
        raise AuthorizationError("Authorization team directory must be a non-empty list")
    validated = [validate_member(item, "Team directory member") for item in directory]
    ids = [item["id"] for item in validated]
    usernames = [item["username"].casefold() for item in validated]
    if len(ids) != len(set(ids)):
        raise AuthorizationError("Team directory member IDs must be unique")
    if len(usernames) != len(set(usernames)):
        raise AuthorizationError("Team directory usernames must be unique")
    return validated
