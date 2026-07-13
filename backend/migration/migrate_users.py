"""
Step 1: Migrate legacy users to new users table.

Sources:
- config/user.json
- config/team.json
- Fallback values from inquiry data: created_by, assigned_sales, pre_sales_owner, technician

Password rule: initial password = {legacy_user_id}JPT2026, stored as hash.
"""

from __future__ import annotations

from .base import MigrationContext, generate_uuid, now_iso, hash_password


def collect_legacy_user_ids(ctx: MigrationContext, inquiries: list[dict]) -> set[str]:
    """Collect all unique legacy user IDs from config and data."""
    user_ids = set()

    # From user.json
    user_config = ctx.load_legacy_config("user.json")
    if user_config.get("user_id"):
        user_ids.add(user_config["user_id"])

    # From team.json
    team_config = ctx.load_legacy_config("team.json")
    for member in team_config.get("members", []):
        if member.get("id"):
            user_ids.add(member["id"])

    # From inquiry data
    user_fields = ["created_by", "assigned_sales", "pre_sales_owner", "technician"]
    for inq in inquiries:
        fields = inq.get("fields", {})
        for field_name in user_fields:
            field_data = fields.get(field_name, {})
            value = field_data.get("value") if isinstance(field_data, dict) else field_data
            if value and isinstance(value, str):
                user_ids.add(value)

        # Also check follow_ups and after_sales for _updated_by
        for fu in inq.get("follow_ups", []):
            if fu.get("_updated_by"):
                user_ids.add(fu["_updated_by"])
        for af in inq.get("after_sales", []):
            if af.get("_updated_by"):
                user_ids.add(af["_updated_by"])
            if af.get("technician"):
                user_ids.add(af["technician"])

    return user_ids


def get_role_from_team_config(team_config: dict, user_id: str) -> str:
    """Look up role from team.json, default to 'sales'."""
    for member in team_config.get("members", []):
        if member.get("id") == user_id:
            role = member.get("role", "sales")
            if role in ("leader", "sales", "tech"):
                return role
            return "sales"
    return "sales"


def get_region_from_team_config(team_config: dict, user_id: str):
    """Look up region from team.json."""
    for member in team_config.get("members", []):
        if member.get("id") == user_id:
            return member.get("region")
    return None


def migrate_users(ctx: MigrationContext, inquiries: list[dict]) -> None:
    """Create user records and build legacy_user_map."""
    legacy_user_ids = collect_legacy_user_ids(ctx, inquiries)
    team_config = ctx.load_legacy_config("team.json")
    user_config = ctx.load_legacy_config("user.json")

    for legacy_id in legacy_user_ids:
        new_uuid = generate_uuid()
        initial_password = f"{legacy_id}JPT2026"
        password_hash = hash_password(initial_password)

        role = get_role_from_team_config(team_config, legacy_id)
        region = get_region_from_team_config(team_config, legacy_id)

        # Try to get display name
        display_name = legacy_id
        for member in team_config.get("members", []):
            if member.get("id") == legacy_id and member.get("name"):
                display_name = member["name"]
                break
        if legacy_id == user_config.get("user_id") and user_config.get("user_name"):
            display_name = user_config["user_name"]

        ctx.conn.execute(
            """
            INSERT INTO users (id, username, password_hash, display_name, role, region, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (new_uuid, legacy_id, password_hash, display_name, role, region, now_iso()),
        )

        ctx.legacy_user_map[legacy_id] = {
            "user_id": new_uuid,
            "initial_password": initial_password,
        }
        ctx.stats["users_created"] += 1

    ctx.conn.commit()
