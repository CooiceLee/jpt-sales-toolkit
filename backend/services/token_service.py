"""Small HS256 token codec using the per-installation secret."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Optional

from .token_secret_service import get_token_secret


TOKEN_EXPIRY_DAYS = 7


def encode_token(user: dict, extra_claims: Optional[dict] = None) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": user["id"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=TOKEN_EXPIRY_DAYS)).timestamp()),
        "role": user["role"],
        **(extra_claims or {}),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    header_text = _encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_text = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_text}.{payload_text}".encode("ascii")
    signature = hmac.new(get_token_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_text}.{payload_text}.{_encode(signature)}"


def decode_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    header_text, payload_text, signature_text = parts
    signing_input = f"{header_text}.{payload_text}".encode("ascii")
    expected = hmac.new(get_token_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _decode(signature_text)):
        raise ValueError("Invalid token signature")
    header = json.loads(_decode(header_text).decode("utf-8"))
    if header.get("alg") != "HS256":
        raise ValueError("Invalid token algorithm")
    payload = json.loads(_decode(payload_text).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(datetime.utcnow().timestamp()):
        raise ValueError("Token expired")
    return payload


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
