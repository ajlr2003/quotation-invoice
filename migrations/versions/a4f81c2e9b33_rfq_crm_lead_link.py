# =============================================================================
# migrations/versions/a4f81c2e9b33_rfq_crm_lead_link.py
# -----------------------------------------------------------------------------
# Adds rfqs.crm_lead_id — links an RFQ directly back to the CRM lead it was
# raised for. A single lead's items are often split across multiple supplier
# RFQs, so this lets the lead screen show every RFQ raised for that customer
# in one place, and lets a new RFQ inherit the customer's own reference
# number from the lead instead of requiring re-entry each time.
# =============================================================================

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = 'a4f81c2e9b33'
down_revision: Union[str, Sequence[str], None] = 'e7d99d0d4e78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rfqs', sa.Column('crm_lead_id', PG_UUID(as_uuid=True), nullable=True))
    op.create_index('ix_rfqs_crm_lead_id', 'rfqs', ['crm_lead_id'])
    op.create_foreign_key(
        'fk_rfqs_crm_lead_id', 'rfqs', 'crm_leads',
        ['crm_lead_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_rfqs_crm_lead_id', 'rfqs', type_='foreignkey')
    op.drop_index('ix_rfqs_crm_lead_id', table_name='rfqs')
    op.drop_column('rfqs', 'crm_lead_id')
