import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)


request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="-",
)


class RequestJsonFormatter(logging.Formatter):
    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        payload = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "request_id": getattr(
                record,
                "request_id",
                request_id_context.get(),
            ),
        }

        for field in (
            "method",
            "path",
            "status_code",
            "duration_ms",
        ):
            value = getattr(
                record,
                field,
                None,
            )

            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = (
                self.formatException(
                    record.exc_info
                )
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
        )


request_logger = logging.getLogger(
    "sm1le.request"
)

request_logger.setLevel(
    logging.INFO
)

request_logger.propagate = False

if not request_logger.handlers:
    handler = logging.StreamHandler(
        sys.stdout
    )

    handler.setFormatter(
        RequestJsonFormatter()
    )

    request_logger.addHandler(
        handler
    )


class RequestLoggingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
    ):
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        request_id = uuid4().hex

        token = request_id_context.set(
            request_id
        )

        state = scope.setdefault(
            "state",
            {},
        )
        state["request_id"] = request_id

        method = scope.get(
            "method",
            "-"
        )
        path = scope.get(
            "path",
            "-"
        )

        started_at = perf_counter()

        status_code: int | None = None

        async def send_with_request_id(
            message: Message,
        ) -> None:
            nonlocal status_code

            if (
                message["type"]
                == "http.response.start"
            ):
                status_code = int(
                    message["status"]
                )

                headers = [
                    (
                        name,
                        value,
                    )
                    for name, value
                    in message.get(
                        "headers",
                        []
                    )
                    if name.lower()
                    != b"x-request-id"
                ]

                headers.append(
                    (
                        b"x-request-id",
                        request_id.encode(
                            "ascii"
                        ),
                    )
                )

                message["headers"] = (
                    headers
                )

            await send(
                message
            )

        try:
            await self.app(
                scope,
                receive,
                send_with_request_id,
            )

        except Exception:
            duration_ms = round(
                (
                    perf_counter()
                    - started_at
                )
                * 1000,
                2,
            )

            request_logger.exception(
                "request_failed",
                extra={
                    "request_id":
                        request_id,
                    "method":
                        method,
                    "path":
                        path,
                    "status_code":
                        500,
                    "duration_ms":
                        duration_ms,
                },
            )

            raise

        else:
            duration_ms = round(
                (
                    perf_counter()
                    - started_at
                )
                * 1000,
                2,
            )

            request_logger.info(
                "request_completed",
                extra={
                    "request_id":
                        request_id,
                    "method":
                        method,
                    "path":
                        path,
                    "status_code":
                        status_code,
                    "duration_ms":
                        duration_ms,
                },
            )

        finally:
            request_id_context.reset(
                token
            )