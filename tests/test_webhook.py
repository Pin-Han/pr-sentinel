import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException

from src.github.webhook import ALLOWED_ACTIONS, PREvent, verify_signature


def _sign(payload: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


class TestVerifySignature:
    def test_valid_signature(self):
        payload = b'{"test": true}'
        secret = "test-secret"
        sig = _sign(payload, secret)
        verify_signature(payload, sig, secret)

    def test_missing_signature(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_signature(b"payload", None, "secret")
        assert exc_info.value.status_code == 401

    def test_invalid_signature(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_signature(b"payload", "sha256=invalid", "secret")
        assert exc_info.value.status_code == 401

    def test_wrong_secret(self):
        payload = b'{"test": true}'
        sig = _sign(payload, "correct-secret")
        with pytest.raises(HTTPException):
            verify_signature(payload, sig, "wrong-secret")


class TestAllowedActions:
    def test_opened_is_allowed(self):
        assert "opened" in ALLOWED_ACTIONS

    def test_synchronize_is_allowed(self):
        assert "synchronize" in ALLOWED_ACTIONS

    def test_reopened_is_allowed(self):
        assert "reopened" in ALLOWED_ACTIONS

    def test_closed_is_not_allowed(self):
        assert "closed" not in ALLOWED_ACTIONS
