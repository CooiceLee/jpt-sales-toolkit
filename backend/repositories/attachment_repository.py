"""
Attachment repository - database operations for attachments table.
"""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, generate_uuid, now_iso


class AttachmentRepository(BaseRepository):
    """Repository for attachments table."""

    table_name = "attachments"

    def create(
        self,
        lead_id: str,
        category: str,
        stored_name: str,
        original_name: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        uploaded_by: str,
        version_no: int = 1,
    ) -> str:
        """Create new attachment record. Returns attachment ID."""
        attachment_id = generate_uuid()

        self.conn.execute(
            """
            INSERT INTO attachments (
                id, lead_id, category, version_no, stored_name, original_name,
                mime_type, size_bytes, sha256, uploaded_by, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attachment_id,
                lead_id,
                category,
                version_no,
                stored_name,
                original_name,
                mime_type,
                size_bytes,
                sha256,
                uploaded_by,
                now_iso(),
            ),
        )
        self.conn.commit()
        return attachment_id

    def list_for_lead(
        self,
        lead_id: str,
        category: Optional[str] = None,
        include_archived: bool = False,
    ) -> list[dict]:
        """List attachments for a lead."""
        sql = """
            SELECT a.*, u.display_name as uploader_name
            FROM attachments a
            LEFT JOIN users u ON a.uploaded_by = u.id
            WHERE a.lead_id = ?
        """
        params: list = [lead_id]

        if not include_archived:
            sql += " AND a.archived_at IS NULL"

        if category:
            sql += " AND a.category = ?"
            params.append(category)

        sql += " ORDER BY a.uploaded_at DESC"

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_latest_version(self, lead_id: str, category: str, original_name: str) -> int:
        """Get latest version number for a file."""
        cursor = self.conn.execute(
            """
            SELECT MAX(version_no) FROM attachments
            WHERE lead_id = ? AND category = ? AND original_name = ?
            """,
            (lead_id, category, original_name),
        )
        result = cursor.fetchone()[0]
        return result if result else 0

    def archive(self, attachment_id: str) -> bool:
        """Archive attachment (soft delete)."""
        cursor = self.conn.execute(
            "UPDATE attachments SET archived_at = ? WHERE id = ? AND archived_at IS NULL",
            (now_iso(), attachment_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def update_metadata(self, attachment_id: str, data: dict) -> Optional[dict]:
        """Update editable attachment metadata."""
        allowed = {"category", "version_no", "original_name"}
        update_data = {key: value for key, value in data.items() if key in allowed}
        if not update_data:
            return self.get_by_id(attachment_id)

        sql, params = self._build_update(attachment_id, update_data)
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_by_id(attachment_id)

    def find_by_sha256(self, sha256: str) -> Optional[dict]:
        """Find attachment by SHA256 hash (for deduplication)."""
        cursor = self.conn.execute(
            "SELECT * FROM attachments WHERE sha256 = ? AND archived_at IS NULL",
            (sha256,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
