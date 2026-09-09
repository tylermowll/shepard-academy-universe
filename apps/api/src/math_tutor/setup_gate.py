"""Ephemeral local-owner authority, never a public token-issuing service."""

import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock

from math_tutor.auth import hash_opaque_token

SETUP_TOKEN_ENV_VAR = "SHEPARD_SETUP_TOKEN"
SETUP_LIFETIME_SECONDS = 30 * 60


@dataclass
class SetupError(Exception):
    code: str
    safe_message: str
    status_code: int
    retry_after: int | None = None


@dataclass
class SetupGate:
    """Only a token digest and monotonic expiry survive application creation.

    Database first-admin checks, not this process-local flag, serialize claims.
    Consume only after a committed account/session transaction so rollback can
    retry. A process crash after commit still leaves setup closed in the database.
    """

    _token_hash: str | None = field(default=None, repr=False)
    _expires_at: float = field(default=0, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    @classmethod
    def from_environment(cls) -> SetupGate:
        token = os.environ.pop(SETUP_TOKEN_ENV_VAR, None)
        if (
            os.getenv("APP_MODE", "private") == "demo"
            or token is None
            or re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token) is None
        ):
            return cls()
        return cls(hash_opaque_token(token), time.monotonic() + SETUP_LIFETIME_SECONDS)

    def available(self) -> bool:
        with self._lock:
            return self._token_hash is not None and time.monotonic() < self._expires_at

    def configured(self) -> bool:
        with self._lock:
            return self._token_hash is not None

    def accepts(self, token: str) -> bool:
        with self._lock:
            return (
                self._token_hash is not None
                and time.monotonic() < self._expires_at
                and re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token) is not None
                and hmac.compare_digest(self._token_hash, hash_opaque_token(token))
            )

    def consume(self) -> None:
        with self._lock:
            self._token_hash = None

    def renew(self) -> str:
        """Issue only through the local owner channel after checking the database."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._token_hash = hash_opaque_token(token)
            self._expires_at = time.monotonic() + SETUP_LIFETIME_SECONDS
        return token
