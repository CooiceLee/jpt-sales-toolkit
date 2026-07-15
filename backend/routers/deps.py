"""
Router dependencies - authentication and common dependencies.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Header, status

from ..config import AppSettings, get_settings
from ..services import AuthService, AdminService, AttachmentService


def get_app_settings() -> AppSettings:
    """Dependency for application settings."""
    return get_settings()


def get_auth_service() -> AuthService:
    """Dependency for auth service."""
    return AuthService()


def get_admin_service(settings: AppSettings = Depends(get_app_settings)) -> AdminService:
    """Dependency for admin service with proper config."""
    return AdminService(data_dir=settings.data_dir)


def get_attachment_service(settings: AppSettings = Depends(get_app_settings)) -> AttachmentService:
    """Dependency for attachment service with proper config."""
    return AttachmentService(
        upload_dir=settings.upload_dir,
        max_size=settings.max_upload_size,
        allowed_mime_types=settings.allowed_mime_types,
        allowed_categories=settings.allowed_categories,
    )


async def get_current_user(
    authorization: Optional[str] = Header(None),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """
    Dependency to get current authenticated user.

    Expects: Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = authorization[7:]  # Remove "Bearer " prefix
    user = auth_service.verify_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return user


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    auth_service: AuthService = Depends(get_auth_service),
) -> Optional[dict]:
    """Dependency for optional authentication."""
    if not authorization:
        return None

    try:
        return await get_current_user(authorization, auth_service)
    except HTTPException:
        return None


def require_role(*allowed_roles: str):
    """
    Dependency factory to require specific roles.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: dict = Depends(require_role("leader"))):
            ...
    """
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {', '.join(allowed_roles)}",
            )
        return user

    return role_checker


def get_actor_role_for_lead(lead_id: str, user: dict) -> str:
    """
    Determine user's role for a specific lead.

    Returns: 'leader', 'owner', 'collaborator', 'watcher', or 'tech'
    """
    from ..repositories import LeadRepository

    if user["role"] == "leader":
        return "leader"

    lead_repo = LeadRepository()
    lead = lead_repo.get_by_id(lead_id)

    if not lead:
        return "none"

    # Global Tech always remains task-scoped, even if legacy data incorrectly
    # assigns that member as a commercial owner or collaborator.
    if user["role"] == "tech":
        assigned_task = lead_repo.conn.execute(
            """
            SELECT 1
            FROM (
                SELECT lead_id, assignee_id, archived_at FROM pre_sales_tasks
                UNION ALL
                SELECT lead_id, assignee_id, archived_at FROM after_sales_tasks
            ) tasks
            WHERE tasks.lead_id = ?
              AND tasks.assignee_id = ?
              AND tasks.archived_at IS NULL
            LIMIT 1
            """,
            (lead_id, user["id"]),
        ).fetchone()
        return "tech" if assigned_task else "none"

    # Check if owner
    if lead["owner_id"] == user["id"]:
        return "owner"

    # Check assignments
    assignments = lead_repo.get_assignments(lead_id)
    for assignment in assignments:
        if assignment["user_id"] == user["id"]:
            return assignment["assignment_type"]

    return "none"


def can_access_customer(customer_id: str, user: dict) -> bool:
    """Return whether the user has a visible lead or task for a customer."""
    from ..repositories import LeadRepository

    lead_repo = LeadRepository()
    if user["role"] == "leader":
        row = lead_repo.conn.execute(
            "SELECT 1 FROM customers WHERE id = ? AND archived_at IS NULL",
            (customer_id,),
        ).fetchone()
        return row is not None

    if user["role"] == "tech":
        row = lead_repo.conn.execute(
            """
            SELECT 1 FROM leads l
            WHERE l.customer_id = ? AND l.archived_at IS NULL
              AND (
                EXISTS (SELECT 1 FROM pre_sales_tasks t WHERE t.lead_id = l.id AND t.assignee_id = ? AND t.archived_at IS NULL)
                OR EXISTS (SELECT 1 FROM after_sales_tasks t WHERE t.lead_id = l.id AND t.assignee_id = ? AND t.archived_at IS NULL)
              )
            LIMIT 1
            """,
            (customer_id, user["id"], user["id"]),
        ).fetchone()
        return row is not None

    row = lead_repo.conn.execute(
        """
        SELECT 1 FROM leads l
        LEFT JOIN lead_assignments a ON a.lead_id = l.id AND a.archived_at IS NULL
        WHERE l.customer_id = ? AND l.archived_at IS NULL
          AND (l.owner_id = ? OR a.user_id = ?)
        LIMIT 1
        """,
        (customer_id, user["id"], user["id"]),
    ).fetchone()
    return row is not None
