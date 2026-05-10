# =============================================================================
# app/utils/email.py
# -----------------------------------------------------------------------------
# Async email helper that sends transactional email with a PDF attachment.
# Uses the Resend HTTP API (resend.com) which works on Render's free tier.
# Falls back to SMTP if RESEND_API_KEY is not set.
# =============================================================================

from __future__ import annotations

import asyncio
import base64
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


async def send_email_with_pdf(
    to_addr: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Send an email with a PDF attachment.

    Prefers Resend HTTP API when RESEND_API_KEY is configured (works on
    Render free tier). Falls back to SMTP when only SMTP credentials are set.

    Args:
        to_addr:      Recipient email address.
        subject:      Email subject line.
        body:         Plain-text email body.
        pdf_bytes:    Raw PDF content to attach.
        pdf_filename: Filename shown to the recipient in their email client.

    Raises:
        RuntimeError: If neither Resend nor SMTP is configured.
    """
    from app.config import settings

    if settings.RESEND_API_KEY:
        await _send_via_resend(
            api_key=settings.RESEND_API_KEY,
            from_addr=f"Kytos Arabia <{settings.SMTP_USER or 'noreply@kytos.com'}>",
            to_addr=to_addr,
            subject=subject,
            body=body,
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf_filename,
        )
    elif settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASS:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _send_via_smtp,
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
    else:
        raise RuntimeError(
            "Email not configured — set RESEND_API_KEY or SMTP_HOST/USER/PASS in .env"
        )


async def _send_via_resend(
    api_key: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Send via Resend HTTP API (works on Render free tier)."""
    import httpx

    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
        "attachments": [
            {
                "filename": pdf_filename,
                "content": pdf_b64,
            }
        ],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        if res.status_code not in (200, 201):
            raise RuntimeError(f"Resend API error {res.status_code}: {res.text}")


def _send_via_smtp(
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
    """Send via SMTP STARTTLS (blocking — run in executor)."""
    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    part = MIMEBase("application", "pdf")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{pdf_filename}"')
    msg.attach(part)

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
