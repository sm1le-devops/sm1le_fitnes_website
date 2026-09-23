import logging

import resend

from core.config import settings


logger = logging.getLogger(__name__)


def mail_is_configured() -> bool:
    return bool(
        settings.resend_api_key
        and settings.mail_from
    )


async def send_email(
    recipient: str,
    subject: str,
    text: str,
) -> bool:
    if not mail_is_configured():
        logger.warning(
            "Email skipped: Resend is not configured"
        )
        return False

    resend.api_key = settings.resend_api_key

    params: resend.Emails.SendParams = {
        "from": settings.mail_from,
        "to": [recipient],
        "subject": subject,
        "text": text,
    }

    try:
        await resend.Emails.send_async(params)

        logger.info(
            "Email sent successfully recipient=%s",
            recipient,
        )

        return True

    except Exception:
        logger.exception(
            "Email delivery failed recipient=%s",
            recipient,
        )

        return False