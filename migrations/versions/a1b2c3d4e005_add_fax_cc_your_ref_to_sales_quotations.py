"""add fax, cc, your_ref to sales_quotations

Revision ID: a1b2c3d4e005
Revises: f2b3c4d5e006
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e005'
down_revision = 'f2b3c4d5e006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sales_quotations', sa.Column('fax',      sa.String(50),  nullable=True))
    op.add_column('sales_quotations', sa.Column('cc',       sa.String(500), nullable=True))
    op.add_column('sales_quotations', sa.Column('your_ref', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('sales_quotations', 'your_ref')
    op.drop_column('sales_quotations', 'cc')
    op.drop_column('sales_quotations', 'fax')
