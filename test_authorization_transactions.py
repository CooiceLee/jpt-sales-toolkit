"""Failure-injection regression for authorization unit-of-work boundaries."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from backend.authorization import (
    build_device_request,
    device_fingerprint,
    initialize_issuer,
    issue_authorization,
    load_issuer_key,
    verify_authorization,
)
from backend.authorization.issuer import public_key_info
from backend.config import init_settings
from backend.repositories import (
    AuthorizationEventRepository,
    DeviceAuthorizationRepository,
    OrganizationRepository,
    UserRepository,
    close_db,
    init_db,
)
from backend.repositories.issuer_initialization_transaction import persist_initialized_issuer
from backend.repositories.offline_activation_transaction import activate_verified_package
from backend.services.password_service import hash_password


def prepare_database(data_dir: Path) -> None:
    close_db()
    os.environ["JPT_DATA_DIR"] = str(data_dir)
    settings = init_settings(Path.cwd())
    init_db(settings.db_path)


def signed_package(key_path: Path) -> tuple[dict, dict, dict]:
    key_info = initialize_issuer(key_path, "Transaction-Key-Passphrase!")
    private_key = load_issuer_key(key_path, "Transaction-Key-Passphrase!")
    member = {
        "id": str(uuid4()), "username": "leader.atomic", "display_name": "Atomic Leader",
        "role": "leader", "region": "Global", "is_active": True,
    }
    organization = OrganizationRepository().get_default()
    package = issue_authorization(
        private_key, organization, member, build_device_request("Atomic Device"), [member]
    )
    return package, member, key_info


def assert_empty_authorization_state() -> None:
    assert UserRepository().list_all() == []
    assert OrganizationRepository().get_default()["signing_public_key"] is None
    assert DeviceAuthorizationRepository().count() == 0
    assert AuthorizationEventRepository().count() == 0


def main() -> None:
    original_data_dir = os.environ.get("JPT_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="jpt_auth_transactions_") as temp_dir:
        root = Path(temp_dir)
        with patch("backend.authorization.device._platform_identifier", return_value="atomic-device"):
            device_fingerprint.cache_clear()

            prepare_database(root / "activation")
            package, _, _ = signed_package(root / "activation-key.pem")
            verified = verify_authorization(package, device_fingerprint())
            with patch(
                "backend.repositories.offline_activation_transaction._write_credential",
                side_effect=RuntimeError("injected credential failure"),
            ):
                try:
                    activate_verified_package(
                        DeviceAuthorizationRepository().conn,
                        package,
                        verified,
                        hash_password("Atomic-Password-2026!"),
                    )
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Injected activation failure did not propagate")
            assert_empty_authorization_state()

            prepare_database(root / "bootstrap")
            package, member, _ = signed_package(root / "bootstrap-key.pem")
            private_key = load_issuer_key(root / "bootstrap-key.pem", "Transaction-Key-Passphrase!")
            key_info = public_key_info(private_key.public_key())
            with patch(
                "backend.repositories.issuer_initialization_transaction._insert_event",
                side_effect=RuntimeError("injected audit failure"),
            ):
                try:
                    persist_initialized_issuer(
                        UserRepository().conn,
                        package,
                        key_info,
                        member["id"],
                        bootstrap_member=member,
                        password_hash=hash_password("Atomic-Password-2026!"),
                    )
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Injected issuer failure did not propagate")
            assert_empty_authorization_state()

        close_db()
        device_fingerprint.cache_clear()
    if original_data_dir is None:
        os.environ.pop("JPT_DATA_DIR", None)
    else:
        os.environ["JPT_DATA_DIR"] = original_data_dir
    print("PASS: authorization activation and issuer initialization roll back atomically")


if __name__ == "__main__":
    main()
