from core.security import verify_password
from models import User


def test_profile_password_change_requires_current_password(
    client,
    make_user,
    login_as,
    csrf,
):
    user = make_user(
        password="OldPassword123!"
    )
    login_as(user)

    token = csrf()

    response = client.post(
        "/auth/profile",
        data={
            "csrf_token": token,
            "password": "NewPassword123!",
            "current_password": "wrong-password",
        },
    )

    assert response.status_code == 400


def test_profile_password_change_invalidates_session(
    client,
    db,
    fake_redis,
    make_user,
    login_as,
    csrf,
):
    user = make_user(
        password="OldPassword123!"
    )
    session_id = login_as(user)

    token = csrf()

    response = client.post(
        "/auth/profile",
        data={
            "csrf_token": token,
            "current_password": "OldPassword123!",
            "password": "NewPassword123!",
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["session_invalidated"]
        is True
    )

    assert (
        f"session:{session_id}"
        not in fake_redis.data
    )
    assert (
        f"user_session:{user.id}"
        not in fake_redis.data
    )

    db.expire_all()

    stored = db.get(
        User,
        user.id,
    )

    assert verify_password(
        "NewPassword123!",
        stored.hashed_password,
    )


def test_profile_email_change_requires_reverification(
    client,
    db,
    make_user,
    login_as,
    csrf,
    monkeypatch,
):
    user = make_user(
        email="old@example.com",
        password="OldPassword123!",
    )
    login_as(user)

    async def fake_send_verification_email(
        email,
        verification_link,
    ):
        return None

    monkeypatch.setattr(
        "routers.auth.send_verification_email",
        fake_send_verification_email,
    )

    token = csrf()

    response = client.post(
        "/auth/profile",
        data={
            "csrf_token": token,
            "current_password": "OldPassword123!",
            "email": "new@example.com",
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["session_invalidated"]
        is True
    )
    assert (
        response.json()["verification_required"]
        is True
    )

    db.expire_all()

    stored = db.get(
        User,
        user.id,
    )

    assert stored.email == "new@example.com"
    assert stored.email_verified is False
