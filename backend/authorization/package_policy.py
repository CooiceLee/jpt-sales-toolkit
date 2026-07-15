"""Signed authorization package schema, time, and device policies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .common import AuthorizationError, parse_utc
from .package_claims import validate_directory, validate_member, validate_organization
from .validation_primitives import (
    decode_base64url,
    require_dict,
    require_exact_fields,
    require_lower_hex,
    require_non_empty_string,
    require_uuid,
)


AUTHORIZATION_DURATION_DAYS = 90
AUTHORIZATION_VERSION = 1
PAYLOAD_FIELDS = {
    "package_id", "authorization_version", "organization", "member",
    "team_directory", "device", "issued_at", "valid_from", "expires_at",
}
DEVICE_FIELDS = {"id", "name", "platform", "request_id"}
SIGNATURE_FIELDS = {"algorithm", "key_id", "public_key", "value"}


def validate_duration(days: Any) -> None:
    if type(days) is not int or days != AUTHORIZATION_DURATION_DAYS:
        raise AuthorizationError(
            f"Authorization period must be exactly {AUTHORIZATION_DURATION_DAYS} days"
        )


def normalize_now(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AuthorizationError("Authorization time must include a timezone")
    return value.astimezone(timezone.utc)


def validate_signature(signature: Any) -> bytes:
    require_dict(signature, "Authorization signature")
    require_exact_fields(signature, SIGNATURE_FIELDS, "Authorization signature")
    if signature["algorithm"] != "ed25519":
        raise AuthorizationError("Authorization signature algorithm is unsupported")
    require_lower_hex(signature["key_id"], 16, "Authorization signing key ID")
    decode_base64url(signature["public_key"], 32, "Authorization public key")
    return decode_base64url(signature["value"], 64, "Authorization signature")


def validate_payload(payload: Any, expected_device_id: str, now: datetime) -> None:
    require_dict(payload, "Authorization payload")
    require_exact_fields(payload, PAYLOAD_FIELDS, "Authorization payload")
    require_uuid(payload["package_id"], "Authorization package ID")
    if type(payload["authorization_version"]) is not int or (
        payload["authorization_version"] != AUTHORIZATION_VERSION
    ):
        raise AuthorizationError("Unsupported authorization payload version")

    validate_organization(payload["organization"])
    member = validate_member(payload["member"], "Authorization member")
    if not member["is_active"]:
        raise AuthorizationError("Authorization member must be active")
    directory = validate_directory(payload["team_directory"])
    matching_member = next((item for item in directory if item["id"] == member["id"]), None)
    if matching_member != member:
        raise AuthorizationError("Authorization member must match the team directory")
    _validate_device(payload["device"], expected_device_id)
    _validate_times(payload, now)


def _validate_times(payload: dict, now: datetime) -> None:
    issued_at = _parse_timestamp(payload["issued_at"], "issued_at")
    valid_from = _parse_timestamp(payload["valid_from"], "valid_from")
    expires_at = _parse_timestamp(payload["expires_at"], "expires_at")
    if not issued_at <= valid_from < expires_at:
        raise AuthorizationError("Authorization timestamps are out of order")
    if expires_at - valid_from != timedelta(days=AUTHORIZATION_DURATION_DAYS):
        raise AuthorizationError(
            f"Authorization period must be exactly {AUTHORIZATION_DURATION_DAYS} days"
        )
    current = normalize_now(now)
    if valid_from > current:
        raise AuthorizationError("Authorization is not active yet")
    if expires_at <= current:
        raise AuthorizationError("Authorization has expired")


def _validate_device(device: Any, expected_device_id: str) -> None:
    require_dict(device, "Authorization device")
    require_exact_fields(device, DEVICE_FIELDS, "Authorization device")
    require_lower_hex(device["id"], 64, "Authorization device fingerprint")
    require_lower_hex(expected_device_id, 64, "Expected device fingerprint")
    if device["id"] != expected_device_id:
        raise AuthorizationError("Authorization belongs to a different device")
    for field in ("name", "platform"):
        require_non_empty_string(device[field], f"Authorization device {field}")
    require_uuid(device["request_id"], "Authorization device request ID")


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AuthorizationError(f"Invalid authorization timestamp: {field}")
    try:
        return parse_utc(value)
    except OverflowError as exc:
        raise AuthorizationError(f"Invalid authorization timestamp: {field}") from exc
