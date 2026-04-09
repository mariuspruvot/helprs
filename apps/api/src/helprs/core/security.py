"""JWT handling and Fernet encryption utilities."""

import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from jose import jwt


def fernet_encrypt(plaintext: str, fernet_key: str) -> str:
    """Encrypt a string using Fernet symmetric encryption."""
    f = Fernet(fernet_key.encode())
    return f.encrypt(plaintext.encode()).decode()


def fernet_decrypt(ciphertext: str, fernet_key: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    f = Fernet(fernet_key.encode())
    return f.decrypt(ciphertext.encode()).decode()


def create_app_jwt(app_id: str, private_key: str) -> str:
    """Create a short-lived JWT for authenticating as the GitHub App.

    Args:
        app_id: The GitHub App ID.
        private_key: The app's RSA private key (PEM format).

    Returns:
        A JWT string valid for 10 minutes.
    """
    now = int(time.time())
    payload = {"iss": app_id, "iat": now - 60, "exp": now + (10 * 60)}
    return jwt.encode(payload, private_key, algorithm="RS256")


def verify_github_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC SHA-256 signature.

    Args:
        payload: Raw request body bytes.
        signature: The X-Hub-Signature-256 header value (e.g., "sha256=...").
        secret: The webhook secret configured in GitHub.
    """
    if not signature or not signature.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def create_access_token(
    data: dict,
    secret_key: str,
    expires_delta: timedelta = timedelta(minutes=15),
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(to_encode, secret_key, algorithm="HS256")


def decode_access_token(token: str, secret_key: str) -> dict:
    """Decode and verify a JWT access token. Raises JWTError on failure."""
    return jwt.decode(token, secret_key, algorithms=["HS256"])
