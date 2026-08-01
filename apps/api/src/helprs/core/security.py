"""JWT handling and Fernet encryption utilities."""

import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, MultiFernet


def _cipher(fernet_keys: list[str]) -> MultiFernet:
    """Build the cipher for an ordered keyset.

    ``MultiFernet`` encrypts with the FIRST key and decrypts with whichever
    one matches, which is exactly what rotation needs: put the new key first,
    keep the retired ones behind it until every stored value has been
    re-encrypted, then drop them.
    """
    if not fernet_keys:
        raise ValueError("At least one Fernet key is required")
    return MultiFernet([Fernet(key.encode()) for key in fernet_keys])


def fernet_encrypt(plaintext: str, fernet_keys: list[str]) -> str:
    """Encrypt a string with the primary key of the keyset."""
    return _cipher(fernet_keys).encrypt(plaintext.encode()).decode()


def fernet_decrypt(ciphertext: str, fernet_keys: list[str]) -> str:
    """Decrypt a value written by any key in the keyset.

    Raises ``InvalidToken`` when no key matches -- which is also what a
    tampered ciphertext produces, since Fernet verifies its HMAC before
    decrypting anything.
    """
    return _cipher(fernet_keys).decrypt(ciphertext.encode()).decode()


def fernet_rotate(ciphertext: str, fernet_keys: list[str]) -> str:
    """Re-encrypt an existing value under the primary key.

    Does not need the plaintext: ``MultiFernet.rotate`` decrypts with
    whichever key matches and re-encrypts with the first. This is what lets a
    retired key actually be retired instead of carried forever.
    """
    return _cipher(fernet_keys).rotate(ciphertext.encode()).decode()


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


def verify_github_webhook_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub webhook HMAC SHA-256 signature.

    Args:
        payload: Raw request body bytes.
        signature: The X-Hub-Signature-256 header value (e.g., "sha256=..."),
            or None when the header is absent, which is a rejection.
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
    """Decode and verify a JWT access token. Raises PyJWTError on failure."""
    return jwt.decode(token, secret_key, algorithms=["HS256"])
