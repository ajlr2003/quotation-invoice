"""merge_purchase_invoices_and_total_price

Revision ID: 155f47726edf
Revises: a07907083d85, e1c3f9a82b05
Create Date: 2026-04-22 09:24:47.390331

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '155f47726edf'
down_revision: Union[str, Sequence[str], None] = ('a07907083d85', 'e1c3f9a82b05')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
