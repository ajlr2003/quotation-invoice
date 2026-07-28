"""fix_draft_sent_enum_lowercase

Revision ID: c9d1f3a5e007
Revises: b1e4c8d2a003
Create Date: 2026-04-27 11:00:00.000000

The DB sales_quotation_status enum was originally created with uppercase
'DRAFT' and 'SENT'. Python's SalesQuotationStatus str-enum has lowercase
values ("draft", "sent"), so every flush writing DRAFT/SENT status fails
with "invalid input value for enum" and silently rolls back.

This migration adds the missing lowercase variants so the Python values
match what PostgreSQL accepts.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "c9d1f3a5e007"
down_revision: Union[str, None] = "b1e4c8d2a003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE sales_quotation_status ADD VALUE IF NOT EXISTS 'draft'")
    op.execute("ALTER TYPE sales_quotation_status ADD VALUE IF NOT EXISTS 'sent'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
