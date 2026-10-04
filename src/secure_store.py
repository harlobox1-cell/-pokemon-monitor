from __future__ import annotations
import base64
import hashlib
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

class SecretBox:
    def __init__(self, data_dir: str):
        root = Path(data_dir)
        root.mkdir(parents=True, exist_ok=True)
        secret_file = root / "app_secret.bin"
        if secret_file.exists():
            raw = secret_file.read_bytes()
        else:
            raw = os.urandom(32)
            secret_file.write_bytes(raw)
            try:
                os.chmod(secret_file, 0o600)
            except OSError:
                pass
        key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        self.fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return ""
