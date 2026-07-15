"""Persist Leader-approved import identities inside the import transaction."""

from ...repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from ...repositories.base import generate_uuid, now_iso
from ...repositories.member_identity_schema import normalize_identity


def write_manual_member_aliases(conn, canonical: dict, context: dict, actor_id: str) -> int:
    manual = context["resolutions"]["member_mappings"]
    if not manual:
        return 0
    source_system = normalize_identity(
        (canonical.get("source") or {}).get("kind") or "spreadsheet"
    )
    metadata = _metadata(canonical)
    used_tokens = {token for token, _purpose in context["member_ids"]}
    written = 0
    for token in sorted(used_tokens):
        if token.startswith("@record:"):
            continue
        raw_names = metadata.get(token, set())
        target = manual.get(token) or next(
            (manual[name] for name in raw_names if name in manual), None
        )
        if not target:
            continue
        for source_name in {token, *raw_names}:
            if _upsert_alias(conn, source_system, source_name, target, actor_id):
                written += 1
    return written


def _metadata(canonical: dict) -> dict[str, set[str]]:
    return {
        str(item.get("username_token") or ""): {
            str(name).strip() for name in item.get("raw_names") or [] if str(name).strip()
        }
        for item in canonical.get("member_name_tokens") or []
    }


def _upsert_alias(conn, source_system: str, source_name: str,
                  user_id: str, actor_id: str) -> bool:
    normalized = normalize_identity(source_name)
    if not normalized:
        return False
    now = now_iso()
    conn.execute(
        """INSERT INTO member_import_aliases (
               id, organization_id, source_system, source_name, normalized_alias,
               user_id, is_active, created_at, created_by, updated_at, updated_by
           ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
           ON CONFLICT(organization_id, source_system, normalized_alias) DO UPDATE SET
               source_name = excluded.source_name, user_id = excluded.user_id,
               is_active = 1, updated_at = excluded.updated_at,
               updated_by = excluded.updated_by""",
        (generate_uuid(), DEFAULT_ORGANIZATION_ID, source_system, source_name, normalized,
         user_id, now, actor_id, now, actor_id),
    )
    return True
