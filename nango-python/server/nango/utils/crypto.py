from __future__ import annotations

import hashlib
import hmac


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


def _to_bytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")
