# =============================================================================
# app/models/__init__.py
# -----------------------------------------------------------------------------
# Re-exports every ORM model so the application can import them from a
# single location. All models must be registered here so SQLAlchemy
# discovers them before ``Base.metadata.create_all()`` is called.
# =============================================================================

from app.models.base import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ActivityEntityType,
    ApprovalEntityType,
    ApprovalStatus,
    CrmLeadStage,
    DocumentEntityType,
    DocumentType,
    PurchaseOrderStatus,
    QuotationStatus,
    RFQStatus,
    SalesOrderStatus,
    SalesQuotationStatus,
    SupplierQuoteStatus,
    UserRole,
)

from app.models.account import Account, AccountType
from app.models.journal_entry import JournalEntry, JournalEntryStatus
from app.models.bank_account import BankAccount, BankAccountType
from app.models.bank_transaction import BankTransaction
from app.models.closed_period import ClosedPeriod
from app.models.user import User
from app.models.customer import Customer
from app.models.supplier import Supplier
from app.models.rfq import RFQ
from app.models.rfq_item import RFQItem
from app.models.supplier_quote import SupplierQuote
from app.models.supplier_quotation import SupplierQuotation
from app.models.supplier_quotation_item import SupplierQuotationItem
from app.models.quotation import Quotation
from app.models.quotation_item import QuotationItem
from app.models.approval import Approval
from app.models.document import Document
from app.models.purchase_order import PurchaseOrder
from app.models.grn import GRN
from app.models.purchase_invoice import PurchaseInvoice
from app.models.sales_quotation import SalesQuotation
from app.models.sales_quotation_item import SalesQuotationItem
from app.models.sales_order import SalesOrder
from app.models.sales_order_item import SalesOrderItem
from app.models.crm_lead import CrmLead
from app.models.payment import Payment
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.project_milestone import ProjectMilestone
from app.models.time_log import TimeLog
from app.models.stock_item import StockItem
from app.models.stock_movement import StockMovement
from app.models.expense import Expense
from app.models.activity_log import ActivityLog
from app.models.vendor_pricelist import VendorPricelist
from app.models.discount_rule import DiscountRule

__all__ = [
    # Mixins
    "AuditMixin", "TimestampMixin", "UUIDPrimaryKeyMixin",
    # Enums
    "UserRole", "RFQStatus", "SupplierQuoteStatus",
    "QuotationStatus", "ApprovalStatus", "ApprovalEntityType",
    "DocumentEntityType", "DocumentType", "PurchaseOrderStatus",
    "SalesQuotationStatus", "SalesOrderStatus", "ActivityEntityType",
    # Models
    "User", "Customer", "Supplier",
    "RFQ", "RFQItem", "SupplierQuote", "SupplierQuotation", "SupplierQuotationItem",
    "Quotation", "QuotationItem",
    "Approval", "Document",
    "PurchaseOrder",
    "GRN",
    "PurchaseInvoice",
    "SalesQuotation",
    "SalesQuotationItem",
    "SalesOrder",
    "SalesOrderItem",
    "Account", "AccountType",
    "JournalEntry", "JournalEntryStatus",
    "BankAccount", "BankAccountType",
    "BankTransaction",
    "ClosedPeriod",
    "CrmLead", "CrmLeadStage",
    "Payment",
    "Project", "ProjectTask", "ProjectMilestone", "TimeLog",
    "StockItem", "StockMovement",
    "Expense",
    "ActivityLog",
    "VendorPricelist",
]
