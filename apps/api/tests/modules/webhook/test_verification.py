"""Tests for webhook signature verification."""

import hashlib
import hmac

from helprs.core.security import verify_github_webhook_signature


class TestVerifyGithubWebhookSignature:
    def test_valid_signature(self):
        payload = b'{"test": "data"}'
        secret = "test-secret"
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_github_webhook_signature(payload, sig, secret) is True

    def test_invalid_signature(self):
        payload = b'{"test": "data"}'
        assert verify_github_webhook_signature(payload, "sha256=invalid", "test-secret") is False

    def test_none_signature_rejects(self):
        payload = b'{"test": "data"}'
        assert verify_github_webhook_signature(payload, None, "test-secret") is False

    def test_missing_sha256_prefix_rejects(self):
        payload = b'{"test": "data"}'
        assert verify_github_webhook_signature(payload, "md5=abc123", "test-secret") is False

    def test_empty_string_signature_rejects(self):
        payload = b'{"test": "data"}'
        assert verify_github_webhook_signature(payload, "", "test-secret") is False
