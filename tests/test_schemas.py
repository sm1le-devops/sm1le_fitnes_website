import pytest
from pydantic import ValidationError

import schemas


def test_user_create_accepts_valid_data():
    data = schemas.UserCreate(
        username="tester",
        email="tester@example.com",
        password="12345678",
        csrf_token="token",
    )

    assert data.email == "tester@example.com"


@pytest.mark.parametrize(
    "username",
    ["ab", "a" * 21],
)
def test_user_create_rejects_bad_username_length(username):
    with pytest.raises(ValidationError):
        schemas.UserCreate(
            username=username,
            email="tester@example.com",
            password="12345678",
            csrf_token="token",
        )


def test_user_create_rejects_invalid_email():
    with pytest.raises(ValidationError):
        schemas.UserCreate(
            username="tester",
            email="not-email",
            password="12345678",
            csrf_token="token",
        )


def test_reset_password_requires_eight_chars():
    with pytest.raises(ValidationError):
        schemas.ResetPasswordRequest(
            token="abc",
            new_password="1234567",
        )


def test_reset_password_accepts_valid_data():
    data = schemas.ResetPasswordRequest(
        token="abc",
        new_password="12345678",
    )

    assert data.token == "abc"
