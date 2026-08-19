"""Versioned envelope encryption for submitted text at rest.

AES-256-GCM from ``cryptography`` provides authenticated encryption. Payloads
carry a version prefix so the key or algorithm can be rotated without
ambiguity. Key rotation limitations are documented in
``docs/PRIVACY_AND_RETENTION.md``.
"""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

#: Current envelope version. Bump when the algorithm or key derivation changes.
ENVELOPE_VERSION = 1

_NONCE_BYTES = 12
_VERSION_BYTES = 1


class DecryptionError(RuntimeError):
    """Raised when a stored payload cannot be authenticated or decoded."""


def encrypt_text(plaintext: str) -> bytes:
    """Encrypt ``plaintext``, returning ``version || nonce || ciphertext``."""
    key = get_settings().encryption_key_bytes
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return ENVELOPE_VERSION.to_bytes(_VERSION_BYTES, "big") + nonce + ciphertext


def decrypt_text(payload: bytes) -> str:
    """Decrypt a payload produced by :func:`encrypt_text`."""
    if len(payload) < _VERSION_BYTES + _NONCE_BYTES + 16:
        raise DecryptionError("Encrypted payload is truncated")

    version = int.from_bytes(payload[:_VERSION_BYTES], "big")
    if version != ENVELOPE_VERSION:
        raise DecryptionError(f"Unsupported envelope version {version}")

    nonce = payload[_VERSION_BYTES : _VERSION_BYTES + _NONCE_BYTES]
    ciphertext = payload[_VERSION_BYTES + _NONCE_BYTES :]
    key = get_settings().encryption_key_bytes
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
    except (InvalidTag, UnicodeDecodeError) as exc:
        raise DecryptionError("Stored text could not be decrypted") from exc
