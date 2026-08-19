"""Transactional email delivery.

Development uses Mailpit on ``localhost:1025``. Messages carry links and never
include submitted content. Delivery failures are logged as an event code and do
not leak recipient addresses into the log.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import Settings

logger = logging.getLogger(__name__)


def _send(settings: Settings, to_address: str, subject: str, body: str) -> bool:
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        # The address is deliberately absent from this log line.
        logger.warning(
            "email delivery failed",
            extra={"event": "email_failed", "error_type": type(exc).__name__},
        )
        return False


def send_verification_email(settings: Settings, to_address: str, token: str) -> bool:
    link = f"{settings.cors_origin_list[0]}/verify?token={token}"
    return _send(
        settings,
        to_address,
        "Confirm your OriginLens address",
        "Confirm your email address to finish creating your OriginLens account:\n\n"
        f"{link}\n\nThis link expires in 24 hours. If you did not create an "
        "account, you can ignore this message.\n",
    )


def send_password_reset_email(settings: Settings, to_address: str, token: str) -> bool:
    link = f"{settings.cors_origin_list[0]}/reset-password?token={token}"
    return _send(
        settings,
        to_address,
        "Reset your OriginLens password",
        f"Use this link to choose a new password:\n\n{link}\n\nThe link expires "
        "in one hour and can be used once. If you did not request a reset, no "
        "action is needed.\n",
    )
