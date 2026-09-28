"""add customer email and contact person to sales invoices

NB: autogenerate also proposed dropping sales_quotations.payment_status —
that column is pre-existing model/DB drift unrelated to this change and is
still read by the app, so it is deliberately left alone (same as in the two
earlier sales_invoice migrations).

Revision ID: b0134500c151
Revises: e4c3039ba845
Create Date: 2026-09-27 22:52:28.941449

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0134500c151'
down_revision: Union[str, Sequence[str], None] = 'e4c3039ba845'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sales_invoices', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('sales_invoices', sa.Column('contact_person', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sales_invoices', 'contact_person')
    op.drop_column('sales_invoices', 'email')
