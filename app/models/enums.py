# =============================================================================
# app/models/enums.py
# -----------------------------------------------------------------------------
# Centralised definition of all application-wide enumerations. Both ORM models
# and Pydantic schemas import from this single module so that enum values are
# never duplicated across the codebase.  All enums inherit from ``str`` so
# that their values serialise directly to JSON strings.
# =============================================================================

from __future__ import annotations

import enum


# ── User ──────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    """Roles that can be assigned to system user accounts.

    Controls which routes and actions each user is permitted to access via the
    ``require_roles`` dependency in ``app/middleware/auth.py``.
    """
    ADMIN     = "admin"
    MANAGER   = "manager"
    SALES     = "sales"
    PURCHASER = "purchaser"
    FINANCE   = "finance"
    VIEWER    = "viewer"


# ── RFQ (Request for Quotation) ───────────────────────────────────────────────

class RFQStatus(str, enum.Enum):
    """Lifecycle states for a Request for Quotation.

    Transitions follow a linear flow with optional cancellation at any stage:
    ``draft`` → ``sent`` → ``received`` → ``evaluated`` → ``awarded`` → ``closed``
    """
    DRAFT     = "draft"
    SENT      = "sent"        # sent to one or more suppliers
    RECEIVED  = "received"    # at least one supplier quote received
    EVALUATED = "evaluated"   # quotes compared, winner identified
    AWARDED   = "awarded"     # supplier selected / contract awarded
    CLOSED    = "closed"
    CANCELLED = "cancelled"


# ── Supplier Quote ────────────────────────────────────────────────────────────

class SupplierQuoteStatus(str, enum.Enum):
    """Status of a single supplier's quote on a specific RFQ line item."""
    PENDING  = "pending"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# ── Quotation (outbound to customers) ────────────────────────────────────────

class QuotationStatus(str, enum.Enum):
    """Lifecycle states for an outbound customer Quotation.

    Flow: ``draft`` → ``pending_approval`` → ``approved`` → ``sent``
          → ``accepted`` / ``rejected`` → ``converted``
    """
    DRAFT            = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED         = "approved"
    SENT             = "sent"        # sent to customer
    ACCEPTED         = "accepted"    # customer accepted
    REJECTED         = "rejected"    # customer rejected
    EXPIRED          = "expired"
    CONVERTED        = "converted"   # converted to invoice


# ── Approval ──────────────────────────────────────────────────────────────────

class ApprovalStatus(str, enum.Enum):
    """Status of a single approval step."""
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalEntityType(str, enum.Enum):
    """The type of entity that an Approval record is attached to."""
    QUOTATION = "quotation"
    INVOICE   = "invoice"


# ── Purchase Order ────────────────────────────────────────────────────────────

class PurchaseOrderStatus(str, enum.Enum):
    """Fulfillment status of a Purchase Order.

    Transitions are driven by Goods Receipt Notes (GRNs):
    ``created`` → ``partial`` (some received) → ``completed`` (all received).
    """
    CREATED      = "created"
    PARTIAL      = "partial"       # some goods received, not yet complete
    SENT         = "sent"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED    = "completed"
    CANCELLED    = "cancelled"


# ── Purchase Invoice (supplier-side, created from GRN) ───────────────────────

class PurchaseInvoiceStatus(str, enum.Enum):
    """Payment status of a supplier-side Purchase Invoice.

    Flow: ``draft`` → ``approved`` → ``paid``
    """
    DRAFT    = "draft"
    APPROVED = "approved"
    PAID     = "paid"


# ── Sales Quotation (Quotation Builder, outbound to customers) ────────────────

class SalesQuotationStatus(str, enum.Enum):
    """Lifecycle states for a Sales Quotation created via the Quotation Builder.

    Flow: ``draft`` → ``sent`` → ``accepted`` / ``rejected`` → ``converted``
    """
    DRAFT     = "draft"
    SENT      = "sent"
    ACCEPTED  = "accepted"
    REJECTED  = "rejected"
    CONVERTED = "converted"   # converted to a SalesOrder


class SalesOrderStatus(str, enum.Enum):
    """Fulfillment status for a Sales Order created from an accepted SalesQuotation.

    Flow: ``confirmed`` → ``shipped`` → ``delivered`` (or ``cancelled``)
    """
    CONFIRMED = "confirmed"
    SHIPPED   = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# ── Document ──────────────────────────────────────────────────────────────────

class DocumentEntityType(str, enum.Enum):
    """The type of business entity that a Document attachment belongs to."""
    RFQ            = "rfq"
    QUOTATION      = "quotation"
    INVOICE        = "invoice"
    SUPPLIER_QUOTE = "supplier_quote"


class DocumentType(str, enum.Enum):
    """MIME-category classification of an uploaded document."""
    PDF   = "pdf"
    EXCEL = "excel"
    WORD  = "word"
    IMAGE = "image"
    OTHER = "other"
