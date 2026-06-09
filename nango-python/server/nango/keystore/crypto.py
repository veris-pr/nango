"""Keystore hashing helpers.

The PBKDF2 salt intentionally reuses the shared encryption key so hashes remain
compatible with the existing TypeScript implementation during the migration.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

_KEY_RANDOM_BYTES = 32
_HASH_ITERATIONS = 310_000
_HASH_LENGTH_BYTES = 32


def generate_private_key_value(entity_type: str, *, prefix: str = "nango") -> str:
    random = secrets.token_hex(_KEY_RANDOM_BYTES)
    return f"{prefix}_{entity_type}_{random}"


def hash_private_key_value(key_value: str, encryption_key: str) -> str:
    if not encryption_key:
        return key_value
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        key_value.encode("utf-8"),
        encryption_key.encode("utf-8"),
        _HASH_ITERATIONS,
        dklen=_HASH_LENGTH_BYTES,
    )
    return base64.b64encode(digest).decode("ascii")
