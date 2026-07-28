"""add_partial_to_purchase_order_status

Revision ID: a2c7ff268eb5
Revises: 507726cc506c
Create Date: 2026-04-22 09:09:36.191723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2c7ff268eb5'
down_revision: Union[str, Sequence[str], None] = '507726cc506c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'partial' value to purchase_order_status enum."""
    op.execute("ALTER TYPE purchase_order_status ADD VALUE IF NOT EXISTS 'partial'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op.
    pass
