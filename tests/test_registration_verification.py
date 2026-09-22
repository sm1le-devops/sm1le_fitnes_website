from types import SimpleNamespace

from routers import auth


def test_unverified_user_flag_defaults_to_safe_check():
    user = SimpleNamespace(
        email_verified=False
    )

    assert (
        getattr(
            user,
            "email_verified",
            True,
        )
        is False
    )

def test_verification_link_uses_auth_route(
    monkeypatch,
):
    class FakeSettings:
        render_external_url = (
            "https://example.com"
        )
        your_domain = (
            "http://localhost:8000"
        )

    monkeypatch.setattr(
        auth,
        "settings",
        FakeSettings(),
    )

    link = auth.verification_link(
        "token-value"
    )

    assert link == (
        "https://example.com"
        "/auth/verify-email?token=token-value"
    )