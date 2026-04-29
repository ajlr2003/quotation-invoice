"""add shipped to sales_order_status enum

Revision ID: d1f2a3b4c005
Revises: c9d1f3a5e007
Create Date: 2026-04-29 00:00:00.000000

Adds:
  - 'shipped' value to sales_order_status PostgreSQL enum
"""
from typing import Union

from alembic import op

revision: str = "d1f2a3b4c005"
down_revision: Union[str, None] = "c9d1f3a5e007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE sales_order_status ADD VALUE IF NOT EXISTS 'shipped'")


def downgrade() -> None:
    pass  # PostgreSQL cannot remove enum values without recreating the type
