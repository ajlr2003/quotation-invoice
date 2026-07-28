# =============================================================================
# migrations/versions/e7d99d0d4e78_sales_quotation_rfq_link_and_crm_.py
# -----------------------------------------------------------------------------
# Adds:
#   - sales_quotations.rfq_id       — links a quotation back to its RFQ so the
#                                      quote number can be derived as "QT" +
#                                      rfq_number.
#   - sales_quotations.created_by_id / approved_by_id / approved_at — simple
#                                      "who made it / who signed off" stamps.
#   - crm_leads.rfq_number / customer_reference — denormalised RFQ reference
#                                      numbers surfaced on the CRM lead card.
# =============================================================================

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = 'e7d99d0d4e78'
down_revision: Union[str, Sequence[str], None] = 'b597a51c7897'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sales_quotations', sa.Column('rfq_id', PG_UUID(as_uuid=True), nullable=True))
    op.add_column('sales_quotations', sa.Column('created_by_id', PG_UUID(as_uuid=True), nullable=True))
    op.add_column('sales_quotations', sa.Column('approved_by_id', PG_UUID(as_uuid=True), nullable=True))
    op.add_column('sales_quotations', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_sales_quotations_rfq_id', 'sales_quotations', ['rfq_id'])
    op.create_index('ix_sales_quotations_created_by_id', 'sales_quotations', ['created_by_id'])
    op.create_index('ix_sales_quotations_approved_by_id', 'sales_quotations', ['approved_by_id'])
    op.create_foreign_key(
        'fk_sales_quotations_rfq_id', 'sales_quotations', 'rfqs',
        ['rfq_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_sales_quotations_created_by_id', 'sales_quotations', 'users',
        ['created_by_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_sales_quotations_approved_by_id', 'sales_quotations', 'users',
        ['approved_by_id'], ['id'], ondelete='SET NULL',
    )

    op.add_column('crm_leads', sa.Column('rfq_number', sa.String(length=50), nullable=True))
    op.add_column('crm_leads', sa.Column('customer_reference', sa.String(length=100), nullable=True))
    op.create_index('ix_crm_leads_rfq_number', 'crm_leads', ['rfq_number'])


def downgrade() -> None:
    op.drop_index('ix_crm_leads_rfq_number', table_name='crm_leads')
    op.drop_column('crm_leads', 'customer_reference')
    op.drop_column('crm_leads', 'rfq_number')

    op.drop_constraint('fk_sales_quotations_approved_by_id', 'sales_quotations', type_='foreignkey')
    op.drop_constraint('fk_sales_quotations_created_by_id', 'sales_quotations', type_='foreignkey')
    op.drop_constraint('fk_sales_quotations_rfq_id', 'sales_quotations', type_='foreignkey')
    op.drop_index('ix_sales_quotations_approved_by_id', table_name='sales_quotations')
    op.drop_index('ix_sales_quotations_created_by_id', table_name='sales_quotations')
    op.drop_index('ix_sales_quotations_rfq_id', table_name='sales_quotations')
    op.drop_column('sales_quotations', 'approved_at')
    op.drop_column('sales_quotations', 'approved_by_id')
    op.drop_column('sales_quotations', 'created_by_id')
    op.drop_column('sales_quotations', 'rfq_id')
