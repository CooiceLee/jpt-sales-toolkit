"""Validation helpers for Leader-managed member lifecycle operations."""

from __future__ import annotations

from .business_region_service import normalize_business_region


VALID_ROLES = frozenset({"leader", "sales", "tech"})


def require_business_region(value: object) -> str:
    """Require and normalize one of the five configured business regions."""
    if not str(value or "").strip():
        raise ValueError("Business region is required")
    return normalize_business_region(value, allow_none=False)


def validate_member_profile(data: dict, require_all: bool = False) -> None:
    required = {"username", "display_name", "role"}
    if require_all and any(not data.get(field) for field in required):
        raise ValueError("Username, display name and role are required")
    if require_all:
        require_business_region(data.get("region"))
    if data.get("role") and data["role"] not in VALID_ROLES:
        raise ValueError(f"Unsupported role: {data['role']}")
    if "region" in data:
        require_business_region(data.get("region"))
    if "display_name" in data and not str(data["display_name"] or "").strip():
        raise ValueError("Display name cannot be empty")
    if "username" in data:
        username = data["username"]
        if not username.strip() or any(character.isspace() for character in username):
            raise ValueError("Username cannot be empty or contain spaces")


def ensure_another_leader(users, excluded_id: str) -> None:
    leaders = [
        user
        for user in users.list_active("leader")
        if user["id"] != excluded_id
    ]
    if not leaders:
        raise ValueError("At least one active Leader must remain")
