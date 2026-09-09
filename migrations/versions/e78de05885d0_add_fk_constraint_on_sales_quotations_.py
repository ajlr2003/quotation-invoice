"""add fk constraint on sales_quotations.updated_by

Revision ID: e78de05885d0
Revises: d5889e463869
Create Date: 2026-09-09 00:58:52.566563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e78de05885d0'
down_revision: Union[str, Sequence[str], None] = 'd5889e463869'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NB: autogenerate also proposed dropping 'payment_status' — that column
    # exists in the DB but isn't declared on the SalesQuotation model (it's
    # pre-existing drift, unrelated to this change, and the frontend still
    # reads it) — deliberately left alone here.
    op.create_foreign_key(None, 'sales_quotations', 'users', ['updated_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, 'sales_quotations', type_='foreignkey')
