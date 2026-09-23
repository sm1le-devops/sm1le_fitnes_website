import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# Environment variables must be set BEFORE importing app/config.
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:///:memory:",
)
os.environ.setdefault(
    "CSRF_SECRET",
    "test-csrf-secret-123456789",
)
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-jwt-secret-123456789",
)
os.environ.setdefault(
    "YOUR_DOMAIN",
    "https://testserver",
)
os.environ.setdefault(
    "RENDER_EXTERNAL_URL",
    "",
)
os.environ.setdefault(
    "REDIS_URL",
    "redis://localhost:6379/15",
)

os.environ.setdefault(
    "STRIPE_SECRET_KEY",
    "sk_test_dummy",
)
os.environ.setdefault(
    "STRIPE_PUBLISHABLE_KEY",
    "pk_test_dummy",
)
os.environ.setdefault(
    "STRIPE_WEBHOOK_SECRET",
    "whsec_test_dummy",
)

# Resend test configuration.
# No real request will be sent because send_email
# is monkeypatched below.
os.environ.setdefault(
    "RESEND_API_KEY",
    "re_test_dummy",
)
os.environ.setdefault(
    "MAIL_FROM",
    "sm1le.fitness <noreply@mail.alabushev.dev>",
)

# Legacy SMTP settings.
# They can be removed later when SMTP dependencies
# are completely removed from the project.
os.environ.setdefault(
    "MAIL_USER",
    "tests@example.com",
)
os.environ.setdefault(
    "MAIL_PASSWORD",
    "test-password",
)
os.environ.setdefault(
    "MAIL_SERVER",
    "smtp.gmail.com",
)
os.environ.setdefault(
    "MAIL_PORT",
    "587",
)


from core.security import (
    generate_csrf_token,
    get_password_hash,
)
from database import Base, get_db
from main import app
from models import User, UserProfile
from services.plan_service import PLANS
from services.session_service import create_session


TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
    future=True,
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(
    dbapi_connection,
    _,
):
    cursor = dbapi_connection.cursor()

    cursor.execute(
        "PRAGMA foreign_keys=ON"
    )

    cursor.close()


TestingSessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


class FakeRedis:
    """Minimal async Redis for tests."""

    def __init__(self):
        self.data = {}

    async def ping(self):
        return True

    async def aclose(self):
        return None

    async def get(self, key):
        return self.data.get(
            str(key)
        )

    async def set(
        self,
        key,
        value,
        ex=None,
        nx=False,
    ):
        key = str(key)

        if nx and key in self.data:
            return False

        self.data[key] = str(value)

        return True

    async def delete(
        self,
        *keys,
    ):
        deleted = 0

        for key in keys:
            key = str(key)

            if key in self.data:
                deleted += 1
                del self.data[key]

        return deleted

    async def getdel(
        self,
        key,
    ):
        return self.data.pop(
            str(key),
            None,
        )

    async def exists(
        self,
        key,
    ):
        return int(
            str(key) in self.data
        )

    async def flushall(self):
        self.data.clear()

        return True


@pytest.fixture(autouse=True)
def bypass_rate_limiter(
    monkeypatch,
):
    async def allow_request(
        self,
        request: Request,
        response: Response,
    ) -> None:
        return None

    monkeypatch.setattr(
        RateLimiter,
        "__call__",
        allow_request,
    )


@pytest.fixture(autouse=True)
def sent_emails(
    monkeypatch,
):
    """
    Prevent every test from sending real email.

    The fake is compatible with both:
    - registration verification email
    - password reset email
    """

    sent = []

    async def fake_send_email(
        recipient: str,
        subject: str,
        text: str,
    ) -> bool:
        sent.append(
            SimpleNamespace(
                recipients=[
                    recipient
                ],
                subject=subject,
                body=text,
            )
        )

        return True

    monkeypatch.setattr(
        "routers.password_reset.send_email",
        fake_send_email,
    )

    monkeypatch.setattr(
        (
            "services."
            "email_verification_service."
            "send_email"
        ),
        fake_send_email,
    )

    return sent


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(
        bind=engine
    )

    Base.metadata.create_all(
        bind=engine
    )

    yield

    Base.metadata.drop_all(
        bind=engine
    )


@pytest.fixture
def db():
    session = TestingSessionLocal()

    try:
        yield session

    finally:
        session.close()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def client(
    fake_redis,
):
    app.state.redis = fake_redis

    def override_get_db():
        session = TestingSessionLocal()

        try:
            yield session

        finally:
            session.close()

    app.dependency_overrides[
        get_db
    ] = override_get_db

    test_client = TestClient(
        app,
        base_url="https://testserver",
    )

    yield test_client

    test_client.cookies.clear()

    app.dependency_overrides.clear()


@pytest.fixture
def plan_id():
    assert PLANS, (
        "plans.json is empty"
    )

    return next(
        iter(
            PLANS.keys()
        )
    )


@pytest.fixture
def make_user():
    def _make_user(
        username="tester",
        email="tester@example.com",
        password="Password123!",
        is_active=True,
        with_profile=True,
    ):
        session = TestingSessionLocal()

        try:
            user = User(
                username=username,
                email=email,
                hashed_password=(
                    get_password_hash(
                        password
                    )
                ),
                is_active=is_active,
            )

            if with_profile:
                user.profile = (
                    UserProfile()
                )

            session.add(user)
            session.commit()
            session.refresh(user)

            user_id = user.id

        finally:
            session.close()

        check = TestingSessionLocal()

        try:
            return check.get(
                User,
                user_id,
            )

        finally:
            check.close()

    return _make_user


@pytest.fixture
def login_as(
    client,
    fake_redis,
):
    def _login_as(user):
        session_id = asyncio.run(
            create_session(
                fake_redis,
                user.id,
            )
        )

        client.cookies.set(
            "session_id",
            session_id,
        )

        return session_id

    return _login_as


@pytest.fixture
def csrf(
    client,
):
    def _csrf():
        token = (
            generate_csrf_token()
        )

        client.cookies.set(
            "csrf_token",
            token,
        )

        return token

    return _csrf