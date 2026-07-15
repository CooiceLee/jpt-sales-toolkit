"""One-transaction import orchestration and governance records."""

from __future__ import annotations

import hashlib
import json

from ...repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from ...repositories.base import generate_uuid, now_iso
from .persistence_common import atomic
from .write_customers import write_customer_entities
from .write_leads import write_lead_entities
from .write_member_aliases import write_manual_member_aliases
from .write_related import write_related_entities


def commit_canonical(conn, canonical: dict, context: dict, actor_id: str,
                     report: dict, before_complete=None) -> dict:
    batch_id, started = generate_uuid(), now_iso()
    with atomic(conn):
        conn.execute(
            """INSERT INTO import_batches (
                   id, organization_id, dataset_id, source_system, source_filename,
                   source_sha256, directory_hash, status, summary_json,
                   created_at, created_by, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, 'importing', ?, ?, ?, ?)""",
            (
                batch_id, DEFAULT_ORGANIZATION_ID, canonical["dataset_id"],
                (canonical.get("source") or {}).get("kind") or "spreadsheet",
                (canonical.get("source") or {}).get("filename"), canonical["source_hash"],
                _directory_hash(canonical), json.dumps(report["summary"], ensure_ascii=False),
                started, actor_id, started,
            ),
        )
        member_aliases = write_manual_member_aliases(conn, canonical, context, actor_id)
        ids, customer_counts = write_customer_entities(
            conn, canonical, context, actor_id, batch_id
        )
        ids, lead_counts = write_lead_entities(
            conn, canonical, context, actor_id, batch_id, ids
        )
        ids, related_counts = write_related_entities(
            conn, canonical, context, actor_id, batch_id, ids
        )
        _write_quality_issues(
            conn, batch_id, canonical["dataset_id"], context["issues"], actor_id
        )
        counts = {**customer_counts, **lead_counts, **related_counts}
        result = {
            "batch_id": batch_id, "dataset_id": canonical["dataset_id"],
            "source_hash": canonical["source_hash"], "status": "completed",
            "counts": counts, "quality_issue_count": sum(
                item["severity"] != "error" for item in context["issues"]
            ),
            "member_aliases_saved": member_aliases,
        }
        if before_complete:
            before_complete(conn, result)
        completed = now_iso()
        conn.execute(
            """UPDATE import_batches SET status = 'completed', summary_json = ?,
               updated_at = ?, completed_at = ? WHERE id = ?""",
            (json.dumps(result, ensure_ascii=False), completed, completed, batch_id),
        )
    return result


def _write_quality_issues(conn, batch_id: str, dataset_id: str,
                          issues: list[dict], actor_id: str) -> None:
    for item in issues:
        if item.get("severity") == "error":
            continue
        raw_value = _issue_source_payload(item)
        auto_resolved = item.get("code") == "excluded_pollution" and not item.get("entity_type")
        issue_status = "resolved" if auto_resolved else "open"
        resolved_at = now_iso() if auto_resolved else None
        resolution_note = "Source value was intentionally discarded outside the verified data boundary" if auto_resolved else None
        conn.execute(
            """UPDATE data_quality_issues SET status = 'resolved', resolved_at = ?,
               resolved_by = ?, resolution_note = ?
               WHERE status = 'open' AND issue_code = ?
                 AND entity_type IS ? AND external_key IS ?
                 AND batch_id != ?
                 AND batch_id IN (SELECT id FROM import_batches
                                  WHERE dataset_id = ? AND organization_id = ?)""",
            (now_iso(), actor_id, f"Superseded by import batch {batch_id}",
             item.get("code") or "source_issue", item.get("entity_type"),
             item.get("external_key"), batch_id, dataset_id, DEFAULT_ORGANIZATION_ID),
        )
        conn.execute(
            """INSERT INTO data_quality_issues (
                   id, batch_id, severity, issue_code, entity_type, external_key,
                   field_name, raw_value, message, status, resolution_note,
                   created_at, resolved_at, resolved_by
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                generate_uuid(), batch_id,
                item.get("severity") if item.get("severity") in {"warning", "info"} else "warning",
                item.get("code") or "source_issue", item.get("entity_type"),
                item.get("external_key"), item.get("field"), raw_value,
                item.get("message") or "Imported data needs review", issue_status,
                resolution_note, now_iso(), resolved_at, actor_id if auto_resolved else None,
            ),
        )


def _directory_hash(canonical: dict) -> str:
    hashes = [str(item.get("row_hash") or "") for item in canonical.get("source_trace") or []]
    return hashlib.sha256("\n".join(hashes).encode()).hexdigest() if hashes else ""


def _issue_source_payload(item: dict):
    source_ref = item.get("source_ref") or {}
    raw = item.get("raw_value")
    if raw is None and not source_ref:
        return None
    return json.dumps({
        "value": raw, "source_ref": source_ref,
        "source_record_key": item.get("source_record_key") or source_ref.get("record_key"),
    }, ensure_ascii=False, default=str)
