"""Tests for security utilities: Fernet, HMAC, JWT."""

import hashlib
import hmac

import pytest
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError

from helprs.core.security import (
    create_access_token,
    decode_access_token,
    fernet_decrypt,
    fernet_encrypt,
    verify_github_webhook_signature,
)

FERNET_KEY = Fernet.generate_key().decode()
SECRET_KEY = "test-jwt-secret"


# --- Fernet encrypt/decrypt ---


def test_fernet_encrypt_decrypt_roundtrip():
    plaintext = "my-secret-api-key-12345"
    ciphertext = fernet_encrypt(plaintext, FERNET_KEY)
    assert ciphertext != plaintext
    assert fernet_decrypt(ciphertext, FERNET_KEY) == plaintext


def test_fernet_decrypt_with_wrong_key_fails():
    other_key = Fernet.generate_key().decode()
    ciphertext = fernet_encrypt("secret", FERNET_KEY)
    with pytest.raises(InvalidToken):
        fernet_decrypt(ciphertext, other_key)


# --- HMAC verify ---


def test_hmac_verify_accepts_valid_signature():
    payload = b'{"action": "opened"}'
    secret = "webhook-secret"
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_github_webhook_signature(payload, sig, secret) is True


def test_hmac_verify_rejects_invalid_signature():
    payload = b'{"action": "opened"}'
    assert verify_github_webhook_signature(payload, "sha256=invalid", "webhook-secret") is False


def test_hmac_verify_rejects_wrong_secret():
    payload = b'{"action": "opened"}'
    secret = "correct-secret"
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_github_webhook_signature(payload, sig, "wrong-secret") is False


# --- JWT ---


def test_jwt_encode_decode_roundtrip():
    data = {"sub": "user-123", "role": "admin"}
    token = create_access_token(data, SECRET_KEY)
    decoded = decode_access_token(token, SECRET_KEY)
    assert decoded["sub"] == "user-123"
    assert decoded["role"] == "admin"
    assert "exp" in decoded


def test_jwt_expired_token_rejected():
    from datetime import timedelta

    token = create_access_token({"sub": "user-1"}, SECRET_KEY, expires_delta=timedelta(seconds=-1))
    with pytest.raises(JWTError):
        decode_access_token(token, SECRET_KEY)


def test_jwt_wrong_secret_rejected():
    token = create_access_token({"sub": "user-1"}, SECRET_KEY)
    with pytest.raises(JWTError):
        decode_access_token(token, "wrong-secret")
