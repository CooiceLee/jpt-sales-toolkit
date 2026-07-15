"""Password hashing and transparent legacy-upgrade contracts."""

from __future__ import annotations

import hashlib

from backend.services.password_service import hash_password, needs_rehash, verify_password


def main() -> None:
    password = "JPT-Secure-2026"
    encoded = hash_password(password)

    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password(password, encoded)
    assert not verify_password("wrong-password", encoded)
    assert not needs_rehash(encoded)

    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    assert verify_password(password, legacy)
    assert not verify_password("wrong-password", legacy)
    assert needs_rehash(legacy)

    for invalid in ("", "dummy", "pbkdf2_sha256$bad$data"):
        assert not verify_password(password, invalid)

    try:
        hash_password("short")
    except ValueError:
        pass
    else:
        raise AssertionError("short passwords must be rejected")

    print("PASS: PBKDF2 hashing and legacy SHA-256 verification contracts")


if __name__ == "__main__":
    main()
