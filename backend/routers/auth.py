"""
Auth router - authentication endpoints.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..services import AuthService
from .deps import get_auth_service, get_current_user, require_role

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


class SwitchUserRequest(BaseModel):
    target_username: str
    password: str


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Authenticate user and return JWT token."""
    result = auth_service.login(request.username, request.password)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return result


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Logout current user (client should discard token)."""
    return {"status": "success", "message": "Logged out"}


@router.post("/switch-user", response_model=LoginResponse)
async def switch_user(
    request: SwitchUserRequest,
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Switch to a different user account."""
    result = auth_service.login(request.target_username, request.password)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return result


@router.get("/users")
async def list_users(
    role: Optional[str] = None,
    user: dict = Depends(require_role("leader", "sales")),
    auth_service: AuthService = Depends(get_auth_service),
):
    """List active users (for assignment dropdowns)."""
    return auth_service.list_users(role)


@router.get("/me")
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """Get current user info."""
    return user
