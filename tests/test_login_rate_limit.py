from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.auth as auth
from database import get_db
from services.login_security_service import (
    LoginBlock,
)


class DummyQuery:
    def __init__(self, user):
        self.user = user

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.user


class DummyDB:
    def __init__(self, user=None):
        self.user = user

    def query(self, *_args, **_kwargs):
        return DummyQuery(
            self.user
        )


def make_test_client(
    db,
) -> TestClient:
    app = FastAPI()

    app.state.redis = object()

    app.include_router(
        auth.router,
        prefix="/auth",
    )

    def override_get_db():
        yield db

    app.dependency_overrides[
        get_db
    ] = override_get_db

    return TestClient(app)


def valid_login_payload():
    return {
        "username": "admin",
        "password": "password123",
        "csrf_token": "test-csrf",
    }


def test_login_returns_429_when_redis_guard_is_already_blocked(
    monkeypatch,
):
    client = make_test_client(
        DummyDB()
    )

    monkeypatch.setattr(
        auth,
        "check_csrf",
        lambda *_args, **_kwargs: None,
    )

    async def blocked(**_kwargs):
        return LoginBlock(
            retry_after=77,
            scope="user",
        )

    monkeypatch.setattr(
        auth,
        "get_login_block",
        blocked,
    )

    response = client.post(
        "/auth/login",
        json=valid_login_payload(),
    )

    assert response.status_code == 429
    assert (
        response.headers["retry-after"]
        == "77"
    )
    assert response.json()["detail"] == (
        "Too many login attempts. Please try again later."
    )


def test_failed_login_records_failure_and_returns_401(
    monkeypatch,
):
    client = make_test_client(
        DummyDB(user=None)
    )

    monkeypatch.setattr(
        auth,
        "check_csrf",
        lambda *_args, **_kwargs: None,
    )

    async def not_blocked(**_kwargs):
        return None

    captured = {}

    async def record_failure(
        redis,
        username,
        client_ip,
    ):
        captured["redis"] = redis
        captured["username"] = username
        captured["client_ip"] = (
            client_ip
        )

        return None

    monkeypatch.setattr(
        auth,
        "get_login_block",
        not_blocked,
    )
    monkeypatch.setattr(
        auth,
        "record_failed_login",
        record_failure,
    )

    response = client.post(
        "/auth/login",
        json=valid_login_payload(),
    )

    assert response.status_code == 401
    assert captured["username"] == "admin"
    assert captured["client_ip"]


def test_failed_attempt_that_reaches_limit_returns_429(
    monkeypatch,
):
    client = make_test_client(
        DummyDB(user=None)
    )

    monkeypatch.setattr(
        auth,
        "check_csrf",
        lambda *_args, **_kwargs: None,
    )

    async def not_blocked(**_kwargs):
        return None

    async def threshold_reached(
        **_kwargs,
    ):
        return LoginBlock(
            retry_after=900,
            scope="user",
        )

    monkeypatch.setattr(
        auth,
        "get_login_block",
        not_blocked,
    )
    monkeypatch.setattr(
        auth,
        "record_failed_login",
        threshold_reached,
    )

    response = client.post(
        "/auth/login",
        json=valid_login_payload(),
    )

    assert response.status_code == 429
    assert (
        response.headers["retry-after"]
        == "900"
    )


def test_successful_login_clears_username_failure_counter(
    monkeypatch,
):
    user = SimpleNamespace(
        id=123,
        hashed_password="hash",
        is_active=True,
    )

    client = make_test_client(
        DummyDB(user=user)
    )

    monkeypatch.setattr(
        auth,
        "check_csrf",
        lambda *_args, **_kwargs: None,
    )

    async def not_blocked(**_kwargs):
        return None

    monkeypatch.setattr(
        auth,
        "get_login_block",
        not_blocked,
    )

    monkeypatch.setattr(
        auth,
        "verify_password_or_dummy",
        lambda *_args, **_kwargs: True,
    )

    cleared = {}

    async def clear_user_failures(
        redis,
        username,
    ):
        cleared["redis"] = redis
        cleared["username"] = username

    monkeypatch.setattr(
        auth,
        "clear_login_user_failures",
        clear_user_failures,
    )

    async def fake_create_session(
        redis,
        user_id,
    ):
        assert user_id == 123
        return "session-test"

    monkeypatch.setattr(
        auth,
        "create_session",
        fake_create_session,
    )

    response = client.post(
        "/auth/login",
        json=valid_login_payload(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "redirect_url":
        "/auth/welcome"
    }

    assert (
        cleared["username"]
        == "admin"
    )
