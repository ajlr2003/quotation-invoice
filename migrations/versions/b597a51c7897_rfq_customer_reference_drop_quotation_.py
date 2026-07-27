# =============================================================================
# migrations/versions/b597a51c7897_rfq_customer_reference_drop_quotation_.py
# -----------------------------------------------------------------------------
# Adds RFQ.customer_reference (the customer's own reference number, e.g. from
# SAP Ariba or email) and drops the free-text quotation_number columns on
# supplier_quotations / supplier_quotation_items — traceability for supplier
# bids is carried by the existing rfq_id foreign key instead.
# =============================================================================

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b597a51c7897'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rfqs', sa.Column('customer_reference', sa.String(length=100), nullable=True))
    op.drop_column('supplier_quotations', 'quotation_number')
    op.drop_column('supplier_quotation_items', 'quotation_number')


def downgrade() -> None:
    op.add_column('supplier_quotation_items', sa.Column('quotation_number', sa.String(length=50), nullable=True))
    op.add_column('supplier_quotations', sa.Column('quotation_number', sa.String(length=50), nullable=True))
    op.drop_column('rfqs', 'customer_reference')
