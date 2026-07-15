"""Read-model construction for installed offline authorization state."""

from __future__ import annotations

import json

from ..authorization import verify_authorization
from ..authorization.clock import AuthorizationClock
from ..authorization.common import AuthorizationError, parse_utc, utc_now
from ..config import get_settings


def build_installation_status(
    organization: dict,
    current_device: str,
    active: dict,
    member: dict,
    has_users: bool,
) -> dict:
    authorization = authorization_status(active, organization, current_device)
    mode = authorization_mode(organization, has_users)
    issuer_path = get_settings().runtime_config_dir / "authorization_issuer.pem"
    trusted = bool(organization.get("signing_public_key"))
    return {
        "mode": mode,
        "activated": bool(authorization and authorization["status"] == "active"),
        "device_id": current_device,
        "trust_required": not trusted,
        "member": member_view(member),
        "authorization": authorization,
        "issuer": {
            "initialized": bool(issuer_path.is_file() and trusted),
            "trusted": trusted,
            "can_initialize": mode in {"legacy", "setup"} and not trusted,
            "fingerprint": organization.get("signing_key_id"),
        },
    }


def authorization_status(active: dict, organization: dict, current_device: str):
    if not active:
        return None
    state = "active"
    try:
        current_time = AuthorizationClock(get_settings().runtime_config_dir).check(utc_now())
        verify_authorization(
            package_from_record(active, organization),
            current_device,
            trusted_public_key=organization.get("signing_public_key"),
            now=current_time,
        )
    except (AuthorizationError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        state = "expired" if "expired" in str(exc).lower() else "invalid"
    try:
        remaining = (parse_utc(active["expires_at"]) - utc_now()).total_seconds() / 86400
    except (TypeError, ValueError):
        remaining = 0
    return {
        "package_id": active["id"],
        "status": state,
        "issued_at": active["issued_at"],
        "expires_at": active["expires_at"],
        "days_remaining": max(0, int(remaining + 0.999)),
    }


def authorization_mode(organization: dict, has_users: bool) -> str:
    if organization.get("authorization_provider") == "remote":
        return "remote"
    if organization.get("signing_public_key"):
        return "offline"
    return "legacy" if has_users else "setup"


def package_from_record(record: dict, organization: dict) -> dict:
    return {
        "format": "jpt-authorization",
        "version": 1,
        "payload": json.loads(record["payload_json"]),
        "signature": {
            "algorithm": record["signature_algorithm"],
            "key_id": record["signing_key_id"],
            "public_key": organization.get("signing_public_key"),
            "value": record["signature"],
        },
    }


def member_view(member):
    if not member:
        return None
    fields = ("id", "username", "display_name", "role", "region")
    return {key: member.get(key) for key in fields}
