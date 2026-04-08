"""
app/models/__init__.py
======================
Re-exports every ORM model so the rest of the application can do:

    from app.models import User, Customer, RFQ, ...

IMPORTANT: models must be imported here so SQLAlchemy's mapper registry
           discovers them before `Base.metadata.create_all()` is called.
"""

from app.models.base import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ApprovalEntityType,
    ApprovalStatus,
    DocumentEntityType,
    DocumentType,
    PurchaseOrderStatus,
    QuotationStatus,
    RFQStatus,
    SupplierQuoteStatus,
    UserRole,
)

from app.models.user import User
from app.models.customer import Customer
from app.models.supplier import Supplier
from app.models.rfq import RFQ
from app.models.rfq_item import RFQItem
from app.models.supplier_quote import SupplierQuote
from app.models.supplier_quotation import SupplierQuotation
from app.models.quotation import Quotation
from app.models.quotation_item import QuotationItem
from app.models.approval import Approval
from app.models.document import Document
from app.models.purchase_order import PurchaseOrder

__all__ = [
    # Mixins
    "AuditMixin", "TimestampMixin", "UUIDPrimaryKeyMixin",
    # Enums
    "UserRole", "RFQStatus", "SupplierQuoteStatus",
    "QuotationStatus", "ApprovalStatus", "ApprovalEntityType",
    "DocumentEntityType", "DocumentType", "PurchaseOrderStatus",
    # Models
    "User", "Customer", "Supplier",
    "RFQ", "RFQItem", "SupplierQuote", "SupplierQuotation",
    "Quotation", "QuotationItem",
    "Approval", "Document",
    "PurchaseOrder",
]
