"""add contracts and contract milestones

NB: autogenerate also proposed dropping sales_quotations.payment_status —
that column is pre-existing model/DB drift unrelated to this change and is
still read by the app, so it is deliberately left alone (same as in the
sales_invoice migrations before this one).

Revision ID: 61d0a4daf37a
Revises: b0134500c151
Create Date: 2026-09-28 01:53:34.143574

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '61d0a4daf37a'
down_revision: Union[str, Sequence[str], None] = 'b0134500c151'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Timeline entries for contracts (postgres enum labels use the member NAME).
    op.execute("ALTER TYPE activity_entity_type ADD VALUE IF NOT EXISTS 'CONTRACT'")

    op.create_table('contracts',
    sa.Column('file_ref', sa.String(length=100), nullable=False),
    sa.Column('customer', sa.String(length=255), nullable=False),
    sa.Column('po_number', sa.String(length=100), nullable=True),
    sa.Column('po_value', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('po_date', sa.Date(), nullable=True),
    sa.Column('po_expiry_date', sa.Date(), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('contract_value', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('risk', sa.Enum('ON_TRACK', 'AT_RISK', 'DELAYED', name='contract_risk_status'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contracts_customer'), 'contracts', ['customer'], unique=False)
    op.create_index(op.f('ix_contracts_file_ref'), 'contracts', ['file_ref'], unique=False)
    op.create_index(op.f('ix_contracts_id'), 'contracts', ['id'], unique=False)
    op.create_table('contract_milestones',
    sa.Column('contract_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('pct', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('status', sa.Enum('PENDING', 'INVOICED', 'RECEIVED', 'OVERDUE', name='contract_milestone_status'), nullable=False),
    sa.Column('planned_date', sa.Date(), nullable=True),
    sa.Column('achieved_date', sa.Date(), nullable=True),
    sa.Column('invoice_number', sa.String(length=100), nullable=True),
    sa.Column('invoice_date', sa.Date(), nullable=True),
    sa.Column('received_date', sa.Date(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contract_milestones_contract_id'), 'contract_milestones', ['contract_id'], unique=False)
    op.create_index(op.f('ix_contract_milestones_id'), 'contract_milestones', ['id'], unique=False)
    op.create_index(op.f('ix_contract_milestones_status'), 'contract_milestones', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_contract_milestones_status'), table_name='contract_milestones')
    op.drop_index(op.f('ix_contract_milestones_id'), table_name='contract_milestones')
    op.drop_index(op.f('ix_contract_milestones_contract_id'), table_name='contract_milestones')
    op.drop_table('contract_milestones')
    op.drop_index(op.f('ix_contracts_id'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_file_ref'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_customer'), table_name='contracts')
    op.drop_table('contracts')
    op.execute("DROP TYPE IF EXISTS contract_risk_status")
    op.execute("DROP TYPE IF EXISTS contract_milestone_status")
    # NB: 'CONTRACT' stays in activity_entity_type — postgres can't drop enum values.
