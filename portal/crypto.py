from cryptography.fernet import Fernet
import base64
import hashlib

import logging

logger = logging.getLogger(__name__)

_fernet = None

def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        from portal.config import settings
        key_str = settings.api_key_encryption_key
        if not key_str or key_str == "change-this-encryption-key-in-production":
            raise RuntimeError("API_KEY_ENCRYPTION_KEY must be set securely and changed from the default value.")
        if len(key_str) < 32:
            raise RuntimeError("API_KEY_ENCRYPTION_KEY must be at least 32 characters long.")
        
        # Derive a 32-byte urlsafe base64 string from the encryption key
        key = hashlib.sha256(settings.api_key_encryption_key.encode()).digest()
        _fernet = Fernet(base64.urlsafe_b64encode(key))
    return _fernet

def encrypt_val(val: str | None) -> str | None:
    if not val:
        return None
    return get_fernet().encrypt(val.encode()).decode()

def decrypt_val(val: str | None) -> str | None:
    if not val:
        return None
    try:
        return get_fernet().decrypt(val.encode()).decode()
    except Exception as e:
        logger.exception("Failed to decrypt API key.")
        raise ValueError("Failed to decrypt API key. This may indicate a corrupted database entry or an incorrect API_KEY_ENCRYPTION_KEY.") from e
