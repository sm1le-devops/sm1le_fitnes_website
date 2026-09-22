from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import settings


CSP_POLICY = "; ".join(
    [
        "default-src 'self'",
        (
            "script-src 'self' 'unsafe-inline' https://js.stripe.com https://cdn.jsdelivr.net"
        ),
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        (
            "connect-src 'self' "
            "https://api.stripe.com "
            "https://*.stripe.com"
        ),
        (
            "frame-src "
            "https://js.stripe.com "
            "https://hooks.stripe.com "
            "https://checkout.stripe.com"
        ),
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ]
)


def is_https_request(
    request: Request,
) -> bool:
    if request.url.scheme == "https":
        return True

    forwarded_proto = request.headers.get(
        "x-forwarded-proto",
        "",
    )

    if forwarded_proto:
        first_proto = (
            forwarded_proto
            .split(",", 1)[0]
            .strip()
            .lower()
        )

        if first_proto == "https":
            return True

    return (
        settings.render_external_url
        .strip()
        .lower()
        .startswith("https://")
    )


def build_allowed_hosts() -> list[str]:
    hosts = {
        "localhost",
        "127.0.0.1",
        "testserver",
    }

    for raw_url in (
        settings.render_external_url,
        settings.your_domain,
    ):
        raw_url = raw_url.strip()

        if not raw_url:
            continue

        parsed = urlparse(raw_url)

        if parsed.hostname:
            hosts.add(
                parsed.hostname
            )

    return sorted(hosts)


class SecurityHeadersMiddleware(
    BaseHTTPMiddleware
):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        response = await call_next(
            request
        )

        response.headers[
            "X-Content-Type-Options"
        ] = "nosniff"

        response.headers[
            "X-Frame-Options"
        ] = "DENY"

        response.headers[
            "Referrer-Policy"
        ] = (
            "strict-origin-when-cross-origin"
        )

        response.headers[
            "Permissions-Policy"
        ] = (
            "camera=(), "
            "microphone=(), "
            "geolocation=()"
        )

        response.headers[
            "Content-Security-Policy"
        ] = CSP_POLICY

        response.headers[
            "Cross-Origin-Resource-Policy"
        ] = "same-origin"

        if is_https_request(
            request
        ):
            response.headers[
                "Strict-Transport-Security"
            ] = (
                "max-age=31536000; "
                "includeSubDomains"
            )

        return response
