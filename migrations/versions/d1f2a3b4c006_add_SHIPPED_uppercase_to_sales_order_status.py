"""add SHIPPED uppercase to sales_order_status enum

Revision ID: d1f2a3b4c006
Revises: d1f2a3b4c005
Create Date: 2026-04-29 12:00:00.000000

Context:
  SQLAlchemy writes enum member NAMES (uppercase) to PostgreSQL.
  The existing DB enum uses uppercase values (CONFIRMED, DELIVERED, etc.)
  but migration d1f2a3b4c005 added lowercase 'shipped'.
  This migration adds the uppercase 'SHIPPED' that SQLAlchemy actually writes.
"""
from typing import Union

from alembic import op

revision: str = "d1f2a3b4c006"
down_revision: Union[str, None] = "d1f2a3b4c005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE sales_order_status ADD VALUE IF NOT EXISTS 'SHIPPED'")


def downgrade() -> None:
    pass  # PostgreSQL cannot remove enum values without recreating the type
