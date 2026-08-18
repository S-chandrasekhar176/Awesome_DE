import base64
import os
from typing import Any, Dict

from cryptography.fernet import Fernet


# Key storage path
_KEY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", ".encryption_key")
_KEY_FILE = os.path.normpath(_KEY_FILE)


def generate_key() -> bytes:
    """Generate a new Fernet key.

    Returns:
        URL-safe base64-encoded 32-byte key.
    """
    return Fernet.generate_key()


def _get_or_create_key() -> bytes:
    """Load existing key from file or create a new one.

    Returns:
        Fernet key bytes.
    """
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            key = f.read()
        if len(key) == 44:  # Valid Fernet key length
            return key
    # Generate and save new key
    key = generate_key()
    key_dir = os.path.dirname(_KEY_FILE)
    os.makedirs(key_dir, exist_ok=True)
    with open(_KEY_FILE, "wb") as f:
        f.write(key)
    # Restrict file permissions to owner only
    os.chmod(_KEY_FILE, 0o600)
    return key


def _get_fernet() -> Fernet:
    """Get a Fernet instance with the stored key."""
    key = _get_or_create_key()
    return Fernet(key)


def encrypt_credentials(data: Dict[str, Any]) -> str:
    """Encrypt a dict of credentials to a string.

    Args:
        data: Dict of credential key-value pairs.

    Returns:
        Encrypted string (base64-encoded ciphertext).
    """
    import json
    f = _get_fernet()
    plaintext = json.dumps(data, separators=(",", ":"))
    encrypted = f.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_credentials(encrypted_str: str) -> Dict[str, Any]:
    """Decrypt credentials string back to a dict.

    Args:
        encrypted_str: The encrypted string from encrypt_credentials.

    Returns:
        Dict of credential key-value pairs.

    Raises:
        ValueError: If decryption fails (wrong key, corrupted data).
    """
    import json
    f = _get_fernet()
    try:
        decrypted = f.decrypt(encrypted_str.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to decrypt credentials: {e}") from e
