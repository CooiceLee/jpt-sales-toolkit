"""Small shared helpers for authorization repositories."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .base import BaseRepository, DEFAULT_ORGANIZATION_ID, generate_uuid, now_iso


VALID_ROLES = frozenset({"leader", "sales", "tech"})
VALID_AUTHORIZATION_PROVIDERS = frozenset({"offline", "remote"})
VALID_ACTIVATION_STATES = frozenset({"issued", "activated"})


def json_text(value: Any) -> Optional[str]:
    """Validate JSON strings and canonically encode Python values."""
    if value is None:
        return None
    if isinstance(value, str):
        json.loads(value)
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def utc_naive(value: str) -> datetime:
    """Parse an ISO timestamp and normalize it for safe comparisons."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def apply_update(repo: BaseRepository, entity_id: str, data: dict) -> bool:
    """Update one repository row and commit using the existing repository contract."""
    if not data:
        return False
    sql, params = repo._build_update(entity_id, data)
    cursor = repo.conn.execute(sql, params)
    repo.conn.commit()
    return cursor.rowcount > 0


def validate_authorization_window(valid_from: str, expires_at: str) -> None:
    if utc_naive(expires_at) <= utc_naive(valid_from):
        raise ValueError("Authorization expiry must be after its valid-from time")


def build_device_record(conn, data: dict) -> dict:
    """Validate issuance input and build a database-ready authorization row."""
    required = {
        "user_id",
        "device_fingerprint_hash",
        "role",
        "payload_json",
        "signature",
        "signing_key_id",
    }
    missing = sorted(field for field in required if not data.get(field))
    if missing:
        raise ValueError(f"Missing authorization fields: {missing}")
    if data["role"] not in VALID_ROLES:
        raise ValueError(f"Unsupported role: {data['role']}")
    activation_state = data.get("activation_state", "issued")
    if activation_state not in VALID_ACTIVATION_STATES:
        raise ValueError(f"Unsupported activation state: {activation_state}")

    organization_id = data.get("organization_id", DEFAULT_ORGANIZATION_ID)
    row = conn.execute(
        "SELECT authorization_duration_days FROM organizations WHERE id = ?",
        (organization_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Organization {organization_id} not found")
    issued_at = data.get("issued_at") or now_iso()
    valid_from = data.get("valid_from") or issued_at
    expires_at = data.get("expires_at") or (
        utc_naive(valid_from) + timedelta(days=row[0])
    ).isoformat()
    validate_authorization_window(valid_from, expires_at)
    return {
        "id": data.get("id") or generate_uuid(),
        "organization_id": organization_id,
        "user_id": data["user_id"],
        "device_fingerprint_hash": data["device_fingerprint_hash"],
        "role": data["role"],
        "activation_state": activation_state,
        "authorization_version": data.get("authorization_version", 1),
        "payload_json": json_text(data["payload_json"]),
        "signature": data["signature"],
        "signature_algorithm": data.get("signature_algorithm", "ed25519"),
        "signing_key_id": data["signing_key_id"],
        "issued_at": issued_at,
        "valid_from": valid_from,
        "expires_at": expires_at,
        "is_active": 1,
        "created_by": data.get("created_by"),
        "updated_at": now_iso(),
    }
