import os
import json
import logging
from typing import Dict
from cryptography.fernet import Fernet, InvalidToken

from core.platform_compat import safe_chmod

logger = logging.getLogger(__name__)

class APIKeyManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.api_keys_file = os.path.join(data_dir, "api_keys.json")
        self.key_file = os.path.join(data_dir, ".key")

    def get_or_create_key(self) -> bytes:
        """Get or create encryption key for API keys"""
        if os.path.exists(self.key_file):
            # Re-tighten on every load so older installs that wrote the
            # key with default umask get repaired the next time the app
            # starts. safe_chmod is a no-op on Windows.
            safe_chmod(self.key_file, 0o600)
            with open(self.key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            safe_chmod(self.key_file, 0o600)
            return key
    
    def encrypt_api_key(self, api_key: str) -> str:
        """Encrypt an API key"""
        if not api_key:
            return ""
        f = Fernet(self.get_or_create_key())
        return f.encrypt(api_key.encode()).decode()
    
    def decrypt_api_key(self, encrypted_key: str) -> str:
        """Decrypt an API key"""
        if not encrypted_key:
            return ""
        f = Fernet(self.get_or_create_key())
        return f.decrypt(encrypted_key.encode()).decode()
    
    def save(self, provider: str, api_key: str):
        """Save encrypted API key to file"""
        keys = self.load()
        keys[provider] = self.encrypt_api_key(api_key)
        with open(self.api_keys_file, 'w', encoding="utf-8") as f:
            json.dump(keys, f)
    
    def load(self) -> Dict[str, str]:
        """Load and decrypt API keys"""
        if not os.path.exists(self.api_keys_file):
            return {}
        with open(self.api_keys_file, 'r', encoding="utf-8") as f:
            encrypted_keys = json.load(f)

        decrypted = {}
        for provider, key in encrypted_keys.items():
            try:
                decrypted[provider] = self.decrypt_api_key(key)
            except (InvalidToken, ValueError) as e:
                logger.warning("Failed to decrypt API key for %s: %s", provider, e)
        return decrypted

