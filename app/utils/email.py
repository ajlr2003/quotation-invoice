# =============================================================================
# app/utils/email.py
# -----------------------------------------------------------------------------
# Async email helper that sends transactional email with a PDF attachment.
# Priority: SendGrid HTTP API → Resend HTTP API → SMTP (fallback).
# Both SendGrid and Resend work on Render's free tier (no SMTP ports needed).
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

    Tries SendGrid first, then Resend, then SMTP.

    Args:
        to_addr:      Recipient email address.
        subject:      Email subject line.
        body:         Plain-text email body.
        pdf_bytes:    Raw PDF content to attach.
        pdf_filename: Filename shown to the recipient in their email client.

    Raises:
        RuntimeError: If no email provider is configured.
    """
    from app.config import settings

    if settings.SENDGRID_API_KEY and settings.SENDGRID_FROM_EMAIL:
        await _send_via_sendgrid(
            api_key=settings.SENDGRID_API_KEY,
            from_addr=settings.SENDGRID_FROM_EMAIL,
            to_addr=to_addr,
            subject=subject,
            body=body,
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf_filename,
        )
    elif settings.RESEND_API_KEY:
        await _send_via_resend(
            api_key=settings.RESEND_API_KEY,
            from_addr=f"Kytos Arabia <{settings.RESEND_FROM_EMAIL}>",
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
            "Email not configured — set SENDGRID_API_KEY or RESEND_API_KEY in environment"
        )


async def _send_via_sendgrid(
    api_key: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Send via SendGrid HTTP API (works on Render free tier)."""
    import httpx

    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    payload = {
        "personalizations": [{"to": [{"email": to_addr}]}],
        "from": {"email": from_addr, "name": "Kytos Arabia"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
        "attachments": [
            {
                "content": pdf_b64,
                "type": "application/pdf",
                "filename": pdf_filename,
            }
        ],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        # SendGrid returns 202 Accepted on success
        if res.status_code not in (200, 201, 202):
            raise RuntimeError(f"SendGrid API error {res.status_code}: {res.text}")


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
