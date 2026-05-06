# =============================================================================
# app/utils/email.py
# -----------------------------------------------------------------------------
# Async email helper that wraps the blocking stdlib ``smtplib`` in a thread
# executor so SMTP I/O does not block the asyncio event loop.  Supports both
# STARTTLS (port 587, default) and implicit SSL/TLS (port 465) via the
# ``send_email_with_pdf`` public coroutine.
# =============================================================================

from __future__ import annotations

import asyncio
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _send_sync(
    host: str,
    port: int,
    user: str,
    password: str,
    to_addr: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Build and send a multipart email with a PDF attachment (blocking).

    This function is deliberately synchronous and is called via
    ``loop.run_in_executor`` to avoid blocking the event loop.  It uses
    STARTTLS to upgrade the connection before authenticating.

    Args:
        host:         SMTP server hostname.
        port:         SMTP server port (typically 587 for STARTTLS).
        user:         SMTP login username (also used as the From address).
        password:     SMTP login password.
        to_addr:      Recipient email address.
        subject:      Email subject line.
        body:         Plain-text email body.
        pdf_bytes:    Raw bytes of the PDF attachment.
        pdf_filename: Filename shown to the recipient for the attachment.
    """
    # ── Build the MIME message ────────────────────────────────────────────────
    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # ── Attach the PDF ────────────────────────────────────────────────────────
    part = MIMEBase("application", "pdf")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)   # base64-encode the binary payload
    part.add_header("Content-Disposition", f'attachment; filename="{pdf_filename}"')
    msg.attach(part)

    # ── Send via STARTTLS ─────────────────────────────────────────────────────
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()          # upgrade plain TCP connection to TLS
        server.login(user, password)
        server.send_message(msg)


async def send_email_with_pdf(
    to_addr: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Send an email with a PDF attachment without blocking the event loop.

    Reads SMTP credentials from ``app.config.settings`` at call time.
    The blocking SMTP work is offloaded to the default thread-pool executor
    via ``loop.run_in_executor``.

    Args:
        to_addr:      Recipient email address.
        subject:      Email subject line.
        body:         Plain-text email body.
        pdf_bytes:    Raw PDF content to attach.
        pdf_filename: Filename shown to the recipient in their email client.

    Raises:
        RuntimeError: If SMTP_HOST, SMTP_USER, or SMTP_PASS are not configured
            in the application settings.
    """
    from app.config import settings

    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASS:
        raise RuntimeError(
            "SMTP not configured — set SMTP_HOST, SMTP_USER, SMTP_PASS in .env"
        )

    # run_in_executor offloads the blocking smtplib call to a thread
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,           # use the default ThreadPoolExecutor
        _send_sync,
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        settings.SMTP_USER,
        settings.SMTP_PASS,
        to_addr,
        subject,
        body,
        pdf_bytes,
        pdf_filename,
    )
