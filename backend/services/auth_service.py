"""
Authentication service - login, logout, JWT tokens.
"""

from __future__ import annotations

from typing import Optional

from ..authorization import AuthorizationProvider, resolve_authorization_provider
from ..repositories import UserCredentialRepository, UserRepository
from .password_service import hash_password, needs_rehash, verify_password
from .token_service import decode_token, encode_token


class AuthService:
    """Authentication service."""

    def __init__(
        self,
        user_repo: Optional[UserRepository] = None,
        credential_repo: Optional[UserCredentialRepository] = None,
        authorization_service: Optional[AuthorizationProvider] = None,
    ):
        self.user_repo = user_repo or UserRepository()
        self.credential_repo = credential_repo or UserCredentialRepository()
        self.authorization_service = authorization_service or resolve_authorization_provider()

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

        if not self.authorization_service.validate_user(user):
            return None

        credential = self.credential_repo.get_by_user_id(user["id"], active_only=True)
        password_hash = credential["password_hash"] if credential else user["password_hash"]
        if not verify_password(password, password_hash):
            return None

        if needs_rehash(password_hash):
            self._store_password(user["id"], hash_password(password), credential)
            credential = self.credential_repo.get_by_user_id(user["id"], active_only=True)

        # Update last login
        self.user_repo.update_last_login(user["id"])

        # Generate token
        token = encode_token(user)

        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user["role"],
                "region": user["region"],
                "must_change_password": bool(credential and credential["must_change_password"]),
            },
        }

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify JWT token and return user info.

        Returns:
            User dict or None if token invalid
        """
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                return None

            user = self.user_repo.get_by_id(user_id)
            if not user or not user["is_active"] or payload.get("role") != user["role"]:
                return None
            if not self.authorization_service.validate_user(user):
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

        credential = self.credential_repo.get_by_user_id(user_id, active_only=True)
        current_hash = credential["password_hash"] if credential else user["password_hash"]
        if not verify_password(old_password, current_hash):
            return False

        try:
            new_hash = hash_password(new_password)
        except ValueError:
            return False
        self._store_password(user_id, new_hash, credential)
        return True

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

    def _store_password(self, user_id: str, password_hash: str, credential: Optional[dict]) -> None:
        self.user_repo.update_password(user_id, password_hash)
        if credential:
            return
        self.credential_repo.create({
            "user_id": user_id,
            "password_hash": password_hash,
            "password_scheme": "pbkdf2_sha256",
            "must_change_password": False,
        })
