"""
All application-wide enumerations.
Centralised here so models and schemas can import from a single source.
"""
import enum


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    ADMIN       = "admin"
    MANAGER     = "manager"
    PURCHASER   = "purchaser"
    FINANCE     = "finance"
    VIEWER      = "viewer"


# ---------------------------------------------------------------------------
# RFQ (Request for Quotation)
# ---------------------------------------------------------------------------

class RFQStatus(str, enum.Enum):
    DRAFT       = "draft"
    SENT        = "sent"           # sent to suppliers
    RECEIVED    = "received"       # at least one supplier quote received
    EVALUATED   = "evaluated"      # quotes compared, winner selected
    CLOSED      = "closed"
    CANCELLED   = "cancelled"


# ---------------------------------------------------------------------------
# Supplier Quote
# ---------------------------------------------------------------------------

class SupplierQuoteStatus(str, enum.Enum):
    PENDING     = "pending"
    RECEIVED    = "received"
    ACCEPTED    = "accepted"
    REJECTED    = "rejected"


# ---------------------------------------------------------------------------
# Quotation (sent TO customers)
# ---------------------------------------------------------------------------

class QuotationStatus(str, enum.Enum):
    DRAFT           = "draft"
    PENDING_APPROVAL= "pending_approval"
    APPROVED        = "approved"
    SENT            = "sent"           # sent to customer
    ACCEPTED        = "accepted"       # customer accepted
    REJECTED        = "rejected"       # customer rejected
    EXPIRED         = "expired"
    CONVERTED       = "converted"      # converted to invoice


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

class ApprovalStatus(str, enum.Enum):
    PENDING     = "pending"
    APPROVED    = "approved"
    REJECTED    = "rejected"


class ApprovalEntityType(str, enum.Enum):
    QUOTATION   = "quotation"
    INVOICE     = "invoice"


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class DocumentEntityType(str, enum.Enum):
    RFQ         = "rfq"
    QUOTATION   = "quotation"
    INVOICE     = "invoice"
    SUPPLIER_QUOTE = "supplier_quote"


class DocumentType(str, enum.Enum):
    PDF         = "pdf"
    EXCEL       = "excel"
    WORD        = "word"
    IMAGE       = "image"
    OTHER       = "other"
