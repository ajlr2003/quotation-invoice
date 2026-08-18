"""add customer_rfqs table and link sales quotations to it

Revision ID: d5889e463869
Revises: 13a997cef183
Create Date: 2026-08-18 10:25:16.666590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5889e463869'
down_revision: Union[str, Sequence[str], None] = '13a997cef183'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # New ActivityEntityType.CUSTOMER_RFQ member — the Postgres enum type
    # backing activity_logs.entity_type must be extended to match, since
    # SQLAlchemy stores enum *names* (not values) and autogenerate doesn't
    # detect Python enum member additions on an existing Postgres enum type.
    op.execute("ALTER TYPE activity_entity_type ADD VALUE IF NOT EXISTS 'CUSTOMER_RFQ'")

    op.create_table('customer_rfqs',
    sa.Column('customer_reference', sa.String(length=100), nullable=False),
    sa.Column('customer_name', sa.String(length=255), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=True),
    sa.Column('date_received', sa.Date(), nullable=True),
    sa.Column('subject', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'QUOTED', 'CLOSED', name='customer_rfq_status'), nullable=False),
    sa.Column('crm_lead_id', sa.UUID(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['crm_lead_id'], ['crm_leads.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_rfqs_customer_reference'), 'customer_rfqs', ['customer_reference'], unique=False)
    op.create_index(op.f('ix_customer_rfqs_id'), 'customer_rfqs', ['id'], unique=False)
    op.add_column('sales_quotations', sa.Column('customer_rfq_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_sales_quotations_customer_rfq_id'), 'sales_quotations', ['customer_rfq_id'], unique=False)
    op.create_foreign_key(None, 'sales_quotations', 'customer_rfqs', ['customer_rfq_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, 'sales_quotations', type_='foreignkey')
    op.drop_index(op.f('ix_sales_quotations_customer_rfq_id'), table_name='sales_quotations')
    op.drop_column('sales_quotations', 'customer_rfq_id')
    op.drop_index(op.f('ix_customer_rfqs_id'), table_name='customer_rfqs')
    op.drop_index(op.f('ix_customer_rfqs_customer_reference'), table_name='customer_rfqs')
    op.drop_table('customer_rfqs')
