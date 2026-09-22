import logging

from fastapi_mail import (
    ConnectionConfig,
    FastMail,
    MessageSchema,
    MessageType,
    NameEmail,
)

from pydantic import SecretStr

from core.config import settings


logger = logging.getLogger(__name__)


conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_user,
    MAIL_PASSWORD=SecretStr(settings.mail_password),
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=settings.mail_port,
    MAIL_SERVER=settings.mail_server,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
)


def mail_is_configured() -> bool:
    return bool(
        settings.mail_user
        and settings.mail_password
        and settings.mail_from
    )


async def send_verification_email(
    email: str,
    verification_link: str,
) -> None:
    if not mail_is_configured():
        logger.warning(
            "Verification email skipped: mail is not configured"
        )
        return

    message = MessageSchema(
        subject="Confirm your sm1le.fitness email",
        recipients=[
            NameEmail(
            name="",
            email=email,
            )
        ],
        body=(
            "Confirm your email address by opening this link:\n\n"
            f"{verification_link}\n\n"
            "The link expires in 1 hour."
        ),
        subtype=MessageType.plain,
    )

    try:
        await FastMail(
            conf
        ).send_message(
            message
        )
    except Exception:
        # Email delivery is an external side effect.
        # A temporary SMTP outage must not roll back an already-created user.
        # The failure is logged and the user can request a resend later.
        logger.exception(
            "Verification email delivery failed"
        )
