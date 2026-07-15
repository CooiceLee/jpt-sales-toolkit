"""Fail-closed attachment boundary for task-scoped Tech accounts."""

from fastapi import HTTPException, status


def filter_attachments_for_user(items: list[dict], user: dict) -> list[dict]:
    """Attachments are closed until they can be bound to a specific task."""
    return [] if user["role"] == "tech" else items


def forbid_tech_attachment_access(user: dict) -> None:
    if user["role"] == "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technical users cannot access lead attachments",
        )


def forbid_tech_attachment_write(user: dict) -> None:
    if user["role"] == "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technical users cannot modify lead attachments",
        )
