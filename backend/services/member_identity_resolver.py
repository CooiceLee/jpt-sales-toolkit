"""Purpose-aware imported member resolution."""

from __future__ import annotations

from ..repositories.member_identity_schema import normalize_identity
from .member_identity_errors import MemberIdentityError


ROLE_RULES = {
    "owner": frozenset({"leader", "sales"}),
    "collaborator": frozenset({"leader", "sales"}),
    "task_assignee": frozenset({"tech"}),
    "actor": frozenset({"leader", "sales", "tech"}),
    "watcher": frozenset({"leader", "sales", "tech"}),
}


class MemberIdentityResolver:
    def __init__(self, aliases, users, organization_id: str):
        self.aliases = aliases
        self.users = users
        self.organization_id = organization_id

    def resolve(self, source_name: str, source_system: str, purpose: str) -> dict:
        if purpose not in ROLE_RULES:
            raise ValueError(f"Unsupported member identity purpose: {purpose}")
        raw_name = str(source_name or "").strip()
        key = normalize_identity(raw_name)
        if not key:
            raise MemberIdentityError("unknown_member", "Imported member name is empty")
        user, matched_by = self._find_user(raw_name, normalize_identity(source_system), key)
        self._validate(user, purpose)
        return {"user_id": user["id"], "role": user["role"], "matched_by": matched_by}

    def _find_user(self, raw_name: str, source_system: str, key: str) -> tuple[dict, str]:
        direct = self.users.get_by_id(raw_name)
        if direct:
            return direct, "stable_id"
        alias = self.aliases.find_active(self.organization_id, source_system, key)
        if alias:
            return self._known_user(alias["user_id"]), "alias"
        members = self.users.list_all()
        usernames = [item for item in members if normalize_identity(item["username"]) == key]
        if usernames:
            return self._single(usernames), "username"
        displays = [item for item in members if normalize_identity(item["display_name"]) == key]
        if displays:
            return self._single(displays), "display_name"
        raise MemberIdentityError("unknown_member", f"No member mapping exists for {raw_name!r}")

    def _known_user(self, user_id: str) -> dict:
        user = self.users.get_by_id(user_id)
        if not user:
            raise MemberIdentityError("unknown_member", "Mapped member account does not exist")
        return user

    @staticmethod
    def _single(matches: list[dict]) -> dict:
        if len(matches) != 1:
            raise MemberIdentityError("ambiguous_member", "Imported member name matches multiple accounts")
        return matches[0]

    @staticmethod
    def _validate(user: dict, purpose: str) -> None:
        if not user["is_active"]:
            raise MemberIdentityError("inactive_member", "Mapped member account is inactive")
        if user["role"] not in ROLE_RULES[purpose]:
            allowed = ", ".join(sorted(ROLE_RULES[purpose]))
            raise MemberIdentityError(
                "role_mismatch", f"Member role {user['role']} is invalid for {purpose}; expected {allowed}"
            )
