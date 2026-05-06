# =============================================================================
# app/services/__init__.py
# -----------------------------------------------------------------------------
# Convenience re-exports for all service modules so routers can do:
#
#     from app.services import auth_service, rfq_service, ...
#
# All service modules are surfaced here.
# =============================================================================

from app.services import auth_service, supplier_service, rfq_service, supplier_quotation_service, purchase_order_service, grn_service, purchase_invoice_service, sales_quotation_service, sales_order_service

__all__ = ["auth_service", "supplier_service", "rfq_service", "supplier_quotation_service", "purchase_order_service", "grn_service", "purchase_invoice_service", "sales_quotation_service", "sales_order_service"]
