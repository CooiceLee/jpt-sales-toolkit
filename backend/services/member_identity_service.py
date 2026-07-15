"""Resolve imported member names to canonical active account IDs."""

from __future__ import annotations

import sqlite3
from typing import Optional

from ..repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from ..repositories.member_identity_schema import normalize_identity
from ..repositories.member_import_alias_repository import MemberImportAliasRepository
from ..repositories.user_repository import UserRepository
from .member_identity_errors import MemberIdentityError
from .member_identity_resolver import MemberIdentityResolver


class MemberIdentityService:
    def __init__(
        self,
        aliases: Optional[MemberImportAliasRepository] = None,
        users: Optional[UserRepository] = None,
        organization_id: str = DEFAULT_ORGANIZATION_ID,
    ):
        self.aliases = aliases or MemberImportAliasRepository()
        self.users = users or UserRepository()
        self.organization_id = organization_id

    def create_alias(self, data: dict, actor_id: str) -> dict:
        self._require_leader(actor_id)
        source_system, source_name, key = self._alias_values(data)
        self._require_active_user(data.get("user_id"))
        try:
            return self.aliases.create(
                self.organization_id, source_system, source_name, key,
                data["user_id"], actor_id,
            )
        except sqlite3.IntegrityError as exc:
            raise MemberIdentityError("alias_conflict", "Member import alias already exists") from exc

    def get_alias(self, alias_id: str, actor_id: str) -> dict:
        self._require_leader(actor_id)
        alias = self.aliases.get_by_id(alias_id)
        if not alias or alias["organization_id"] != self.organization_id:
            raise MemberIdentityError("alias_not_found", "Member import alias was not found")
        return alias

    def list_aliases(self, actor_id: str, source_system: Optional[str] = None) -> list[dict]:
        self._require_leader(actor_id)
        source = normalize_identity(source_system) if source_system else None
        return self.aliases.list_for_organization(self.organization_id, source, True)

    def update_alias(self, alias_id: str, data: dict, actor_id: str) -> dict:
        current = self.get_alias(alias_id, actor_id)
        changes = dict(data)
        if "is_active" in changes:
            if type(changes["is_active"]) not in (bool, int) or changes["is_active"] not in (0, 1):
                raise MemberIdentityError("invalid_alias", "Alias active state must be boolean")
            changes["is_active"] = int(bool(changes["is_active"]))
        source_data = {**current, **changes}
        if {"source_system", "source_name"}.intersection(changes):
            source, name, key = self._alias_values(source_data)
            changes.update({"source_system": source, "source_name": name, "normalized_alias": key})
        if "user_id" in changes:
            self._require_active_user(changes["user_id"])
        try:
            return self.aliases.update(alias_id, changes, actor_id)
        except sqlite3.IntegrityError as exc:
            raise MemberIdentityError("alias_conflict", "Member import alias already exists") from exc

    def delete_alias(self, alias_id: str, actor_id: str) -> bool:
        self.get_alias(alias_id, actor_id)
        return self.aliases.delete(alias_id)

    def resolve_member(self, source_name: str, source_system: str, purpose: str) -> dict:
        resolver = MemberIdentityResolver(self.aliases, self.users, self.organization_id)
        return resolver.resolve(source_name, source_system, purpose)

    def _require_leader(self, actor_id: str) -> dict:
        actor = self._require_active_user(actor_id)
        if actor["role"] != "leader":
            raise MemberIdentityError("leader_required", "Only an active Leader can manage aliases")
        return actor

    def _require_active_user(self, user_id: Optional[str]) -> dict:
        user = self._require_known_user(user_id)
        if not user["is_active"]:
            raise MemberIdentityError("inactive_member", "Member account is inactive")
        return user

    def _require_known_user(self, user_id: Optional[str]) -> dict:
        user = self.users.get_by_id(str(user_id or ""))
        if not user:
            raise MemberIdentityError("unknown_member", "Member account does not exist")
        return user

    @staticmethod
    def _alias_values(data: dict) -> tuple[str, str, str]:
        source_system = normalize_identity(data.get("source_system"))
        source_name = str(data.get("source_name") or "").strip()
        key = normalize_identity(source_name)
        if not source_system or not key:
            raise MemberIdentityError("invalid_alias", "Source system and member alias are required")
        return source_system, source_name, key
