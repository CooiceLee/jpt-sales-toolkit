"""Leader-managed member identity and authorization lifecycle operations."""

from __future__ import annotations

import sqlite3
from typing import Optional
from uuid import uuid4

from ..repositories import (
    AuthorizationEventRepository,
    DeviceAuthorizationRepository,
    UserCredentialRepository,
    UserRepository,
)
from .member_authorization_presenter import present_event, present_member
from .member_authorization_validation import (
    ensure_another_leader,
    validate_member_profile,
)
from .business_region_service import normalize_business_region


class MemberAuthorizationService:
    """CRUD for the shared team directory and its local authorization state."""

    def __init__(self):
        self.users = UserRepository()
        self.credentials = UserCredentialRepository()
        self.authorizations = DeviceAuthorizationRepository()
        self.events = AuthorizationEventRepository()

    def list_members(self) -> list[dict]:
        return [present_member(user, self.authorizations) for user in self.users.list_all()]

    def create_member(self, data: dict, actor_id: str) -> dict:
        validate_member_profile(data, require_all=True)
        try:
            user_id = self.users.create(
                username=data["username"].strip(),
                password_hash=f"!unprovisioned:{uuid4()}",
                display_name=data["display_name"].strip(),
                role=data["role"],
                region=normalize_business_region(data.get("region")),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username already exists") from exc
        self._event("member_created", actor_id, user_id, data)
        return present_member(self.users.get_by_id(user_id), self.authorizations)

    def update_member(self, user_id: str, data: dict, actor_id: str) -> dict:
        current = self._require_user(user_id)
        validate_member_profile(data)
        if "username" in data:
            data["username"] = data["username"].strip()
        if "region" in data:
            data["region"] = normalize_business_region(data.get("region"))
        if current["role"] == "leader" and "role" in data and data["role"] != "leader":
            ensure_another_leader(self.users, user_id)
        try:
            updated = self.users.update_profile(user_id, data)
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username already exists") from exc
        if data.get("role") and data["role"] != current["role"]:
            self._deactivate_authorization(user_id, "role_changed")
        self._event("member_updated", actor_id, user_id, data)
        return present_member(updated, self.authorizations)

    def deactivate_member(self, user_id: str, actor_id: str) -> dict:
        current = self._require_user(user_id)
        if user_id == actor_id:
            raise ValueError("You cannot deactivate your own account")
        if current["role"] == "leader":
            ensure_another_leader(self.users, user_id)
        self.users.deactivate(user_id)
        credential = self.credentials.get_by_user_id(user_id, active_only=True)
        if credential:
            self.credentials.deactivate(credential["id"])
        self._deactivate_authorization(user_id, "member_deactivated")
        self._event("member_deactivated", actor_id, user_id)
        return present_member(self.users.get_by_id(user_id), self.authorizations)

    def reactivate_member(self, user_id: str, actor_id: str) -> dict:
        self._require_user(user_id)
        self.users.reactivate(user_id)
        self._event("member_reactivated", actor_id, user_id)
        return present_member(self.users.get_by_id(user_id), self.authorizations)

    def list_events(self, limit: int = 100) -> list[dict]:
        return [present_event(item) for item in self.events.list_recent(limit=limit)]

    def _deactivate_authorization(self, user_id: str, reason: str) -> None:
        active = self.authorizations.get_active_for_user(user_id)
        if active:
            self.authorizations.deactivate(active["id"], reason)

    def _require_user(self, user_id: str) -> dict:
        user = self.users.get_by_id(user_id)
        if not user:
            raise ValueError("Member not found")
        return user

    def _event(self, event_type: str, actor_id: str, user_id: str, data: Optional[dict] = None) -> None:
        self.events.create({
            "event_type": event_type,
            "actor_user_id": actor_id,
            "user_id": user_id,
            "event_data_json": data,
        })
