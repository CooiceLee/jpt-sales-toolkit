"""Unauthenticated setup, recovery and device activation endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from ..authorization.common import AuthorizationError
from ..authorization.provider import AuthorizationProvider
from ..services.first_run_setup_service import FirstRunSetupService
from ..services.leader_authorization_recovery_service import (
    LeaderAuthorizationRecoveryService,
)
from ..services.offline_authorization_service import OfflineAuthorizationService
from .authorization_dependencies import (
    get_authorization_provider,
    get_first_run_service,
    get_offline_service,
    get_recovery_service,
)
from .authorization_http import (
    json_attachment,
    raise_service_error,
    read_json_upload,
    require_loopback,
)
from .authorization_models import FirstRunSetup, LeaderRecovery


router = APIRouter()


@router.get("/status")
async def authorization_status(
    service: AuthorizationProvider = Depends(get_authorization_provider),
):
    return service.status()


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap_first_leader(
    setup: FirstRunSetup,
    request: Request,
    service: FirstRunSetupService = Depends(get_first_run_service),
):
    require_loopback(request)
    try:
        return service.bootstrap(setup.model_dump())
    except (AuthorizationError, ValueError) as exc:
        raise_service_error(exc)


@router.post("/leader/recover")
async def recover_leader_device(
    recovery: LeaderRecovery,
    request: Request,
    service: LeaderAuthorizationRecoveryService = Depends(get_recovery_service),
):
    require_loopback(request)
    try:
        return service.recover(
            recovery.username, recovery.password, recovery.issuer_passphrase
        )
    except (AuthorizationError, ValueError) as exc:
        raise_service_error(exc)


@router.post("/device-request")
async def create_device_request(
    service: OfflineAuthorizationService = Depends(get_offline_service),
):
    request = service.create_device_request()
    return json_attachment(request, f"jpt-device-{request['device_id'][:12]}.jptreq")


@router.post("/activate")
async def activate_authorization(
    authorization_file: UploadFile = File(...),
    password: str = Form(..., min_length=8, max_length=1024),
    issuer_fingerprint: Optional[str] = Form(default=None, max_length=128),
    service: OfflineAuthorizationService = Depends(get_offline_service),
):
    package = await read_json_upload(authorization_file, ".jptauth")
    try:
        return service.activate(package, password, issuer_fingerprint)
    except (AuthorizationError, ValueError) as exc:
        raise_service_error(exc)
