"""rename_supplier_quotations_price_to_unit_price

Revision ID: c6e105c69eb2
Revises: 155f47726edf
Create Date: 2026-04-22 09:41:44.912784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6e105c69eb2'
down_revision: Union[str, Sequence[str], None] = '155f47726edf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("supplier_quotations", "price", new_column_name="unit_price")


def downgrade() -> None:
    op.alter_column("supplier_quotations", "unit_price", new_column_name="price")
