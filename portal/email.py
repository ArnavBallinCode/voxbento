import logging
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from portal.crypto import decrypt_val
from portal.models import Event

logger = logging.getLogger(__name__)

# Jinja2 setup
env = Environment(
    loader=FileSystemLoader("templates/emails"),
    autoescape=select_autoescape(["html", "xml"])
)

async def test_smtp_connection(
    host: str, port: int, username: str | None, password: str | None, use_tls: bool
) -> tuple[bool, str | None]:
    """Tests the SMTP connection using the provided credentials."""
    try:
        if use_tls:
            # We use starttls if the port is typically a STARTTLS port (e.g., 587)
            # or implicit TLS if the port is typically an SSL port (e.g., 465).
            # For simplicity, let aiosmtplib handle connection upgrades.
            client = aiosmtplib.SMTP(hostname=host, port=port, use_tls=(port == 465))
            await client.connect()
            if port != 465:
                await client.starttls()
        else:
            client = aiosmtplib.SMTP(hostname=host, port=port, use_tls=False)
            await client.connect()

        if username and password:
            await client.login(username, password)

        await client.quit()
        return True, None
    except Exception as e:
        logger.exception("SMTP test connection failed")
        return False, str(e)

from tenacity import retry, stop_after_attempt, wait_exponential


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
async def send_email(
    event: Event, to_email: str, subject: str, template_name: str, context: dict[str, Any]
) -> None:
    """Sends an email using the event's configured SMTP settings with retry logic."""
    if not event.smtp_host or not event.smtp_port or not event.smtp_sender_email:
        raise ValueError("SMTP configuration is incomplete for this event.")

    # Load and render the template
    template = env.get_template(template_name)
    html_content = template.render(**context)

    message = EmailMessage()
    message["From"] = f"{event.smtp_sender_name} <{event.smtp_sender_email}>" if event.smtp_sender_name else event.smtp_sender_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content("Please view this email in an HTML-capable client.")
    message.add_alternative(html_content, subtype="html")

    # Get credentials
    password = decrypt_val(event.encrypted_smtp_password) if event.encrypted_smtp_password else None

    if event.smtp_use_tls:
        client = aiosmtplib.SMTP(hostname=event.smtp_host, port=event.smtp_port, use_tls=(event.smtp_port == 465))
        await client.connect()
        if event.smtp_port != 465:
            await client.starttls()
    else:
        client = aiosmtplib.SMTP(hostname=event.smtp_host, port=event.smtp_port, use_tls=False)
        await client.connect()

    if event.smtp_username and password:
        await client.login(event.smtp_username, password)

    await client.send_message(message)
    await client.quit()
