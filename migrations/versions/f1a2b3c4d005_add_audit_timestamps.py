"""add audit timestamps to sales_quotations and sales_orders

Revision ID: f1a2b3c4d005
Revises: fa3c9d12e001
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d005'
down_revision = ('fa3c9d12e001', 'd1f2a3b4c006')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sales_quotations', sa.Column('accepted_at',  sa.DateTime(timezone=True), nullable=True))
    op.add_column('sales_quotations', sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sales_quotations', sa.Column('updated_by',   sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))

    op.add_column('sales_orders', sa.Column('shipped_at',   sa.DateTime(timezone=True), nullable=True))
    op.add_column('sales_orders', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sales_orders', sa.Column('updated_by',   sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column('sales_quotations', 'updated_by')
    op.drop_column('sales_quotations', 'converted_at')
    op.drop_column('sales_quotations', 'accepted_at')

    op.drop_column('sales_orders', 'updated_by')
    op.drop_column('sales_orders', 'delivered_at')
    op.drop_column('sales_orders', 'shipped_at')
