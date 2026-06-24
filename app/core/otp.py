import secrets
import time
from typing import Dict


class OTPStore:
    def __init__(self, expiry_seconds: int = 900):
        self._store: Dict[str, dict] = {}
        self.expiry = expiry_seconds

    def generate(self, key: str) -> str:
        code = str(secrets.randbelow(1_000_000)).zfill(6)
        self._store[key] = {
            "code": code,
            "expires_at": time.time() + self.expiry,
        }
        return code

    def verify(self, key: str, code: str) -> bool:
        entry = self._store.get(key)
        if not entry:
            return False
        if time.time() > entry["expires_at"]:
            del self._store[key]
            return False
        if entry["code"] != code:
            return False
        del self._store[key]
        return True

    def has_pending(self, key: str) -> bool:
        entry = self._store.get(key)
        if not entry:
            return False
        if time.time() > entry["expires_at"]:
            del self._store[key]
            return False
        return True


# 15 min for password reset, 24 h for email verification
password_reset_store = OTPStore(expiry_seconds=900)
email_verify_store = OTPStore(expiry_seconds=86400)
