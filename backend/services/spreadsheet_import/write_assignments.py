"""Transactional collaborator and watcher writer."""

from ...repositories.base import generate_uuid, now_iso
from .bindings import bind, binding_id
from .member_matching import resolution_name
from .persistence_common import action_for, apply_archive_action, upsert


def write_assignments(conn, canonical, context, actor_id, batch_id, ids, counts):
    dataset_id, source_hash = canonical["dataset_id"], canonical["source_hash"]
    for item in context["entities"]["assignments"]:
        action = action_for(item)
        bound_id = binding_id(conn, dataset_id, "assignments", item["external_key"])
        if action in {"ARCHIVE", "RESTORE"}:
            existed = bound_id and conn.execute(
                "SELECT 1 FROM lead_assignments WHERE id = ?", (bound_id,)
            ).fetchone()
            if not existed:
                raise ValueError(f"Cannot {action.lower()} unknown assignment {item['external_key']}")
            apply_archive_action(conn, "lead_assignments", bound_id, action, actor_id)
            bind(conn, dataset_id, "assignments", item["external_key"], bound_id,
                 batch_id, source_hash)
            ids["assignments"][item["external_key"]] = bound_id
            counts["assignments"]["updated"] += 1
            continue
        assignment_type = item.get("assignment_type") or "collaborator"
        if assignment_type not in {"collaborator", "watcher"}:
            raise ValueError("Spreadsheet assignments must be collaborator or watcher")
        token = resolution_name(item, assignment_type)
        user_id = context["member_ids"][(token, assignment_type)]
        lead_id = ids["leads"][item["lead_key"]]
        row = conn.execute(
            """SELECT id FROM lead_assignments
               WHERE lead_id = ? AND user_id = ? AND assignment_type = ?""",
            (lead_id, user_id, assignment_type),
        ).fetchone()
        assignment_id = bound_id
        assignment_id = assignment_id or (row[0] if row else generate_uuid())
        existed = conn.execute(
            "SELECT 1 FROM lead_assignments WHERE id = ?", (assignment_id,)
        ).fetchone()
        if not apply_archive_action(conn, "lead_assignments", assignment_id, action, actor_id):
            upsert(conn, "lead_assignments", assignment_id, {
                "lead_id": lead_id, "user_id": user_id, "assignment_type": assignment_type,
                "created_at": now_iso(), "created_by": actor_id, "archived_at": None,
            })
        bind(conn, dataset_id, "assignments", item["external_key"], assignment_id,
             batch_id, source_hash)
        ids["assignments"][item["external_key"]] = assignment_id
        counts["assignments"]["updated" if existed else "created"] += 1
