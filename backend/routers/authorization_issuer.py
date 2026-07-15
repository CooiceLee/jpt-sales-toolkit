"""Leader-only issuer key and signed authorization endpoints."""

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..authorization.common import AuthorizationError
from ..services.authorization_issuer_service import AuthorizationIssuerService
from ..services.leader_authorization_recovery_service import (
    LeaderAuthorizationRecoveryService,
)
from .authorization_dependencies import get_issuer_service, get_recovery_service
from .authorization_http import (
    json_attachment,
    member_filename,
    raise_service_error,
    read_json_upload,
)
from .authorization_models import IssuerInitialize
from .deps import require_role


router = APIRouter()


@router.post("/issuer/initialize")
async def initialize_issuer_key(
    request: IssuerInitialize,
    leader: dict = Depends(require_role("leader")),
    service: AuthorizationIssuerService = Depends(get_issuer_service),
):
    try:
        return service.initialize(request.passphrase, leader["id"])
    except (AuthorizationError, ValueError) as exc:
        raise_service_error(exc)


@router.post("/issuer/renew-local")
async def renew_local_leader_authorization(
    request: IssuerInitialize,
    leader: dict = Depends(require_role("leader")),
    service: LeaderAuthorizationRecoveryService = Depends(get_recovery_service),
):
    try:
        return service.renew(leader["id"], request.passphrase)
    except (AuthorizationError, ValueError) as exc:
        raise_service_error(exc)


@router.post("/issue")
async def issue_authorization(
    member_id: str = Form(...),
    request_file: UploadFile = File(...),
    passphrase: str = Form(..., min_length=1, max_length=1024),
    days: int = Form(90, ge=1, le=365),
    leader: dict = Depends(require_role("leader")),
    service: AuthorizationIssuerService = Depends(get_issuer_service),
):
    device_request = await read_json_upload(request_file, ".jptreq")
    try:
        package = service.issue(member_id, device_request, passphrase, leader["id"], days)
        filename = member_filename(package["payload"]["member"])
        return json_attachment(package, filename)
    except (AuthorizationError, ValueError) as exc:
        raise_service_error(exc)
