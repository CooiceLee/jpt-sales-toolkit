"""Issue and verify signed, device-bound offline authorization packages."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .common import AuthorizationError, canonical_bytes, iso_utc, utc_now
from .device import validate_device_request
from .issuer import load_public_key, public_key_info
from .package_validation import (
    AUTHORIZATION_DURATION_DAYS,
    AUTHORIZATION_VERSION,
    member_claims,
    normalize_now,
    organization_claims,
    validate_duration,
    validate_payload,
    validate_signature,
)


PACKAGE_FORMAT = "jpt-authorization"
PACKAGE_VERSION = AUTHORIZATION_VERSION


def issue_authorization(
    private_key: Ed25519PrivateKey,
    organization: dict,
    member: dict,
    device_request: dict,
    team_directory: list,
    days: int = 90,
    now: Optional[datetime] = None,
) -> dict:
    validate_duration(days)
    if not isinstance(device_request, dict):
        raise AuthorizationError("Device request must be an object")
    request = validate_device_request(device_request)
    issued_at = normalize_now(now or utc_now())
    payload = {
        "package_id": str(uuid.uuid4()),
        "authorization_version": AUTHORIZATION_VERSION,
        "organization": organization_claims(organization),
        "member": member_claims(member),
        "team_directory": _directory_claims(team_directory),
        "device": {
            "id": request["device_id"],
            "name": request["device_name"],
            "platform": request["platform"],
            "request_id": request["request_id"],
        },
        "issued_at": iso_utc(issued_at),
        "valid_from": iso_utc(issued_at),
        "expires_at": iso_utc(issued_at + timedelta(days=AUTHORIZATION_DURATION_DAYS)),
    }
    validate_payload(payload, request["device_id"], issued_at)
    key_info = public_key_info(private_key.public_key())
    signature = private_key.sign(canonical_bytes(payload))
    return {
        "format": PACKAGE_FORMAT,
        "version": PACKAGE_VERSION,
        "payload": payload,
        "signature": {
            "algorithm": "ed25519",
            "key_id": key_info["key_id"],
            "public_key": key_info["public_key"],
            "value": base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
        },
    }


def verify_authorization(
    package: dict,
    expected_device_id: str,
    trusted_public_key: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict:
    if not isinstance(package, dict) or set(package) != {"format", "version", "payload", "signature"}:
        raise AuthorizationError("Authorization package fields are invalid")
    if (
        package.get("format") != PACKAGE_FORMAT
        or type(package.get("version")) is not int
        or package.get("version") != PACKAGE_VERSION
    ):
        raise AuthorizationError("Unsupported authorization package format")
    payload = package.get("payload")
    signature = package.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, dict):
        raise AuthorizationError("Authorization package is incomplete")
    signature_bytes = validate_signature(signature)

    encoded_key = signature.get("public_key")
    if trusted_public_key and encoded_key != trusted_public_key:
        raise AuthorizationError("Authorization issuer does not match the trusted organization")
    public_key = load_public_key(encoded_key)
    try:
        signed_payload = canonical_bytes(payload)
        public_key.verify(signature_bytes, signed_payload)
    except (TypeError, OverflowError) as exc:
        raise AuthorizationError("Authorization payload is invalid") from exc
    except (InvalidSignature, ValueError) as exc:
        raise AuthorizationError("Authorization signature is invalid") from exc

    validate_payload(payload, expected_device_id, now or utc_now())
    key_info = public_key_info(public_key)
    if signature.get("key_id") != key_info["key_id"]:
        raise AuthorizationError("Authorization signing key ID is invalid")
    return {"payload": payload, **key_info, "signature": signature["value"]}


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _directory_claims(team_directory: list) -> list[dict]:
    if not isinstance(team_directory, list):
        raise AuthorizationError("Team directory must be a list")
    return [member_claims(item) for item in team_directory]
