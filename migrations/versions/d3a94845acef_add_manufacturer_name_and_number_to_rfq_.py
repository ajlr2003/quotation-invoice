"""add manufacturer name and number to rfq items

Revision ID: d3a94845acef
Revises: 0ab4f9067dc4
Create Date: 2026-08-02 12:18:45.022883

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3a94845acef'
down_revision: Union[str, Sequence[str], None] = '0ab4f9067dc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('rfq_items', sa.Column('manufacturer_name', sa.String(length=255), nullable=True))
    op.add_column('rfq_items', sa.Column('manufacturer_number', sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('rfq_items', 'manufacturer_number')
    op.drop_column('rfq_items', 'manufacturer_name')
