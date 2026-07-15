"""Password hashing with transparent legacy SHA-256 verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


PBKDF2_ITERATIONS = 600_000
PBKDF2_DKLEN = 32
PBKDF2_PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Return a salted PBKDF2 password hash in a self-describing format."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=PBKDF2_DKLEN,
    )
    return "$".join(
        (
            PBKDF2_PREFIX,
            str(PBKDF2_ITERATIONS),
            _encode(salt),
            _encode(digest),
        )
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify modern PBKDF2 hashes and the legacy unsalted SHA-256 format."""
    if encoded_hash.startswith(f"{PBKDF2_PREFIX}$"):
        return _verify_pbkdf2(password, encoded_hash)
    if len(encoded_hash) == 64:
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, encoded_hash)
    return False


def needs_rehash(encoded_hash: str) -> bool:
    """Return whether a valid legacy or weaker hash should be upgraded."""
    parts = encoded_hash.split("$")
    if len(parts) != 4 or parts[0] != PBKDF2_PREFIX:
        return True
    try:
        return int(parts[1]) != PBKDF2_ITERATIONS
    except ValueError:
        return True


def _verify_pbkdf2(password: str, encoded_hash: str) -> bool:
    try:
        _, iterations, salt_text, digest_text = encoded_hash.split("$")
        expected = _decode(digest_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _decode(salt_text),
            int(iterations),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
