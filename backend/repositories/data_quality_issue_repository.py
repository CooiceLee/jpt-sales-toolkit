"""Queries and lifecycle updates for imported data-quality prompts."""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, now_iso


class DataQualityIssueRepository(BaseRepository):
    table_name = "data_quality_issues"

    def get_with_binding(self, issue_id: str) -> Optional[dict]:
        row = self.conn.execute(self._select_sql() + " WHERE q.id = ?", (issue_id,)).fetchone()
        return dict(row) if row else None

    def list_with_bindings(
        self,
        status: Optional[str] = "open",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict]:
        sql, params = self._select_sql() + " WHERE 1=1", []
        if status:
            sql += " AND q.status = ?"
            params.append(status)
        if entity_type:
            sql += " AND q.entity_type = ?"
            params.append(entity_type)
        if entity_id:
            sql += " AND b.local_entity_id = ?"
            params.append(entity_id)
        sql += " ORDER BY q.created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def open_counts_for_leads(self, lead_ids: list[str]) -> dict[str, int]:
        if not lead_ids:
            return {}
        marks = ",".join("?" for _ in lead_ids)
        rows = self.conn.execute(
            f"""SELECT b.local_entity_id, COUNT(DISTINCT q.id) AS issue_count
                FROM data_quality_issues q
                JOIN import_batches ib ON ib.id = q.batch_id
                JOIN import_bindings b
                  ON b.organization_id = ib.organization_id
                 AND b.dataset_id = ib.dataset_id
                 AND b.entity_type = q.entity_type
                 AND b.external_key = q.external_key
                WHERE q.status = 'open' AND b.entity_type = 'leads'
                  AND b.local_entity_id IN ({marks})
                GROUP BY b.local_entity_id""",
            lead_ids,
        ).fetchall()
        return {row["local_entity_id"]: row["issue_count"] for row in rows}

    def set_status(self, issue_id: str, status: str, note: str, actor_id: str) -> dict:
        resolved_at = now_iso() if status != "open" else None
        self.conn.execute(
            """UPDATE data_quality_issues
               SET status = ?, resolution_note = ?, resolved_at = ?, resolved_by = ?
               WHERE id = ?""",
            (status, note or None, resolved_at, actor_id if resolved_at else None, issue_id),
        )
        self.conn.commit()
        return self.get_with_binding(issue_id)

    @staticmethod
    def _select_sql() -> str:
        return """SELECT q.*, ib.dataset_id, ib.source_filename,
                         b.local_entity_id
                  FROM data_quality_issues q
                  JOIN import_batches ib ON ib.id = q.batch_id
                  LEFT JOIN import_bindings b
                    ON b.organization_id = ib.organization_id
                   AND b.dataset_id = ib.dataset_id
                   AND b.entity_type = q.entity_type
                   AND b.external_key = q.external_key"""
