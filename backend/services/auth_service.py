"""
Authentication service - login, logout, JWT tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Optional

try:
    import jwt  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    jwt = None

from ..repositories import UserRepository

# JWT configuration (MVP: simple secret, production should use env var)
JWT_SECRET = "jpt-sales-toolkit-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 7


def hash_password(password: str) -> str:
    """Hash password using SHA-256. MVP only."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    return hash_password(password) == password_hash


def _b64url_encode(data: bytes) -> str:
    """Encode bytes using URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Decode URL-safe base64 string with optional missing padding."""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class AuthService:
    """Authentication service."""

    def __init__(self, user_repo: Optional[UserRepository] = None):
        self.user_repo = user_repo or UserRepository()

    def login(self, username: str, password: str) -> Optional[dict]:
        """
        Authenticate user and return JWT token.

        Returns:
            dict with token and user info, or None if auth fails
        """
        user = self.user_repo.get_by_username(username)
        if not user:
            return None

        if not user["is_active"]:
            return None

        if not verify_password(password, user["password_hash"]):
            return None

        # Update last login
        self.user_repo.update_last_login(user["id"])

        # Generate token
        token = self._generate_token(user)

        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user["role"],
                "region": user["region"],
            },
        }

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify JWT token and return user info.

        Returns:
            User dict or None if token invalid
        """
        try:
            payload = self._decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                return None

            user = self.user_repo.get_by_id(user_id)
            if not user or not user["is_active"]:
                return None

            return {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user["role"],
                "region": user["region"],
            }

        except Exception:
            return None

    def switch_user(self, token: str, target_username: str, password: str) -> Optional[dict]:
        """
        Switch to a different user account.
        Requires valid current token and target user credentials.
        """
        # Verify current token is valid
        current_user = self.verify_token(token)
        if not current_user:
            return None

        # Login as target user
        return self.login(target_username, password)

    def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str,
    ) -> bool:
        """Change user password."""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return False

        if not verify_password(old_password, user["password_hash"]):
            return False

        new_hash = hash_password(new_password)
        return self.user_repo.update_password(user_id, new_hash)

    def list_users(self, role: Optional[str] = None) -> list[dict]:
        """List active users (for assignment dropdowns)."""
        users = self.user_repo.list_active(role)
        return [
            {
                "id": u["id"],
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
                "region": u["region"],
            }
            for u in users
        ]

    def _generate_token(self, user: dict) -> str:
        """Generate JWT token for user."""
        now = datetime.utcnow()
        payload = {
            "sub": user["id"],
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=JWT_EXPIRY_DAYS)).timestamp()),
            "role": user["role"],
        }
        return self._encode_token(payload)

    def _encode_token(self, payload: dict) -> str:
        """Encode token with PyJWT when available, otherwise use stdlib fallback."""
        if jwt is not None:
            return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = hmac.new(
            JWT_SECRET.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"

    def _decode_token(self, token: str) -> dict:
        """Decode token with PyJWT when available, otherwise use stdlib fallback."""
        if jwt is not None:
            return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")

        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(
            JWT_SECRET.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        actual = _b64url_decode(signature_b64)

        if not hmac.compare_digest(expected, actual):
            raise ValueError("Invalid token signature")

        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = payload.get("exp")
        if exp is not None and int(exp) < int(datetime.utcnow().timestamp()):
            raise ValueError("Token expired")

        return payload
