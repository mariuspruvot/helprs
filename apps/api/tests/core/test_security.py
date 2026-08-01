"""Tests for security utilities: Fernet, HMAC, JWT."""

import hashlib
import hmac

import pytest
from cryptography.fernet import Fernet, InvalidToken
from jwt import PyJWTError

from helprs.core.security import (
    create_access_token,
    decode_access_token,
    fernet_decrypt,
    fernet_encrypt,
    fernet_rotate,
    verify_github_webhook_signature,
)

FERNET_KEY = Fernet.generate_key().decode()
SECRET_KEY = "test-jwt-secret-at-least-32-bytes"


# --- Fernet encrypt/decrypt ---


def test_fernet_encrypt_decrypt_roundtrip():
    plaintext = "my-secret-api-key-12345"
    ciphertext = fernet_encrypt(plaintext, [FERNET_KEY])
    assert ciphertext != plaintext
    assert fernet_decrypt(ciphertext, [FERNET_KEY]) == plaintext


def test_fernet_decrypt_with_wrong_key_fails():
    other_key = Fernet.generate_key().decode()
    ciphertext = fernet_encrypt("secret", [FERNET_KEY])
    with pytest.raises(InvalidToken):
        fernet_decrypt(ciphertext, [other_key])


def test_an_empty_keyset_is_rejected():
    """Silently encrypting with no key is not a failure mode worth having."""
    with pytest.raises(ValueError, match="At least one Fernet key"):
        fernet_encrypt("secret", [])


# --- Key rotation ---


def test_a_value_written_by_a_retired_key_is_still_readable():
    """The whole point of the fallback list: replacing the key must not make
    every stored credential unreadable the moment it is deployed."""
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    written_before_rotation = fernet_encrypt("gho_token", [old_key])

    assert fernet_decrypt(written_before_rotation, [new_key, old_key]) == "gho_token"


def test_new_values_use_the_primary_key_only():
    """A value written after rotation must not need the retired key, or the
    old key could never be dropped."""
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()

    written_after_rotation = fernet_encrypt("gho_token", [new_key, old_key])

    assert fernet_decrypt(written_after_rotation, [new_key]) == "gho_token"


def test_rotate_rewrites_under_the_primary_key():
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    original = fernet_encrypt("gho_token", [old_key])

    rewritten = fernet_rotate(original, [new_key, old_key])

    assert rewritten != original
    # Readable with the new key alone: the old one is now droppable.
    assert fernet_decrypt(rewritten, [new_key]) == "gho_token"


def test_rotate_is_safe_to_run_twice():
    """The script is re-runnable, so rotating an already-primary value must
    be a no-op in effect rather than an error."""
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    keys = [new_key, old_key]
    once = fernet_rotate(fernet_encrypt("gho_token", [old_key]), keys)

    twice = fernet_rotate(once, keys)

    assert fernet_decrypt(twice, [new_key]) == "gho_token"


def test_rotate_fails_loudly_when_no_key_matches():
    """The rotation script relies on this to report which rows it could not
    read instead of writing garbage over them."""
    unknown = Fernet.generate_key().decode()
    orphan = fernet_encrypt("gho_token", [unknown])

    with pytest.raises(InvalidToken):
        fernet_rotate(orphan, [Fernet.generate_key().decode()])


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
    with pytest.raises(PyJWTError):
        decode_access_token(token, SECRET_KEY)


def test_jwt_wrong_secret_rejected():
    token = create_access_token({"sub": "user-1"}, SECRET_KEY)
    with pytest.raises(PyJWTError):
        decode_access_token(token, "a-different-secret-of-adequate-length")
