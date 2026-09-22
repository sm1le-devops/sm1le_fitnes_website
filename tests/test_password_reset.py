import re

from core.security import verify_password
from models import User
from services.session_service import (
    build_session_key,
    build_user_session_key,
)


GENERIC_MESSAGE = (
    "If an account with this email exists, "
    "a recovery link has been sent to it"
)


def extract_token(message):
    body = str(message.body)

    match = re.search(
        r"token=([^\s]+)",
        body,
    )

    assert match
    return match.group(1)


def test_forgot_password_does_not_enumerate_accounts(
    client,
    sent_emails,
):
    response = client.post(
        "/auth/forgot-password",
        json={
            "email": "missing@example.com"
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["message"]
        == GENERIC_MESSAGE
    )
    assert sent_emails == []


def test_forgot_password_sends_reset_email(
    client,
    sent_emails,
    make_user,
):
    make_user(
        email="reset@example.com",
    )

    response = client.post(
        "/auth/forgot-password",
        json={
            "email": "RESET@example.com"
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["message"]
        == GENERIC_MESSAGE
    )
    assert len(sent_emails) == 1

    token = extract_token(sent_emails[0])

    assert token


def test_forgot_password_cooldown_prevents_second_email(
    client,
    sent_emails,
    make_user,
):
    make_user(
        email="reset@example.com",
    )

    first = client.post(
        "/auth/forgot-password",
        json={
            "email": "reset@example.com"
        },
    )
    second = client.post(
        "/auth/forgot-password",
        json={
            "email": "reset@example.com"
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(sent_emails) == 1


def test_reset_password_get_rejects_missing_token(
    client,
):
    response = client.get(
        "/auth/reset-password"
    )

    assert response.status_code == 200
    assert "Token is missing" in response.text


def test_reset_password_get_rejects_unknown_token(
    client,
):
    response = client.get(
        "/auth/reset-password",
        params={
            "token": "does-not-exist"
        },
    )

    assert response.status_code == 200
    assert (
        "Token is invalid or expired"
        in response.text
    )


def test_reset_password_is_one_time_and_kills_session(
    client,
    db,
    fake_redis,
    sent_emails,
    make_user,
    login_as,
):
    user = make_user(
        email="reset@example.com",
        password="OldPassword123!",
    )

    session_id = login_as(user)

    forgot = client.post(
        "/auth/forgot-password",
        json={
            "email": "reset@example.com"
        },
    )

    assert forgot.status_code == 200
    token = extract_token(sent_emails[0])

    response = client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": "NewPassword123!",
        },
    )

    assert response.status_code == 200

    db.expire_all()
    stored = db.get(User, user.id)

    assert (
        verify_password(
            "NewPassword123!",
            stored.hashed_password,
        )
        is True
    )

    assert (
        build_session_key(session_id)
        not in fake_redis.data
    )
    assert (
        build_user_session_key(user.id)
        not in fake_redis.data
    )

    second_use = client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": "AnotherPassword123!",
        },
    )

    assert second_use.status_code == 400


def test_reset_password_rejects_invalid_token(
    client,
):
    response = client.post(
        "/auth/reset-password",
        json={
            "token": "invalid-token",
            "new_password": "NewPassword123!",
        },
    )

    assert response.status_code == 400


def test_reset_password_validates_password_length(
    client,
):
    response = client.post(
        "/auth/reset-password",
        json={
            "token": "anything",
            "new_password": "short",
        },
    )

    assert response.status_code == 422
