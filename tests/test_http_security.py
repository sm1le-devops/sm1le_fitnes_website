from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.testclient import TestClient

from core.security_headers import (
    CSP_POLICY,
    SecurityHeadersMiddleware,
)


def make_app() -> FastAPI:
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://example.com"
        ],
        allow_credentials=True,
        allow_methods=[
            "GET",
            "POST",
            "OPTIONS",
        ],
        allow_headers=[
            "Content-Type",
            "X-CSRF-Token",
        ],
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "testserver"
        ],
    )

    app.add_middleware(
        SecurityHeadersMiddleware,
    )

    @app.get("/test")
    async def test_route():
        return {
            "ok": True
        }

    return app


def test_security_headers_are_present():
    client = TestClient(
        make_app(),
        base_url="https://testserver",
    )

    response = client.get(
        "/test"
    )

    assert response.status_code == 200

    assert (
        response.headers[
            "x-content-type-options"
        ]
        == "nosniff"
    )

    assert (
        response.headers[
            "x-frame-options"
        ]
        == "DENY"
    )

    assert (
        response.headers[
            "referrer-policy"
        ]
        == "strict-origin-when-cross-origin"
    )

    assert (
        response.headers[
            "permissions-policy"
        ]
        == (
            "camera=(), "
            "microphone=(), "
            "geolocation=()"
        )
    )


def test_csp_is_attached():
    client = TestClient(
        make_app(),
        base_url="https://testserver",
    )

    response = client.get(
        "/test"
    )

    assert (
        response.headers[
            "content-security-policy"
        ]
        == CSP_POLICY
    )

    assert (
        "frame-ancestors 'none'"
        in CSP_POLICY
    )
    assert (
        "object-src 'none'"
        in CSP_POLICY
    )


def test_hsts_is_present_on_https():
    client = TestClient(
        make_app(),
        base_url="https://testserver",
    )

    response = client.get(
        "/test"
    )

    assert (
        response.headers[
            "strict-transport-security"
        ]
        == (
            "max-age=31536000; "
            "includeSubDomains"
        )
    )


def test_cors_allows_expected_origin():
    client = TestClient(
        make_app(),
        base_url="https://testserver",
    )

    response = client.options(
        "/test",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method":
                "POST",
            "Access-Control-Request-Headers":
                "X-CSRF-Token",
        },
    )

    assert response.status_code == 200

    assert (
        response.headers[
            "access-control-allow-origin"
        ]
        == "https://example.com"
    )


def test_cors_rejects_untrusted_origin():
    client = TestClient(
        make_app(),
        base_url="https://testserver",
    )

    response = client.options(
        "/test",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method":
                "POST",
            "Access-Control-Request-Headers":
                "X-CSRF-Token",
        },
    )

    assert response.status_code == 400

    assert (
        response.headers.get(
            "access-control-allow-origin"
        )
        is None
    )


def test_trusted_host_rejects_bad_host():
    client = TestClient(
        make_app(),
        base_url="https://evil.example",
    )

    response = client.get(
        "/test"
    )

    assert response.status_code == 400
