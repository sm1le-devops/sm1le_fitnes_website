from fastapi import (
    FastAPI,
    Request,
)
from fastapi.testclient import (
    TestClient,
)

from core.request_logging import (
    RequestLoggingMiddleware,
)


def build_app() -> FastAPI:
    app = FastAPI()

    app.add_middleware(
        RequestLoggingMiddleware
    )

    @app.get("/test")
    async def test_endpoint(
        request: Request,
    ):
        return {
            "request_id":
                request.state.request_id
        }

    return app


def test_request_id_is_generated():
    client = TestClient(
        build_app()
    )

    response = client.get(
        "/test"
    )

    assert response.status_code == 200

    request_id = response.headers[
        "x-request-id"
    ]

    assert len(request_id) == 32

    assert (
        response.json()[
            "request_id"
        ]
        == request_id
    )


def test_each_request_gets_unique_id():
    client = TestClient(
        build_app()
    )

    first = client.get(
        "/test"
    )

    second = client.get(
        "/test"
    )

    assert (
        first.headers[
            "x-request-id"
        ]
        != second.headers[
            "x-request-id"
        ]
    )