"""
Step 4: Migrate legacy follow_ups to lead_activities.

Legacy follow_ups[] become lead_activities with:
- action_type = 'follow_up'
- is_formal_follow_up = 1
- visibility = 'all'
"""

from __future__ import annotations

import json

from .base import MigrationContext, generate_uuid, empty_to_none


def migrate_activities(ctx: MigrationContext, inquiries: list[dict]) -> None:
    """Migrate follow_ups from all inquiries to lead_activities."""
    for inquiry in inquiries:
        legacy_id = inquiry.get("inquiry_id", "")
        lead_id = ctx.legacy_id_map.get(legacy_id)

        if not lead_id:
            continue

        follow_ups = inquiry.get("follow_ups", [])
        for fu in follow_ups:
            # Resolve actor
            actor_legacy_id = fu.get("_updated_by") or fu.get("_created_by")
            actor_mapping = ctx.legacy_user_map.get(actor_legacy_id or "", {})
            actor_id = actor_mapping.get("user_id")

            # Build summary from content
            content = empty_to_none(fu.get("content"))
            method = empty_to_none(fu.get("method"))
            summary = content[:200] if content else f"{method or 'Follow-up'} recorded"

            # Build payload
            payload = {
                "method": method,
                "content": content,
                "status": empty_to_none(fu.get("status")),
                "customer_feedback": empty_to_none(fu.get("customer_feedback")),
                "next_action": empty_to_none(fu.get("next_action")),
                "next_action_date": empty_to_none(fu.get("next_action_date")),
                "response_date": empty_to_none(fu.get("response_date")),
            }
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}

            # Use date as created_at
            created_at = fu.get("date") or fu.get("_created_at") or fu.get("_updated_at")
            if created_at and "T" not in created_at:
                created_at = f"{created_at}T00:00:00"

            ctx.conn.execute(
                """
                INSERT INTO lead_activities (
                    id, lead_id, actor_id, action_type, visibility,
                    is_formal_follow_up, summary, payload_json, created_at
                ) VALUES (?, ?, ?, 'follow_up', 'all', 1, ?, ?, ?)
                """,
                (
                    generate_uuid(),
                    lead_id,
                    actor_id,
                    summary,
                    json.dumps(payload) if payload else None,
                    created_at,
                ),
            )
            ctx.stats["activities_created"] += 1

    ctx.conn.commit()
