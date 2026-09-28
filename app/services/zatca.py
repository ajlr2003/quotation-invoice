# =============================================================================
# app/services/zatca.py
# -----------------------------------------------------------------------------
# ZATCA (Saudi tax authority) Phase 1 "simplified tax invoice" QR code.
#
# Phase 1 only requires a TLV-encoded, base64 QR tag embedded on the invoice —
# no external account or API call. It is NOT the same as Phase 2 ("Fatoora")
# real-time e-invoice clearance, which requires the business to onboard with
# ZATCA, obtain a cryptographic signing certificate from them, and clear every
# invoice through their API before it's issued — that's a compliance project
# for Kytos to run with ZATCA directly, not something addable from here.
#
# TLV = one byte tag, one byte length, then that many bytes of UTF-8 value,
# repeated for the 5 required fields, concatenated and base64-encoded.
# =============================================================================

from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO

import qrcode


def _tlv(tag: int, value: str) -> bytes:
    data = value.encode("utf-8")
    if len(data) > 255:
        data = data[:255]  # each TLV length byte caps a field at 255 bytes
    return bytes([tag, len(data)]) + data


def build_zatca_qr_payload(
    seller_name: str,
    vat_number: str,
    timestamp: datetime,
    invoice_total: float,
    vat_total: float,
) -> str:
    """Return the base64 TLV payload ZATCA's Phase 1 QR code must contain."""
    tlv = (
        _tlv(1, seller_name)
        + _tlv(2, vat_number)
        + _tlv(3, timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"))
        + _tlv(4, f"{invoice_total:.2f}")
        + _tlv(5, f"{vat_total:.2f}")
    )
    return base64.b64encode(tlv).decode("ascii")


def build_zatca_qr_image(
    seller_name: str,
    vat_number: str,
    timestamp: datetime,
    invoice_total: float,
    vat_total: float,
) -> BytesIO:
    """Render the QR code (encoding the base64 TLV payload) as a PNG in memory."""
    payload = build_zatca_qr_payload(seller_name, vat_number, timestamp, invoice_total, vat_total)
    img = qrcode.make(payload, border=1)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
