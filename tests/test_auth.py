from core.security import (
    generate_csrf_token,
    verify_password,
)
from models import User


def get_csrf_from_page(client, path):
    response = client.get(path)

    assert response.status_code == 200

    token = response.cookies.get(
        "csrf_token"
    )

    assert token
    return token


def test_register_creates_user_and_profile(client, db):
    csrf = get_csrf_from_page(
        client,
        "/auth/register",
    )

    response = client.post(
        "/auth/register",
        json={
            "username": "new_user",
            "email": "new@example.com",
            "password": "Password123!",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Success"

    db.expire_all()

    user = (
        db.query(User)
        .filter(User.username == "new_user")
        .first()
    )

    assert user is not None
    assert user.profile is not None
    assert (
        verify_password(
            "Password123!",
            user.hashed_password,
        )
        is True
    )


def test_register_rejects_csrf_mismatch(client):
    get_csrf_from_page(
        client,
        "/auth/register",
    )

    different_valid_token = (
        generate_csrf_token()
    )

    response = client.post(
        "/auth/register",
        json={
            "username": "new_user",
            "email": "new@example.com",
            "password": "Password123!",
            "csrf_token": different_valid_token,
        },
    )

    assert response.status_code == 403


def test_register_rejects_invalid_username(client):
    csrf = get_csrf_from_page(
        client,
        "/auth/register",
    )

    response = client.post(
        "/auth/register",
        json={
            "username": "bad-name",
            "email": "new@example.com",
            "password": "Password123!",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 400


def test_register_rejects_duplicate_user(
    client,
    make_user,
):
    make_user(
        username="existing",
        email="existing@example.com",
    )

    csrf = get_csrf_from_page(
        client,
        "/auth/register",
    )

    response = client.post(
        "/auth/register",
        json={
            "username": "existing",
            "email": "another@example.com",
            "password": "Password123!",
            "csrf_token": csrf,
        },
    )

    assert response.status_code in (400, 409)


def test_login_rejects_wrong_password(
    client,
    make_user,
):
    make_user(
        username="login_user",
        email="login@example.com",
        password="CorrectPassword123!",
    )

    csrf = get_csrf_from_page(
        client,
        "/auth/login",
    )

    response = client.post(
        "/auth/login",
        json={
            "username": "login_user",
            "password": "wrong-password",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 401


def test_login_rejects_disabled_user(
    client,
    make_user,
):
    make_user(
        username="disabled",
        email="disabled@example.com",
        is_active=False,
    )

    csrf = get_csrf_from_page(
        client,
        "/auth/login",
    )

    response = client.post(
        "/auth/login",
        json={
            "username": "disabled",
            "password": "Password123!",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 403


def test_login_creates_server_side_session(
    client,
    fake_redis,
    make_user,
):
    user = make_user(
        username="login_user",
        email="login@example.com",
    )

    csrf = get_csrf_from_page(
        client,
        "/auth/login",
    )

    response = client.post(
        "/auth/login",
        json={
            "username": "login_user",
            "password": "Password123!",
            "csrf_token": csrf,
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["redirect_url"]
        == "/auth/welcome"
    )

    session_id = response.cookies.get(
        "session_id"
    )

    assert session_id
    assert (
        fake_redis.data[
            f"session:{session_id}"
        ]
        == str(user.id)
    )


def test_profile_requires_authentication(client):
    response = client.get(
        "/auth/profile",
        follow_redirects=False,
    )

    assert response.status_code in (401, 303)


def test_profile_update_writes_normalized_profile(
    client,
    db,
    make_user,
    login_as,
    csrf,
):
    user = make_user()
    login_as(user)

    token = csrf()

    response = client.post(
        "/auth/profile",
        data={
            "csrf_token": token,
            "gender": "male",
            "weight": "82.5",
            "height": "189",
        },
    )

    assert response.status_code == 200

    db.expire_all()

    stored = db.get(User, user.id)

    assert stored.profile is not None
    assert stored.profile.gender == "male"
    assert stored.profile.weight == 82.5
    assert stored.profile.height == 189


def test_logout_deletes_redis_session(
    client,
    fake_redis,
    make_user,
    login_as,
    csrf,
):
    user = make_user()
    session_id = login_as(user)
    token = csrf()

    response = client.post(
        "/auth/logout",
        data={
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert (
        f"session:{session_id}"
        not in fake_redis.data
    )
    assert (
        f"user_session:{user.id}"
        not in fake_redis.data
    )
