"""Unit contracts for T02 secrets, tokens, passwords, and rate limits.

No database, network, or operator secret is involved; synthetic values only.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.orm import Session

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

    for bad in ("GENERATE_AT_SETUP", "changeme", "  ChangeMe  ", "short-secret", " " * 64):
        monkeypatch.setenv(settings.SESSION_SECRET_ENV_VAR, bad)
        with pytest.raises(ValueError, match="missing or a placeholder"):
            settings.session_secret()


def test_public_origin_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, raising=False)
    assert settings.app_public_origin() == "http://127.0.0.1:8000"

    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, "https://tutor.example")
    assert settings.app_public_origin() == "https://tutor.example"
    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, "https://tutor.example:443")
    assert settings.app_public_origin() == "https://tutor.example"
    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, "http://localhost:80")
    assert settings.app_public_origin() == "http://localhost"


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


@pytest.mark.parametrize(
    ("origin", "minimum"),
    [
        ("http://localhost:8000", 6),
        ("http://127.0.0.1:8000", 6),
        ("http://[::1]:8000", 6),
        ("https://localhost", 12),
        ("https://127.0.0.1:8000", 12),
        ("https://tutor.example", 12),
        ("http://192.168.0.2:8000", 12),
    ],
)
def test_password_policy_uses_only_configured_exact_loopback_origin(
    monkeypatch: pytest.MonkeyPatch, origin: str, minimum: int
) -> None:
    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, origin)
    assert auth_service.minimum_admin_password_length() == minimum
    assert auth_service.local_passwords_allowed() is (minimum == 6)
    assert auth_service.validate_admin_credentials("Owner", "a" * minimum) == "Owner"
    with pytest.raises(ValueError, match="at least"):
        auth_service.validate_admin_credentials("Owner", "a" * (minimum - 1))


def test_password_verifier_rejects_malformed_unicode() -> None:
    hashed = auth_service.hash_password("synthetic-valid-password")
    assert not auth_service.verify_password(hashed, "\ud800")


def test_malformed_login_performs_dummy_check_without_querying_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str] = []

    def verify(_hashed: str, password: str) -> bool:
        checked.append(password)
        return False

    monkeypatch.setattr(auth_service, "verify_password", verify)
    with Session() as unbound:
        assert auth_service.authenticate_admin(unbound, "name\ud800", "password") is None
        assert not unbound.in_transaction()
        assert auth_service.authenticate_admin(unbound, "name", "password\ud800") is None
        assert not unbound.in_transaction()
    assert checked == ["invalid-credentials", "invalid-credentials"]


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


@pytest.mark.parametrize(
    "origin",
    [
        "http://tutor.example",
        "http://192.0.2.1",
        "https://tutor.example/path",
        "https://user:password@tutor.example",
        "https://tutor.example?query=1",
        "https://tutor.example#fragment",
        "null",
        "ftp://localhost",
        "https://tutor.example:bad",
    ],
)
def test_public_origin_rejects_unsafe_configuration(
    origin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(settings.APP_PUBLIC_ORIGIN_ENV_VAR, origin)
    with pytest.raises(ValueError, match="APP_PUBLIC_ORIGIN"):
        settings.app_public_origin()


def test_csrf_rejects_expired_future_and_non_ascii_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "time", lambda: 10000.0)
    token = auth_service.sign_anon_csrf("nonce", SYNTHETIC_SECRET)
    assert auth_service.verify_anon_csrf(token, SYNTHETIC_SECRET)
    monkeypatch.setattr(time, "time", lambda: 9999.0)
    assert not auth_service.verify_anon_csrf(token, SYNTHETIC_SECRET)
    monkeypatch.setattr(time, "time", lambda: 13600.0)
    assert not auth_service.verify_anon_csrf(token, SYNTHETIC_SECRET)
    assert not auth_service.verify_anon_csrf("é.signature", SYNTHETIC_SECRET)


def test_login_limiter_bounds_concurrent_admission_and_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_service.clear_login_rate_limit()
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(auth_service, "MAX_LOGIN_RATE_KEYS", 2)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(auth_service.register_login_attempt, ["caller"] * 100))
    assert results.count(None) == auth_service.LOGIN_RATE_LIMIT
    assert auth_service.register_login_attempt("second") is None
    assert auth_service.register_login_attempt("third") == 60.0
    monkeypatch.setattr(time, "monotonic", lambda: 160.0)
    assert auth_service.register_login_attempt("third") is None
    auth_service.clear_login_rate_limit()
