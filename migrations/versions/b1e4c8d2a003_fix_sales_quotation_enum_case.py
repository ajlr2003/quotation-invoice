"""fix sales_quotation_status enum uppercase values

Revision ID: b1e4c8d2a003
Revises: fa3c9d12e001, 9ce3eafcf9a8
Create Date: 2026-04-27 10:00:00.000000

The original enum was created with uppercase values ('DRAFT', 'SENT').
The fa3c9d12e001 migration added lowercase values ('accepted', 'rejected',
'converted'). SQLAlchemy maps enum members by NAME (uppercase), so writing
ACCEPTED fails because only lowercase 'accepted' exists.

This migration adds the uppercase variants so SQLAlchemy can write them.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "b1e4c8d2a003"
down_revision: Union[str, tuple] = ("fa3c9d12e001", "9ce3eafcf9a8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE sales_quotation_status ADD VALUE IF NOT EXISTS 'ACCEPTED'")
    op.execute("ALTER TYPE sales_quotation_status ADD VALUE IF NOT EXISTS 'REJECTED'")
    op.execute("ALTER TYPE sales_quotation_status ADD VALUE IF NOT EXISTS 'CONVERTED'")


def downgrade() -> None:
    pass
