"""Offline issuer, device request, and signed package security contracts."""

from __future__ import annotations

import base64
import copy
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.authorization import (
    build_device_request,
    device_fingerprint,
    initialize_issuer,
    issue_authorization,
    load_issuer_key,
    verify_authorization,
)
from backend.authorization.common import AuthorizationError
from backend.authorization.common import canonical_bytes


def expect_error(action, text: str) -> None:
    try:
        action()
    except AuthorizationError as exc:
        assert text.lower() in str(exc).lower(), str(exc)
        return
    raise AssertionError(f"Expected AuthorizationError containing: {text}")


def resign(package: dict, private_key) -> dict:
    signed = copy.deepcopy(package)
    signature = private_key.sign(canonical_bytes(signed["payload"]))
    signed["signature"]["value"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return signed


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_auth_crypto_") as temp_dir:
        key_path = Path(temp_dir) / "issuer.pem"
        key_info = initialize_issuer(key_path, "Issuer-Passphrase-2026")
        assert len(key_info["fingerprint"]) == 64
        assert key_path.is_file()
        expect_error(
            lambda: load_issuer_key(key_path, "incorrect-passphrase"),
            "passphrase",
        )
        private_key = load_issuer_key(key_path, "Issuer-Passphrase-2026")

        with patch("backend.authorization.device._platform_identifier", return_value="device-alpha"):
            device_fingerprint.cache_clear()
            request = build_device_request("Sales Laptop")
        member = {
            "id": "sales-001", "username": "sales01", "display_name": "Sales 01",
            "role": "sales", "region": "EU", "is_active": True,
        }
        organization = {"id": "org-001", "name": "JPT", "slug": "jpt"}
        issued_at = datetime(2026, 7, 14, tzinfo=timezone.utc)
        package = issue_authorization(
            private_key,
            organization,
            member,
            request,
            [member],
            days=90,
            now=issued_at,
        )
        verified = verify_authorization(
            package,
            request["device_id"],
            now=issued_at + timedelta(days=1),
        )
        assert verified["payload"]["member"]["id"] == member["id"]
        assert verified["fingerprint"] == key_info["fingerprint"]
        expect_error(
            lambda: issue_authorization(
                private_key, organization, member, request, [member], days=91, now=issued_at,
            ),
            "exactly 90 days",
        )

        tampered = copy.deepcopy(package)
        tampered["payload"]["member"]["role"] = "leader"
        expect_error(
            lambda: verify_authorization(tampered, request["device_id"], now=issued_at),
            "signature",
        )
        expect_error(
            lambda: verify_authorization(package, "0" * 64, now=issued_at),
            "different device",
        )
        expect_error(
            lambda: verify_authorization(package, request["device_id"], now=issued_at + timedelta(days=91)),
            "expired",
        )
        expect_error(
            lambda: verify_authorization(
                package,
                request["device_id"],
                trusted_public_key="not-the-trusted-key",
                now=issued_at,
            ),
            "trusted organization",
        )

        wrong_duration = copy.deepcopy(package)
        wrong_duration["payload"]["expires_at"] = "2026-10-13T00:00:00Z"
        expect_error(
            lambda: verify_authorization(
                resign(wrong_duration, private_key), request["device_id"], now=issued_at,
            ),
            "exactly 90 days",
        )

        duplicate_id = copy.deepcopy(package)
        duplicate_id["payload"]["team_directory"].append(copy.deepcopy(member))
        expect_error(
            lambda: verify_authorization(
                resign(duplicate_id, private_key), request["device_id"], now=issued_at,
            ),
            "ids must be unique",
        )

        duplicate_username = copy.deepcopy(package)
        other_member = copy.deepcopy(member)
        other_member.update({"id": "tech-002", "username": "SALES01", "role": "tech"})
        duplicate_username["payload"]["team_directory"].append(other_member)
        expect_error(
            lambda: verify_authorization(
                resign(duplicate_username, private_key), request["device_id"], now=issued_at,
            ),
            "usernames must be unique",
        )

        malformed_directory = copy.deepcopy(package)
        del malformed_directory["payload"]["team_directory"][0]["is_active"]
        expect_error(
            lambda: verify_authorization(
                resign(malformed_directory, private_key), request["device_id"], now=issued_at,
            ),
            "fields are invalid",
        )

        non_boolean_directory = copy.deepcopy(package)
        non_boolean_directory["payload"]["team_directory"][0]["is_active"] = 1
        expect_error(
            lambda: verify_authorization(
                resign(non_boolean_directory, private_key), request["device_id"], now=issued_at,
            ),
            "boolean",
        )

        malformed_organization = copy.deepcopy(package)
        del malformed_organization["payload"]["organization"]["slug"]
        expect_error(
            lambda: verify_authorization(
                resign(malformed_organization, private_key), request["device_id"], now=issued_at,
            ),
            "organization fields",
        )

        wrong_payload_version = copy.deepcopy(package)
        wrong_payload_version["payload"]["authorization_version"] = 2
        expect_error(
            lambda: verify_authorization(
                resign(wrong_payload_version, private_key), request["device_id"], now=issued_at,
            ),
            "payload version",
        )

        wrong_package_version = copy.deepcopy(package)
        wrong_package_version["version"] = 2
        expect_error(
            lambda: verify_authorization(wrong_package_version, request["device_id"], now=issued_at),
            "package format",
        )

        bad_order = copy.deepcopy(package)
        bad_order["payload"]["issued_at"] = "2026-07-15T00:00:00Z"
        expect_error(
            lambda: verify_authorization(
                resign(bad_order, private_key), request["device_id"], now=issued_at,
            ),
            "out of order",
        )

        bad_timestamp = copy.deepcopy(package)
        bad_timestamp["payload"]["valid_from"] = "2026-07-14T00:00:00"
        expect_error(
            lambda: verify_authorization(
                resign(bad_timestamp, private_key), request["device_id"], now=issued_at,
            ),
            "timestamp",
        )

        bad_signature_shape = copy.deepcopy(package)
        bad_signature_shape["signature"]["value"] = "abc"
        expect_error(
            lambda: verify_authorization(bad_signature_shape, request["device_id"], now=issued_at),
            "signature",
        )

        bad_public_key_shape = copy.deepcopy(package)
        bad_public_key_shape["signature"]["public_key"] = "abc"
        expect_error(
            lambda: verify_authorization(bad_public_key_shape, request["device_id"], now=issued_at),
            "public key",
        )

        bad_key_id_shape = copy.deepcopy(package)
        bad_key_id_shape["signature"]["key_id"] = "NOT-A-KEY-ID"
        expect_error(
            lambda: verify_authorization(bad_key_id_shape, request["device_id"], now=issued_at),
            "key id",
        )

        extra_package_field = copy.deepcopy(package)
        extra_package_field["unexpected"] = True
        expect_error(
            lambda: verify_authorization(extra_package_field, request["device_id"], now=issued_at),
            "package fields",
        )
        device_fingerprint.cache_clear()

    print("PASS: encrypted Ed25519 issuer and device-bound authorization contracts")


if __name__ == "__main__":
    main()
