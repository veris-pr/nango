import base64
import os
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionError(Exception):
    pass


def derive_key(encryption_key: str, salt: bytes = b'nango-salt') -> bytes:
    """Derive a 256-bit key from the encryption key using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(encryption_key.encode())


def encrypt(plaintext: str, encryption_key: str) -> Tuple[str, str, str]:
    """
    Encrypt a plaintext string using AES-256-GCM.
    Returns: (ciphertext_base64, iv_base64, tag_base64)
    """
    if not plaintext:
        return '', '', ''

    key = derive_key(encryption_key)
    aesgcm = AESGCM(key)

    iv = os.urandom(12)

    ciphertext_with_tag = aesgcm.encrypt(iv, plaintext.encode(), None)

    ciphertext = ciphertext_with_tag[:-16]
    tag = ciphertext_with_tag[-16:]

    return (
        base64.b64encode(ciphertext).decode(),
        base64.b64encode(iv).decode(),
        base64.b64encode(tag).decode()
    )


def decrypt(ciphertext_b64: str, iv_b64: str, tag_b64: str, encryption_key: str) -> str:
    """
    Decrypt ciphertext using AES-256-GCM.
    Requires: ciphertext_base64, iv_base64, tag_base64, and encryption_key
    """
    if not ciphertext_b64 or not iv_b64 or not tag_b64:
        return ''

    try:
        key = derive_key(encryption_key)
        aesgcm = AESGCM(key)

        ciphertext = base64.b64decode(ciphertext_b64)
        iv = base64.b64decode(iv_b64)
        tag = base64.b64decode(tag_b64)

        ciphertext_with_tag = ciphertext + tag

        plaintext = aesgcm.decrypt(iv, ciphertext_with_tag, None)
        return plaintext.decode()
    except Exception as e:
        raise EncryptionError(f"Decryption failed: {e}")


def encrypt_value(value: Optional[str], encryption_key: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Helper to encrypt a value and return (ciphertext, iv, tag)."""
    if not value:
        return None, None, None
    return encrypt(value, encryption_key)


def decrypt_value(ciphertext: Optional[str], iv: Optional[str], tag: Optional[str], encryption_key: str) -> Optional[str]:
    """Helper to decrypt a value from (ciphertext, iv, tag)."""
    if not ciphertext:
        return None
    return decrypt(ciphertext, iv, tag, encryption_key)