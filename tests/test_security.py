from core.security import (
    generate_csrf_token,
    get_password_hash,
    is_username_valid,
    validate_csrf_token,
    verify_password,
)
from core import security

def test_csrf_token_is_valid():
    token = generate_csrf_token()

    assert validate_csrf_token(token) is True


def test_random_csrf_token_is_invalid():
    assert validate_csrf_token("not-a-real-token") is False


def test_empty_csrf_token_is_invalid():
    assert validate_csrf_token("") is False


def test_password_hash_round_trip():
    password = "StrongPassword123!"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_username_validation():
    assert is_username_valid("sm1le_dev") is True
    assert is_username_valid("User123") is True

    assert is_username_valid("bad name") is False
    assert is_username_valid("bad-name") is False
    assert is_username_valid("bad@name") is False

def test_missing_password_hash_uses_dummy_verify(
    monkeypatch,
):
    calls = []

    def fake_dummy_verify(
        *_args,
        **_kwargs,
    ):
        calls.append(True)

    monkeypatch.setattr(
        security.pwd_context,
        "dummy_verify",
        fake_dummy_verify,
    )

    result = security.verify_password_or_dummy(
        "Password123!",
        None,
    )

    assert result is False
    assert calls == [True]