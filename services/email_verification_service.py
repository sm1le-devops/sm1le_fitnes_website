from services.email_service import send_email


async def send_verification_email(
    email: str,
    verification_link: str,
) -> None:
    await send_email(
        recipient=email,
        subject="Confirm your sm1le.fitness email",
        text=(
            "Confirm your email address by opening this link:\n\n"
            f"{verification_link}\n\n"
            "The link expires in 1 hour."
        ),
    )