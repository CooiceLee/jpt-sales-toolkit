"""
Attachment service - file upload and attachment management.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

from ..config import (
    ALLOWED_ATTACHMENT_MIME_TYPES,
    ATTACHMENT_CATEGORIES,
    MAX_UPLOAD_SIZE,
)
from ..repositories import AttachmentRepository


# Default constraints
DEFAULT_MAX_SIZE = MAX_UPLOAD_SIZE
DEFAULT_ALLOWED_MIME_TYPES = ALLOWED_ATTACHMENT_MIME_TYPES
DEFAULT_ALLOWED_CATEGORIES = ATTACHMENT_CATEGORIES


class AttachmentService:
    """Service for managing lead attachments."""

    def __init__(
        self,
        upload_dir: Optional[Path] = None,
        max_size: int = DEFAULT_MAX_SIZE,
        allowed_mime_types: Tuple[str, ...] = DEFAULT_ALLOWED_MIME_TYPES,
        allowed_categories: Tuple[str, ...] = DEFAULT_ALLOWED_CATEGORIES,
    ):
        self.repo = AttachmentRepository()
        self.upload_dir = upload_dir
        self.max_size = max_size
        self.allowed_mime_types = allowed_mime_types
        self.allowed_categories = allowed_categories

    def list_for_lead(
        self,
        lead_id: str,
        category: Optional[str] = None,
    ) -> list[dict]:
        """List attachments for a lead."""
        return self.repo.list_for_lead(lead_id, category)

    def validate_upload(
        self,
        category: str,
        content: bytes,
        mime_type: str,
    ) -> Optional[str]:
        """
        Validate upload parameters.
        Returns error message if invalid, None if valid.
        """
        if category not in self.allowed_categories:
            return f"Invalid category. Allowed: {', '.join(self.allowed_categories)}"

        if len(content) > self.max_size:
            max_mb = self.max_size // (1024 * 1024)
            return f"File too large. Maximum size: {max_mb}MB"

        if mime_type not in self.allowed_mime_types:
            return f"File type not allowed: {mime_type}"

        return None

    def upload(
        self,
        lead_id: str,
        category: str,
        filename: str,
        content: bytes,
        mime_type: str,
        uploaded_by: str,
    ) -> dict:
        """Upload and save attachment."""
        if not self.upload_dir:
            raise ValueError("Upload directory not configured")

        # Validate
        error = self.validate_upload(category, content, mime_type)
        if error:
            raise ValueError(error)

        # Calculate file hash
        sha256 = hashlib.sha256(content).hexdigest()

        # Check for duplicate by hash
        existing = self.repo.find_by_sha256(sha256)
        if existing and existing["lead_id"] == lead_id:
            return existing

        # Determine version
        version_no = self.repo.get_latest_version(lead_id, category, filename) + 1

        # Generate stored name
        ext = Path(filename).suffix
        stored_name = f"{uuid4()}{ext}"

        # Ensure upload directory exists
        lead_upload_dir = self.upload_dir / lead_id / category
        lead_upload_dir.mkdir(parents=True, exist_ok=True)

        # Save file
        file_path = lead_upload_dir / stored_name
        with open(file_path, "wb") as f:
            f.write(content)

        # Create database record
        attachment_id = self.repo.create(
            lead_id=lead_id,
            category=category,
            stored_name=stored_name,
            original_name=filename,
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=sha256,
            uploaded_by=uploaded_by,
            version_no=version_no,
        )

        return self.repo.get_by_id(attachment_id)

    def get_by_id(self, attachment_id: str) -> Optional[dict]:
        """Get attachment by ID."""
        return self.repo.get_by_id(attachment_id)

    def verify_ownership(self, attachment_id: str, lead_id: str) -> bool:
        """Verify attachment belongs to the specified lead."""
        attachment = self.repo.get_by_id(attachment_id)
        if not attachment:
            return False
        return attachment["lead_id"] == lead_id

    def archive(self, attachment_id: str, lead_id: str, actor_id: str) -> bool:
        """
        Archive an attachment.
        Requires lead_id to verify ownership.
        """
        if not self.verify_ownership(attachment_id, lead_id):
            raise ValueError("Attachment does not belong to this lead")
        return self.repo.archive(attachment_id)

    def update_metadata(
        self,
        attachment_id: str,
        lead_id: str,
        actor_id: str,
        category: Optional[str] = None,
        version_no: Optional[int] = None,
        original_name: Optional[str] = None,
    ) -> dict:
        """Update attachment metadata and move file if category changes."""
        attachment = self.repo.get_by_id(attachment_id)
        if not attachment or attachment["lead_id"] != lead_id:
            raise ValueError("Attachment does not belong to this lead")

        update_data = {}
        if category is not None:
            if category not in self.allowed_categories:
                raise ValueError(f"Invalid category. Allowed: {', '.join(self.allowed_categories)}")
            update_data["category"] = category
        if version_no is not None:
            if version_no < 1:
                raise ValueError("version_no must be >= 1")
            update_data["version_no"] = version_no
        if original_name is not None:
            name = original_name.strip()
            if not name:
                raise ValueError("original_name cannot be empty")
            update_data["original_name"] = name

        old_category = attachment["category"]
        if category and category != old_category and self.upload_dir:
            old_path = self.upload_dir / lead_id / old_category / attachment["stored_name"]
            new_dir = self.upload_dir / lead_id / category
            new_path = new_dir / attachment["stored_name"]
            if old_path.exists():
                new_dir.mkdir(parents=True, exist_ok=True)
                old_path.replace(new_path)

        updated = self.repo.update_metadata(attachment_id, update_data)
        if not updated:
            raise ValueError("Attachment not found")
        return updated

    def get_file_path(self, attachment_id: str) -> Optional[Path]:
        """Get physical file path for download."""
        attachment = self.repo.get_by_id(attachment_id)
        if not attachment or not self.upload_dir:
            return None

        return (
            self.upload_dir
            / attachment["lead_id"]
            / attachment["category"]
            / attachment["stored_name"]
        )
