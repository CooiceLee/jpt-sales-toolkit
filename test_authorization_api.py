"""End-to-end first-run, issuance, activation and fail-closed API regression."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.authorization.device import device_fingerprint
from backend.repositories import (
    DeviceAuthorizationRepository,
    OrganizationRepository,
    UserCredentialRepository,
    UserRepository,
    close_db,
)


LEADER_PASSWORD = "Leader-Login-2026!"
ISSUER_PASSPHRASE = "Issuer-Key-Passphrase-2026!"
MEMBER_PASSWORD = "Member-Login-2026!"


def expect(response, code: int, label: str):
    assert response.status_code == code, (
        f"{label}: expected HTTP {code}, got {response.status_code}; {response.text[:500]}"
    )
    return response


def set_device(device: dict, raw_id: str) -> None:
    device["raw"] = raw_id
    device_fingerprint.cache_clear()


def login(client: TestClient, username: str, password: str):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    return response, (
        {"Authorization": f"Bearer {response.json()['token']}"}
        if response.status_code == 200 else {}
    )


def bootstrap_and_issue(client: TestClient, device: dict) -> tuple[dict, str]:
    status = expect(client.get("/api/authorization/status"), 200, "fresh status").json()
    assert status["mode"] == "setup" and not status["activated"]
    missing_region = expect(client.post("/api/authorization/bootstrap", json={
        "username": "leader.missing-region",
        "display_name": "Missing Region Leader",
        "password": LEADER_PASSWORD,
        "issuer_passphrase": ISSUER_PASSPHRASE,
    }), 400, "first Leader requires business region")
    assert missing_region.json()["detail"] == "Business region is required"
    bootstrap = expect(client.post("/api/authorization/bootstrap", json={
        "username": "leader.local",
        "display_name": "Local Leader",
        "region": "Global",
        "password": LEADER_PASSWORD,
        "issuer_passphrase": ISSUER_PASSPHRASE,
    }), 201, "first Leader bootstrap").json()
    assert bootstrap["status"]["mode"] == "offline"
    assert bootstrap["status"]["activated"] is True

    _, leader_headers = login(client, "leader.local", LEADER_PASSWORD)
    assert leader_headers
    leader = next(item for item in client.get(
        "/api/authorization/members", headers=leader_headers
    ).json() if item["username"] == "leader.local")
    assert leader["region"] == "GLOBAL"
    missing_member_region = expect(client.post(
        "/api/authorization/members", headers=leader_headers,
        json={
            "username": "sales.missing-region",
            "display_name": "Sales Missing Region",
            "role": "sales",
        },
    ), 400, "new member requires business region")
    assert missing_member_region.json()["detail"] == "Business region is required"
    expect(client.post("/api/authorization/bootstrap", json={
        "username": "second", "display_name": "Second", "password": LEADER_PASSWORD,
        "issuer_passphrase": ISSUER_PASSPHRASE,
    }), 400, "one-time bootstrap closes")
    expect(client.post(
        "/api/authorization/issuer/initialize", headers=leader_headers,
        json={"passphrase": ISSUER_PASSPHRASE},
    ), 400, "trusted issuer cannot be reinitialized")

    sales = expect(client.post(
        "/api/authorization/members", headers=leader_headers,
        json={
            "username": "sales.one", "display_name": "Sales One",
            "role": "sales", "region": "Europe",
        },
    ), 201, "create Sales member").json()
    assert sales["region"] == "EU"
    updated = expect(client.patch(
        f"/api/authorization/members/{leader['id']}", headers=leader_headers,
        json={"display_name": "Primary Leader"},
    ), 200, "partial Leader profile update").json()
    assert updated["display_name"] == "Primary Leader"

    set_device(device, "member-computer")
    request_response = expect(
        client.post("/api/authorization/device-request"), 200, "member device request"
    )
    request_bytes = request_response.content
    set_device(device, "leader-computer")

    expect(client.post(
        "/api/authorization/issue", headers=leader_headers,
        data={
            "member_id": sales["id"], "passphrase": ISSUER_PASSPHRASE, "days": "91",
        },
        files={"request_file": ("sales.jptreq", request_bytes, "application/json")},
    ), 400, "authorization duration cannot exceed policy")
    issued = expect(client.post(
        "/api/authorization/issue", headers=leader_headers,
        data={
            "member_id": sales["id"], "passphrase": ISSUER_PASSPHRASE, "days": "90",
        },
        files={"request_file": ("sales.jptreq", request_bytes, "application/json")},
    ), 200, "issue Sales authorization")
    assert ".jptauth" in issued.headers["content-disposition"]
    package = issued.json()
    issuer_code = client.get("/api/authorization/status").json()["issuer"]["fingerprint"]
    assert issuer_code == package["signature"]["key_id"]

    before_renewal = DeviceAuthorizationRepository().get_active_for_user(leader["id"])
    renewed = expect(client.post(
        "/api/authorization/issuer/renew-local", headers=leader_headers,
        json={"passphrase": ISSUER_PASSPHRASE},
    ), 200, "renew current Leader authorization").json()
    after_renewal = DeviceAuthorizationRepository().get_active_for_user(leader["id"])
    assert renewed["activated"] and after_renewal["id"] != before_renewal["id"]

    DeviceAuthorizationRepository().deactivate(after_renewal["id"], "simulate_expiry")
    assert client.get("/api/authorization/status").json()["activated"] is False
    expect(client.post("/api/authorization/leader/recover", json={
        "username": "leader.local", "password": "Wrong-Password-2026!",
        "issuer_passphrase": ISSUER_PASSPHRASE,
    }), 400, "Leader recovery rejects wrong login password")
    recovered = expect(client.post("/api/authorization/leader/recover", json={
        "username": "leader.local", "password": LEADER_PASSWORD,
        "issuer_passphrase": ISSUER_PASSPHRASE,
    }), 200, "recover expired Leader authorization").json()
    assert recovered["activated"] and recovered["member"]["role"] == "leader"
    return package, issuer_code


def activate_member(client: TestClient, package: dict, issuer_code: str, device: dict) -> None:
    package_bytes = json.dumps(package).encode("utf-8")
    set_device(device, "wrong-computer")
    expect(client.post(
        "/api/authorization/activate",
        data={"password": MEMBER_PASSWORD, "issuer_fingerprint": issuer_code},
        files={"authorization_file": ("sales.jptauth", package_bytes, "application/json")},
    ), 400, "wrong device is rejected")
    assert UserRepository().list_all() == []

    set_device(device, "member-computer")
    expect(client.post(
        "/api/authorization/activate",
        data={"password": MEMBER_PASSWORD, "issuer_fingerprint": "0" * 16},
        files={"authorization_file": ("sales.jptauth", package_bytes, "application/json")},
    ), 400, "wrong Leader verification code is rejected")
    assert UserRepository().list_all() == []
    assert not OrganizationRepository().get_default()["signing_public_key"]

    tampered = copy.deepcopy(package)
    tampered["payload"]["member"]["role"] = "leader"
    expect(client.post(
        "/api/authorization/activate",
        data={"password": MEMBER_PASSWORD, "issuer_fingerprint": issuer_code},
        files={
            "authorization_file": (
                "sales.jptauth", json.dumps(tampered).encode("utf-8"), "application/json"
            )
        },
    ), 400, "tampered role is rejected")
    assert UserRepository().list_all() == []

    activated = expect(client.post(
        "/api/authorization/activate",
        data={"password": MEMBER_PASSWORD, "issuer_fingerprint": issuer_code},
        files={"authorization_file": ("sales.jptauth", package_bytes, "application/json")},
    ), 200, "activate Sales device").json()
    assert activated["mode"] == "offline" and activated["activated"]
    assert activated["member"]["username"] == "sales.one"
    credential = UserCredentialRepository().get_by_user_id(activated["member"]["id"])
    assert credential["password_scheme"] == "pbkdf2_sha256"

    response, sales_headers = login(client, "sales.one", MEMBER_PASSWORD)
    expect(response, 200, "bound Sales login")
    expect(client.get("/api/authorization/members", headers=sales_headers), 403, "Sales admin denial")
    expect(client.post("/api/auth/login", json={
        "username": "leader.local", "password": LEADER_PASSWORD,
    }), 401, "directory Leader cannot log in on Sales device")

    set_device(device, "copied-computer")
    expect(client.get("/api/auth/me", headers=sales_headers), 401, "copied token/device denial")
    set_device(device, "member-computer")
    expect(client.get("/api/auth/me", headers=sales_headers), 200, "original device remains valid")

    active = DeviceAuthorizationRepository().get_active_for_user(activated["member"]["id"])
    DeviceAuthorizationRepository().deactivate(active["id"], "regression_test")
    fail_closed = client.get("/api/authorization/status").json()
    assert fail_closed["mode"] == "offline" and not fail_closed["activated"]
    expect(client.post("/api/auth/login", json={
        "username": "sales.one", "password": MEMBER_PASSWORD,
    }), 401, "deactivated authorization fails closed")


def main() -> None:
    original_override = os.environ.get("JPT_DEVICE_ID")
    with tempfile.TemporaryDirectory(prefix="jpt_auth_api_") as temp_dir:
        root = Path(temp_dir)
        device = {"raw": "leader-computer"}
        with patch("backend.authorization.device._platform_identifier", side_effect=lambda: device["raw"]):
            with patch.dict(os.environ, {
                "JPT_DATA_DIR": str(root / "leader"),
                "JPT_DEVICE_ID": "production-override-must-be-ignored",
            }):
                close_db()
                device_fingerprint.cache_clear()
                expected = hashlib.sha256(
                    b"jpt-device-v1:leader-computer"
                ).hexdigest()
                assert device_fingerprint() == expected
                with TestClient(create_app()) as client:
                    package, issuer_code = bootstrap_and_issue(client, device)
                close_db()

            with patch.dict(os.environ, {"JPT_DATA_DIR": str(root / "member")}):
                close_db()
                set_device(device, "member-computer")
                with TestClient(create_app()) as client:
                    activate_member(client, package, issuer_code, device)
                close_db()
                device_fingerprint.cache_clear()

    if original_override is None:
        os.environ.pop("JPT_DEVICE_ID", None)
    else:
        os.environ["JPT_DEVICE_ID"] = original_override
    print("PASS: first-run, signed activation, device binding and fail-closed authorization API")


if __name__ == "__main__":
    main()
