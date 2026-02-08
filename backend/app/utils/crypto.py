"""Encrypt/decrypt access tokens at rest."""
import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from app.config import get_settings


def _get_fernet() -> Optional[Fernet]:
    key = get_settings().secret_key.encode()
    # Fernet needs 32 url-safe base64-encoded bytes
    digest = hashlib.sha256(key).digest()
    b64 = base64.urlsafe_b64encode(digest)
    return Fernet(b64)


def encrypt_token(plain: str) -> str:
    f = _get_fernet()
    if not f:
        return plain
    return f.encrypt(plain.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    f = _get_fernet()
    if not f:
        return encrypted
    try:
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return encrypted
