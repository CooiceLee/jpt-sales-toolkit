"""Translate task service failures into stable HTTP responses."""

from typing import NoReturn

from fastapi import HTTPException, status

from ..repositories.base import ConflictError


def raise_task_update_error(error: Exception) -> NoReturn:
    if isinstance(error, ConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "conflict",
                "current_version": error.current_version,
                "your_version": error.your_version,
                "current_data": error.current_data,
                "message": "此记录已被他人修改，请刷新后重试",
            },
        ) from error
    if isinstance(error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    raise error
