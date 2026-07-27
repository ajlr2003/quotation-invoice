# =============================================================================
# app/routers/odoo.py
# -----------------------------------------------------------------------------
# FastAPI proxy router for Odoo integration. All routes delegate to the Odoo
# XML-RPC API via app.integrations.odoo_client and return data normalised into
# Kytos-standard JSON shapes that the frontend already understands.
#
# All routes are mounted under /api/v1/odoo by app/main.py.
#
# Endpoint summary:
#   GET  /invoices          — list customer invoices from Odoo
#   POST /invoices          — create a customer invoice in Odoo
#   POST /invoices/{id}/confirm   — post (confirm) a draft invoice in Odoo
#   GET  /invoices/kpis     — invoice KPIs: total, received, outstanding, overdue
#   GET  /partners          — list Odoo contacts for client autocomplete
#
# All routes require a valid Kytos JWT (get_current_user dependency).
# =============================================================================

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import settings
from app.integrations.odoo_client import odoo
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole

logger = logging.getLogger(__name__)
router = APIRouter()

_finance_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.FINANCE)

# ── Odoo field lists ──────────────────────────────────────────────────────────
_INVOICE_FIELDS = [
    "name", "partner_id", "invoice_date", "invoice_date_due",
    "amount_untaxed", "amount_tax", "amount_total", "amount_residual",
    "state", "payment_state", "move_type", "narration",
]


# =============================================================================
# Helpers
# =============================================================================

def _map_status(state: str, payment_state: str, due_date: Optional[str]) -> str:
    """Convert Odoo state/payment_state pair to a Kytos UI status string.

    Args:
        state:         Odoo move state — ``"draft"`` or ``"posted"``.
        payment_state: Odoo payment state — ``"not_paid"``, ``"paid"``, etc.
        due_date:      ISO date string of the invoice due date, or None.

    Returns:
        One of ``"Draft"``, ``"Sent"``, ``"Paid"``, ``"Overdue"``.
    """
    if state == "draft":
        return "Draft"
    if payment_state == "paid":
        return "Paid"
    # Posted but not paid — check if overdue
    if due_date:
        try:
            due = date.fromisoformat(due_date)
            if due < date.today():
                return "Overdue"
        except ValueError:
            pass
    return "Sent"


def _fmt_currency(amount: float) -> str:
    """Format a float amount as a dollar string, e.g. 12450.0 → '$12,450.00'."""
    return f"${amount:,.2f}"


def _normalise_invoice(rec: dict) -> dict:
    """Convert a raw Odoo account.move record to Kytos invoice shape.

    Args:
        rec: Raw dict from Odoo search_read on account.move.

    Returns:
        Normalised dict ready for the frontend invoice list.
    """
    partner = rec.get("partner_id")
    company = partner[1] if partner else "Unknown"

    inv_date = rec.get("invoice_date") or ""
    due_date = rec.get("invoice_date_due") or ""

    # Friendly date display
    def fmt_date(d: str) -> str:
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%b %d, %Y")
        except Exception:
            return d or "—"

    dates_str = f"Created: {fmt_date(inv_date)} • Due: {fmt_date(due_date)}"
    ui_status = _map_status(rec["state"], rec.get("payment_state", "not_paid"), due_date)

    return {
        "id":          rec["id"],
        "num":         rec.get("name") or f"DRAFT-{rec['id']}",
        "company":     company,
        "dates":       dates_str,
        "invoice_date": inv_date,
        "due_date":    due_date,
        "amount":      _fmt_currency(rec.get("amount_total", 0)),
        "amount_total": float(rec.get("amount_total", 0)),
        "amount_residual": float(rec.get("amount_residual", 0)),
        "status":      ui_status,
        "odoo_state":  rec["state"],
        "payment_state": rec.get("payment_state", "not_paid"),
        "source":      "odoo",   # badge indicator for frontend
    }


# =============================================================================
# Invoice KPIs
# =============================================================================

@router.get(
    "/invoices/kpis",
    summary="Invoice KPIs from Odoo",
    description=(
        "Returns four aggregated KPI values computed from Odoo's account.move "
        "records: total invoiced (all posted), received (paid), outstanding "
        "(unpaid residual), and count of overdue invoices."
    ),
)
async def invoice_kpis(_=Depends(get_current_user)) -> dict:
    try:
        posted = await odoo.search_read(
            "account.move",
            [["move_type", "=", "out_invoice"], ["state", "=", "posted"]],
            ["amount_total", "amount_residual", "payment_state", "invoice_date_due"],
            limit=500,
        )
    except Exception as e:
        logger.error("Odoo KPI fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Odoo error: {e}")

    today = date.today()
    total_invoiced = sum(float(r.get("amount_total", 0)) for r in posted)
    total_received = sum(
        float(r.get("amount_total", 0))
        for r in posted if r.get("payment_state") == "paid"
    )
    total_outstanding = sum(float(r.get("amount_residual", 0)) for r in posted)

    overdue_count = 0
    for r in posted:
        due = r.get("invoice_date_due")
        if due and r.get("payment_state") != "paid":
            try:
                if date.fromisoformat(due) < today:
                    overdue_count += 1
            except ValueError:
                pass

    return {
        "total_invoiced":   round(total_invoiced, 2),
        "total_received":   round(total_received, 2),
        "total_outstanding": round(total_outstanding, 2),
        "overdue_count":    overdue_count,
        "invoice_count":    len(posted),
    }


# =============================================================================
# Invoice list
# =============================================================================

@router.get(
    "/invoices",
    summary="List customer invoices from Odoo",
    description=(
        "Returns customer invoices (account.move, move_type=out_invoice) from Odoo, "
        "normalised into Kytos UI format. Optionally filter by status: "
        "Draft | Sent | Paid | Overdue."
    ),
)
async def list_invoices(
    status_filter: Optional[str] = Query(None, alias="status", description="Draft | Sent | Paid | Overdue"),
    limit: int = Query(50, ge=1, le=200),
    _=Depends(get_current_user),
) -> dict:
    try:
        domain: list[Any] = [["move_type", "=", "out_invoice"]]

        # Pre-filter at DB level where possible
        if status_filter == "Draft":
            domain.append(["state", "=", "draft"])
        elif status_filter in ("Sent", "Overdue", "Paid"):
            domain.append(["state", "=", "posted"])
            if status_filter == "Paid":
                domain.append(["payment_state", "=", "paid"])

        records = await odoo.search_read(
            "account.move", domain, _INVOICE_FIELDS, limit=limit
        )
    except Exception as e:
        logger.error("Odoo invoice list failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Odoo error: {e}")

    invoices = [_normalise_invoice(r) for r in records]

    # Post-filter overdue (requires date comparison — can't do in Odoo domain easily)
    if status_filter == "Overdue":
        invoices = [i for i in invoices if i["status"] == "Overdue"]
    elif status_filter == "Sent":
        invoices = [i for i in invoices if i["status"] == "Sent"]

    # Count per status for sidebar badges
    all_records = await odoo.search_read(
        "account.move",
        [["move_type", "=", "out_invoice"]],
        ["state", "payment_state", "invoice_date_due"],
        limit=500,
    )
    all_norm = [_normalise_invoice(r) for r in all_records]
    counts = {s: sum(1 for i in all_norm if i["status"] == s)
              for s in ("Draft", "Sent", "Paid", "Overdue")}

    return {"items": invoices, "total": len(invoices), "counts": counts}


# =============================================================================
# Create invoice
# =============================================================================

class InvoiceCreateRequest(BaseModel):
    """Payload for creating a customer invoice in Odoo."""
    client: str
    amount: float
    due: Optional[str] = None       # ISO date string YYYY-MM-DD
    desc: Optional[str] = None
    payment_terms: Optional[str] = None


@router.post(
    "/invoices",
    status_code=201,
    summary="Create a customer invoice in Odoo",
    description=(
        "Creates a draft customer invoice in Odoo. "
        "If the client name matches an existing Odoo contact it is linked; "
        "otherwise a new contact is created automatically."
    ),
)
async def create_invoice(
    payload: InvoiceCreateRequest,
    _=Depends(_finance_roles),
) -> dict:
    try:
        # Resolve or create Odoo partner
        partner_ids = await odoo.execute(
            "res.partner", "search",
            [[["name", "ilike", payload.client.strip()]]],
            {"limit": 1},
        )
        if partner_ids:
            partner_id = partner_ids[0]
        else:
            partner_id = await odoo.create("res.partner", {"name": payload.client.strip()})

        # Build invoice record
        invoice_vals: dict[str, Any] = {
            "move_type": "out_invoice",
            "partner_id": partner_id,
            "invoice_line_ids": [(0, 0, {
                "name": payload.desc or "Services rendered",
                "quantity": 1,
                "price_unit": payload.amount,
            })],
        }
        if payload.due:
            invoice_vals["invoice_date_due"] = payload.due
        if payload.desc:
            invoice_vals["narration"] = payload.desc

        invoice_id = await odoo.create("account.move", invoice_vals)

        # Fetch the created record to return normalised shape
        records = await odoo.search_read(
            "account.move", [["id", "=", invoice_id]], _INVOICE_FIELDS, limit=1
        )
        if not records:
            raise HTTPException(status_code=500, detail="Invoice created but could not be retrieved")

        return _normalise_invoice(records[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Odoo invoice creation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Odoo error: {e}")


# =============================================================================
# Confirm (post) invoice
# =============================================================================

@router.post(
    "/invoices/{invoice_id}/confirm",
    summary="Post (confirm) a draft invoice in Odoo",
    description=(
        "Transitions a draft invoice to posted state in Odoo (equivalent to "
        "clicking 'Confirm' in the Odoo UI). A confirmed invoice is assigned "
        "a sequential invoice number and becomes billable."
    ),
)
async def confirm_invoice(
    invoice_id: int,
    _=Depends(_finance_roles),
) -> dict:
    try:
        await odoo.action("account.move", "action_post", [invoice_id])
        records = await odoo.search_read(
            "account.move", [["id", "=", invoice_id]], _INVOICE_FIELDS, limit=1
        )
        if not records:
            raise HTTPException(status_code=404, detail="Invoice not found after confirm")
        return _normalise_invoice(records[0])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Odoo invoice confirm failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Odoo error: {e}")


# =============================================================================
# Invoice PDF download
# =============================================================================

@router.get(
    "/invoices/{invoice_id}/pdf",
    summary="Download invoice PDF from Odoo",
    response_class=Response,
)
async def download_invoice_pdf(
    invoice_id: int,
    _=Depends(get_current_user),
) -> Response:
    """Fetch the invoice PDF from Odoo via its HTTP report controller.

    Odoo SaaS 17+ removed render_qweb_pdf from XML-RPC. We authenticate
    via the JSON-RPC session endpoint, grab the session cookie, then fetch
    the PDF through /report/pdf/account.report_invoice/{id}.
    """
    import base64

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:

            # Step 1 — authenticate via Odoo web session using the account password
            password = settings.ODOO_PASSWORD
            if not password:
                raise RuntimeError(
                    "ODOO_PASSWORD is not set in .env — add it to enable PDF downloads. "
                    "Use your Odoo login password (same one you use at kytos1.odoo.com)."
                )

            auth = await client.post(
                f"{odoo._url}/web/session/authenticate",
                json={
                    "jsonrpc": "2.0", "method": "call", "id": 1,
                    "params": {
                        "db":       odoo._db,
                        "login":    odoo._login,
                        "password": password,
                    },
                },
                headers={"Content-Type": "application/json"},
            )
            auth.raise_for_status()
            auth_result = auth.json().get("result", {})
            if not auth_result.get("uid"):
                raise RuntimeError("Odoo session auth failed — check ODOO_PASSWORD in .env")

            session_id = auth.cookies.get("session_id")
            if not session_id:
                raise RuntimeError("Odoo did not return a session cookie")

            # Step 2 — fetch the PDF using the session cookie
            pdf_resp = await client.get(
                f"{odoo._url}/report/pdf/account.report_invoice/{invoice_id}",
                cookies={"session_id": session_id},
            )
            pdf_resp.raise_for_status()

            ct = pdf_resp.headers.get("content-type", "")
            if "application/pdf" not in ct:
                raise RuntimeError(
                    f"Odoo returned non-PDF response ({pdf_resp.status_code}): {pdf_resp.text[:200]}"
                )

            return Response(
                content=pdf_resp.content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="invoice-{invoice_id}.pdf"',
                    "Content-Length": str(len(pdf_resp.content)),
                },
            )

    except Exception as e:
        logger.error("Odoo PDF download failed for invoice %s: %s", invoice_id, e)
        raise HTTPException(status_code=502, detail=f"Could not generate PDF: {e}")


# =============================================================================
# Partners (for client autocomplete)
# =============================================================================

@router.get(
    "/partners",
    summary="List Odoo contacts",
    description="Returns Odoo contacts for use in client autocomplete fields.",
)
async def list_partners(
    q: str = Query("", description="Search by name"),
    _=Depends(get_current_user),
) -> list[dict]:
    try:
        domain: list[Any] = [["active", "=", True]]
        if q:
            domain.append(["name", "ilike", q])
        else:
            domain.append(["is_company", "=", True])
        records = await odoo.search_read(
            "res.partner", domain, ["id", "name", "email", "phone"], limit=30
        )
        return records
    except Exception as e:
        logger.error("Odoo partner list failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Odoo error: {e}")
