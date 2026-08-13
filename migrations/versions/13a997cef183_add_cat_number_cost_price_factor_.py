"""add cat_number, cost, price_factor, currency to stock_items

Revision ID: 13a997cef183
Revises: 3f16c66f636b
Create Date: 2026-08-13 10:39:03.086044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13a997cef183'
down_revision: Union[str, Sequence[str], None] = '3f16c66f636b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('stock_items', sa.Column('cat_number', sa.String(length=200), nullable=True))
    op.add_column('stock_items', sa.Column('cost', sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column('stock_items', sa.Column('price_factor', sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column('stock_items', sa.Column('currency', sa.String(length=10), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('stock_items', 'currency')
    op.drop_column('stock_items', 'price_factor')
    op.drop_column('stock_items', 'cost')
    op.drop_column('stock_items', 'cat_number')
