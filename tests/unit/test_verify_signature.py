"""Tests for _verify_signature from src/github/webhooks.py."""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.github.webhooks import _verify_signature


def _make_signature(payload: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


class TestVerifySignature:
    @patch("src.github.webhooks.get_settings")
    def test_valid_signature(self, mock_settings):
        secret = "test-secret-123"
        mock_settings.return_value.github_webhook_secret = secret
        payload = b'{"action": "opened"}'
        signature = _make_signature(payload, secret)
        # Should not raise
        _verify_signature(payload, signature)

    @patch("src.github.webhooks.get_settings")
    def test_invalid_signature_raises_401(self, mock_settings):
        secret = "test-secret-123"
        mock_settings.return_value.github_webhook_secret = secret
        payload = b'{"action": "opened"}'
        bad_signature = "sha256=0000000000000000000000000000000000000000000000000000000000000000"
        with pytest.raises(HTTPException) as exc_info:
            _verify_signature(payload, bad_signature)
        assert exc_info.value.status_code == 401

    @patch("src.github.webhooks.get_settings")
    def test_wrong_secret_raises_401(self, mock_settings):
        mock_settings.return_value.github_webhook_secret = "correct-secret"
        payload = b'{"test": true}'
        signature = _make_signature(payload, "wrong-secret")
        with pytest.raises(HTTPException) as exc_info:
            _verify_signature(payload, signature)
        assert exc_info.value.status_code == 401
