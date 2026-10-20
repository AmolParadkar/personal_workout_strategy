"""Protecting connector secrets: encrypting the services' access keys before
they're stored, and signing the OAuth `state` so a returning sign-in can't be
forged or replayed for someone else.

Both use CONNECTOR_ENCRYPTION_KEY (a Fernet key), which only the API has.
Making one: see backend/.env.example.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken

STATE_LIFETIME_SECONDS = 10 * 60


class InvalidStateError(Exception):
    """The OAuth `state` is forged, for someone else, or older than 10 minutes."""


def encrypt(key: str, plain: str) -> str:
    return Fernet(key.encode()).encrypt(plain.encode()).decode()


def decrypt(key: str, encrypted: str) -> str:
    try:
        return Fernet(key.encode()).decrypt(encrypted.encode()).decode()
    except InvalidToken as error:
        # Usually means CONNECTOR_ENCRYPTION_KEY was changed: people must reconnect.
        raise ValueError("Stored key can't be decrypted") from error


def _state_secret(key: str) -> bytes:
    # A separate secret for signing, derived from the encryption key.
    return hashlib.sha256(b"oauth-state:" + key.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_state(key: str, profile_id: str, service: str, now: float | None = None) -> str:
    payload = {
        "p": profile_id,
        "s": service,
        "e": int((now or time.time()) + STATE_LIFETIME_SECONDS),
        "n": secrets.token_urlsafe(8),
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_state_secret(key), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def check_state(
    key: str, state: str, profile_id: str, service: str, now: float | None = None
) -> None:
    """Raise unless `state` was made by us, for this person and service, in the last 10 minutes."""
    try:
        body, signature = state.split(".")
        expected = _b64(hmac.new(_state_secret(key), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise InvalidStateError
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError) as error:
        raise InvalidStateError from error
    if payload.get("p") != profile_id or payload.get("s") != service:
        raise InvalidStateError
    if payload.get("e", 0) < (now or time.time()):
        raise InvalidStateError
