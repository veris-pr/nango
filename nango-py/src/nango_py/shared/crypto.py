"""Crypto helpers for the Python core.

Replicates the authoritative TypeScript algorithms:

- PBKDF2-HMAC-SHA256, 310000 iterations, 32-byte output, base64 — used to hash
  API secret keys and customer keys before lookup. Mirrors
  ``packages/keystore/lib/utils/encryption.ts`` and
  ``packages/shared/lib/utils/encryption.manager.ts`` (salt = encryption key).
- AES-256-GCM with a 12-byte IV and 16-byte auth tag, base64 — used to encrypt
  ``api_secrets.secret``, ``customer_keys.secret``, connection credentials,
  and provider config secrets. Mirrors ``packages/utils/lib/encryption.ts``
  ``Encryption.encryptSync`` / ``decryptSync``.

When ``NANGO_ENCRYPTION_KEY`` is unset, the TypeScript ``shouldEncrypt()``
returns false and hashing/encryption become pass-through; this module mirrors
that so local unencrypted deployments keep working.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PBKDF2_ITERATIONS = 310_000
PBKDF2_KEY_LENGTH = 32
GCM_IV_LENGTH = 12
GCM_TAG_LENGTH = 16


def hash_secret(plaintext: str, encryption_key: str) -> str:
    """PBKDF2 hash of a secret key for DB lookup.

    Returns the plaintext unchanged when no encryption key is configured
    (matches ``CustomerKeyService.hashSecret`` / ``secretService.hashSecret``).
    """
    if not encryption_key:
        return plaintext
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        plaintext.encode("utf-8"),
        encryption_key.encode("utf-8"),
        PBKDF2_ITERATIONS,
        dklen=PBKDF2_KEY_LENGTH,
    )
    return base64.b64encode(digest).decode("ascii")


def encrypt_aes_gcm(plaintext: str, key_b64: str) -> tuple[str, str, str]:
    """Encrypt with AES-256-GCM; returns ``(ciphertext_b64, iv_b64, tag_b64)``."""
    iv = os.urandom(GCM_IV_LENGTH)
    encryptor = Cipher(algorithms.AES(base64.b64decode(key_b64)), modes.GCM(iv)).encryptor()
    encrypted = encryptor.update(plaintext.encode("utf-8")) + encryptor.finalize()
    return (
        base64.b64encode(encrypted).decode("ascii"),
        base64.b64encode(iv).decode("ascii"),
        base64.b64encode(encryptor.tag).decode("ascii"),
    )


def decrypt_aes_gcm(ciphertext_b64: str, iv_b64: str, tag_b64: str, key_b64: str) -> str:
    """Decrypt AES-256-GCM and return the UTF-8 plaintext string."""
    decryptor = Cipher(
        algorithms.AES(base64.b64decode(key_b64)),
        modes.GCM(base64.b64decode(iv_b64), base64.b64decode(tag_b64)),
    ).decryptor()
    decrypted = decryptor.update(base64.b64decode(ciphertext_b64)) + decryptor.finalize()
    return decrypted.decode("utf-8")


def decrypt_api_secret(
    secret: str,
    iv: str | None,
    tag: str | None,
    encryption_key: str,
) -> str:
    """Decrypt an ``api_secrets`` / ``customer_keys`` secret column.

    Mirrors ``EncryptionManager.decryptAPISecret``: pass the secret through
    unchanged when encryption is disabled or the row was never encrypted
    (missing ``iv``/``tag``). Raises :class:`InvalidTag` on a tampered ciphertext.
    """
    if not encryption_key or not iv or not tag:
        return secret
    return decrypt_aes_gcm(secret, iv, tag, encryption_key)


def hmac_sha256_hex(secret: str, payload: str | bytes) -> str:
    """HMAC-SHA256 hex digest for ``X-Nango-Hmac-Sha256`` signatures."""
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def verify_hmac_sha256_hex(secret: str, payload: str | bytes, signature: str) -> bool:
    expected = hmac_sha256_hex(secret, payload)
    return hmac.compare_digest(expected, signature)


def unsafe_legacy_sha256_hex(secret: str, payload: str | bytes) -> str:
    """Deprecated ``X-Nango-Signature``: SHA256 of ``secret + payload``."""
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(secret.encode("utf-8") + payload_bytes).hexdigest()


def nango_webhook_signature_headers(secret: str, payload: str | bytes) -> dict[str, str]:
    return {
        "X-Nango-Signature": unsafe_legacy_sha256_hex(secret, payload),
        "X-Nango-Hmac-Sha256": hmac_sha256_hex(secret, payload),
    }


def stable_json(value: object) -> str:
    """Stable JSON stringification (sorted keys, compact separators).

    Mirrors the TS ``stringify`` used for webhook body signing.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
