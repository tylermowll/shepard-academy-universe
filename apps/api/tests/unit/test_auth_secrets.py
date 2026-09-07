"""Unit contracts for T02 secrets, tokens, passwords, and rate limits.

No database, network, or operator secret is involved; synthetic values only.
"""

import pytest

from math_tutor import auth as auth_service
from math_tutor import settings

SYNTHETIC_SECRET = "t02-synthetic-session-secret-0123456789abcdef"
OTHER_SECRET = "t02-other-synthetic-secret-fedcba9876543210"


def test_session_secret_accepts_long_random_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(settings.SESSION_SECRET_ENV_VAR, SYNTHETIC_SECRET)

    assert settings.session_secret() == SYNTHETIC_SECRET


def test_session_secret_rejects_missing_placeholder_and_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(settings.SESSION_SECRET_ENV_VAR, raising=False)
    with pytest.raises(ValueError, match="missing or a placeholder"):
        settings.session_secret()

    for bad in ("GENERATE_AT_SETUP", "changeme", "  ChangeMe  ", "short-secret"):
        monkeypatch.setenv(settings.SESSION_SECRET_ENV_VAR, bad)
        with pytest.raises(ValueError, match="missing or a placeholder"):
            settings.session_secret()


def test_public_origin_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, raising=False)
    assert settings.app_public_origin() == "http://localhost:8080"

    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, "https://tutor.example")
    assert settings.app_public_origin() == "https://tutor.example"


def test_password_hash_is_argon2id_and_verifies() -> None:
    hashed = auth_service.hash_password("correct-horse-battery-99")

    assert hashed.split("$")[1] == "argon2id"
    assert auth_service.verify_password(hashed, "correct-horse-battery-99") is True
    assert auth_service.verify_password(hashed, "wrong-password") is False
    assert auth_service.verify_password("not-a-hash", "wrong-password") is False
    assert hashed != "correct-horse-battery-99"


def test_password_hashes_use_fresh_salts() -> None:
    first = auth_service.hash_password("same-password-0123456789")
    second = auth_service.hash_password("same-password-0123456789")

    assert first != second
    assert auth_service.verify_password(first, "same-password-0123456789") is True
    assert auth_service.verify_password(second, "same-password-0123456789") is True


def test_anon_csrf_round_trip_and_rejection() -> None:
    token = auth_service.sign_anon_csrf("nonce-0123456789", SYNTHETIC_SECRET)

    assert auth_service.verify_anon_csrf(token, SYNTHETIC_SECRET) is True
    assert auth_service.verify_anon_csrf(token, OTHER_SECRET) is False
    assert auth_service.verify_anon_csrf(token + "tampered", SYNTHETIC_SECRET) is False
    assert auth_service.verify_anon_csrf("no-separator-here", SYNTHETIC_SECRET) is False
    assert auth_service.verify_anon_csrf("", SYNTHETIC_SECRET) is False


def test_opaque_token_hash_is_stable_sha256() -> None:
    token = auth_service.new_opaque_token()

    assert auth_service.hash_opaque_token(token) == auth_service.hash_opaque_token(token)
    assert len(auth_service.hash_opaque_token(token)) == 64
    assert auth_service.new_opaque_token() != token


def test_login_rate_limit_counts_and_resets() -> None:
    auth_service.clear_login_rate_limit()
    try:
        for _ in range(auth_service.LOGIN_RATE_LIMIT):
            assert auth_service.register_login_attempt("198.51.100.7") is None
        retry_after = auth_service.register_login_attempt("198.51.100.7")
        assert retry_after is not None and retry_after > 0
        assert auth_service.register_login_attempt("198.51.100.9") is None
    finally:
        auth_service.clear_login_rate_limit()
    assert auth_service.register_login_attempt("198.51.100.7") is None
    auth_service.clear_login_rate_limit()
