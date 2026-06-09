from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def hmac_sha256_hex(secret: str, payload: str | bytes) -> str:
    return hmac.new(_to_bytes(secret), _to_bytes(payload), hashlib.sha256).hexdigest()


def verify_hmac_sha256_hex(secret: str, payload: str | bytes, signature: str) -> bool:
    expected = hmac_sha256_hex(secret, payload)
    return hmac.compare_digest(expected, signature)


def unsafe_legacy_sha256_hex(secret: str, payload: str | bytes) -> str:
    return hashlib.sha256(_to_bytes(secret) + _to_bytes(payload)).hexdigest()


def nango_webhook_signature_headers(secret: str, payload: str | bytes) -> dict[str, str]:
    return {
        "X-Nango-Signature": unsafe_legacy_sha256_hex(secret, payload),
        "X-Nango-Hmac-Sha256": hmac_sha256_hex(secret, payload),
    }


def decrypt_aes_gcm_base64(key: str, ciphertext: str, iv: str, auth_tag: str) -> str:
    decryptor = Cipher(
        algorithms.AES(base64.b64decode(key)),
        modes.GCM(base64.b64decode(iv), base64.b64decode(auth_tag)),
    ).decryptor()
    decrypted = decryptor.update(base64.b64decode(ciphertext)) + decryptor.finalize()
    return decrypted.decode("utf-8")


def _to_bytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")
