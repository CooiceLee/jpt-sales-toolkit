"""Encrypted Ed25519 issuer-key lifecycle."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .common import AuthorizationError


def initialize_issuer(path: Path, passphrase: str) -> dict:
    if len(passphrase) < 12:
        raise AuthorizationError("Issuer passphrase must contain at least 12 characters")
    if path.exists():
        raise AuthorizationError("Authorization issuer is already initialized")
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase.encode("utf-8")),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as key_file:
        key_file.write(private_pem)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return public_key_info(private_key.public_key())


def load_issuer_key(path: Path, passphrase: str) -> Ed25519PrivateKey:
    if not path.is_file():
        raise AuthorizationError("Authorization issuer is not initialized")
    try:
        key = serialization.load_pem_private_key(
            path.read_bytes(),
            password=passphrase.encode("utf-8"),
        )
    except (TypeError, ValueError) as exc:
        raise AuthorizationError("Issuer passphrase is incorrect") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise AuthorizationError("Stored issuer key has an unsupported type")
    return key


def public_key_info(public_key: Ed25519PublicKey) -> dict:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    fingerprint = hashlib.sha256(raw).hexdigest()
    return {"public_key": encoded, "fingerprint": fingerprint, "key_id": fingerprint[:16]}


def load_public_key(encoded: str) -> Ed25519PublicKey:
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        return Ed25519PublicKey.from_public_bytes(raw)
    except (TypeError, ValueError) as exc:
        raise AuthorizationError("Authorization public key is invalid") from exc
