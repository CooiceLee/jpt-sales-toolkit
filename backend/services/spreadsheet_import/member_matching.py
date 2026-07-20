"""Purpose-aware matching of imported names to existing team accounts."""

from collections import defaultdict

from ...repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from ...repositories.member_import_alias_repository import MemberImportAliasRepository
from ...repositories.user_repository import UserRepository
from ..member_identity_errors import MemberIdentityError
from ..member_identity_resolver import MemberIdentityResolver, ROLE_RULES
from .member_mapping_keys import manual_member_target, member_mapping_key
from .persistence_common import CLEAR_TOKEN

def resolve_members(conn, canonical: dict, manual: dict[str, str]) -> tuple[list[dict], dict]:
    source_system = (canonical.get("source") or {}).get("kind") or "spreadsheet"
    occurrences = _occurrences(canonical)
    users = UserRepository(conn)
    resolver = MemberIdentityResolver(
        MemberImportAliasRepository(conn), users, DEFAULT_ORGANIZATION_ID
    )
    active = [user for user in users.list_all() if user.get("is_active")]
    public, resolved = [], {}
    for (name, purpose), raw_names in sorted(occurrences.items()):
        target_id = manual_member_target(manual, name, purpose, raw_names)
        candidates = [_public_user(user) for user in active if user["role"] in ROLE_RULES[purpose]]
        try:
            match = (_manual_match(users, target_id, purpose) if target_id else
                     _auto_match(resolver, name, raw_names, source_system, purpose))
            resolved[(name, purpose)] = match["user_id"]
            public.append(_entry(name, purpose, "resolved", match, candidates))
        except MemberIdentityError as exc:
            public.append(_entry(name, purpose, "blocker", None, candidates, exc.code, str(exc)))
    return public, resolved


def token_for(entity: dict, purpose: str) -> str:
    fields = {
        "owner": ("owner_username_token", "owner_name_raw"),
        "collaborator": ("member_username_token", "member_name_raw"),
        "watcher": ("member_username_token", "member_name_raw"),
        "actor": ("actor_username_token", "actor_name_raw"),
        "task_assignee": ("assignee_username_token", "assignee_name_raw"),
    }
    token_field, raw_field = fields[purpose]
    return str(entity.get(token_field) or entity.get(raw_field) or "").strip()


def resolution_name(entity: dict, purpose: str) -> str:
    token = token_for(entity, purpose)
    if token:
        return token
    if purpose in {"owner", "collaborator", "watcher"} and entity.get("external_key"):
        return f"@record:{entity['external_key']}:{purpose}"
    return ""


def _occurrences(canonical: dict) -> dict[tuple[str, str], set[str]]:
    result: dict[tuple[str, str], set[str]] = defaultdict(set)
    raw_by_token = {
        str(item.get("username_token") or ""): set(item.get("raw_names") or [])
        for item in canonical.get("member_name_tokens") or []
    }
    entities = canonical.get("entities") or {}
    groups = (
        ("leads", lambda item: "owner"),
        ("assignments", lambda item: item.get("assignment_type") or "collaborator"),
        ("activities", lambda item: "actor"),
        ("pre_sales_tasks", lambda item: "task_assignee"),
        ("after_sales_tasks", lambda item: "task_assignee"),
    )
    for group, purpose_for in groups:
        for item in entities.get(group) or []:
            if str(item.get("action") or "UPSERT").upper() != "UPSERT":
                continue
            purpose = purpose_for(item)
            if purpose not in ROLE_RULES:
                continue
            name = resolution_name(item, purpose)
            if name == CLEAR_TOKEN and purpose in {"actor", "task_assignee"}:
                continue
            if name:
                result[(name, purpose)].update(raw_by_token.get(name) or {name})
    return result


def _auto_match(resolver, name, raw_names, source_system, purpose):
    matches, errors = {}, []
    for candidate in [name, *sorted(raw_names)]:
        try:
            match = resolver.resolve(candidate, source_system, purpose)
            matches[match["user_id"]] = match
        except MemberIdentityError as exc:
            errors.append(exc)
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        raise MemberIdentityError("ambiguous_member", "Member aliases resolve to different accounts")
    raise errors[0] if errors else MemberIdentityError("unknown_member", "Member mapping is missing")


def _manual_match(users: UserRepository, user_id: str, purpose: str) -> dict:
    user = users.get_by_id(user_id)
    if not user:
        raise MemberIdentityError("unknown_member", "Selected member account does not exist")
    if not user.get("is_active"):
        raise MemberIdentityError("inactive_member", "Selected member account is inactive")
    if user["role"] not in ROLE_RULES[purpose]:
        raise MemberIdentityError(
            "role_mismatch", f"Role {user['role']} cannot be used for {purpose}"
        )
    return {"user_id": user["id"], "role": user["role"], "matched_by": "manual"}


def _entry(name, purpose, status, match, candidates, code=None, message=None) -> dict:
    return {
        "source_name": name, "purpose": purpose,
        "mapping_key": member_mapping_key(name, purpose), "status": status,
        "user_id": match.get("user_id") if match else None,
        "matched_by": match.get("matched_by") if match else None,
        "candidates": candidates, "code": code, "message": message,
    }


def _public_user(user: dict) -> dict:
    return {key: user.get(key) for key in ("id", "username", "display_name", "role")}
