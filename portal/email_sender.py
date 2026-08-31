import logging
from typing import Any, Dict

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from portal.config import settings

logger = logging.getLogger(__name__)

conf = ConnectionConfig(
    MAIL_USERNAME=settings.smtp_user,
    MAIL_PASSWORD=settings.smtp_password,
    MAIL_FROM=settings.smtp_from_email,
    MAIL_PORT=settings.smtp_port,
    MAIL_SERVER=settings.smtp_host or "localhost",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=bool(settings.smtp_user),
    VALIDATE_CERTS=True,
)


async def send_demo_request_email(form_data: Dict[str, Any]) -> None:
    if not settings.smtp_host:
        logger.warning("SMTP host is not configured. Email not sent.")
        return

    subject = f"New Demo Request from {form_data.get('email', 'Unknown')}"

    body = f"""
    New Demo Request:

    Email: {form_data.get("email")}
    First Name: {form_data.get("firstName")}
    Last Name: {form_data.get("lastName")}
    Phone Number: {form_data.get("phoneNumber")}
    Company Name: {form_data.get("companyName")}
    Country: {form_data.get("country")}
    Industry: {form_data.get("industry")}
    Company Size: {form_data.get("companySize")}
    Language Support Needed For: {form_data.get("languageSupport")}
    """

    message = MessageSchema(
        subject=subject, recipients=["voxbento.dev@gmail.com"], body=body, subtype=MessageType.plain
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        logger.info(f"Demo request email sent for {form_data.get('email')}")
    except Exception as e:
        logger.error(f"Failed to send demo request email: {e}")
