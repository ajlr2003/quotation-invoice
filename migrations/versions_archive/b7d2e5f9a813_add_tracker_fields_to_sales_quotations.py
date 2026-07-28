"""add_tracker_fields_to_sales_quotations

Adds oem, date_received, deadline, follow_up_date, and outcome columns to
sales_quotations so the Sales > Quotations page can mirror the team's
existing Excel/WhatsApp quotation tracker (Quotation No., Project/Customer,
Date Received, Deadline, Date Submitted, Status, Value, Validity, Contact,
Remarks, Follow-up/Outcome).

Revision ID: b7d2e5f9a813
Revises: f4a6c8d3e507
Create Date: 2026-07-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2e5f9a813"
down_revision: Union[str, Sequence[str], None] = "f4a6c8d3e507"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sales_quotations", sa.Column("oem", sa.String(length=200), nullable=True))
    op.add_column("sales_quotations", sa.Column("date_received", sa.Date(), nullable=True))
    op.add_column("sales_quotations", sa.Column("deadline", sa.Date(), nullable=True))
    op.add_column("sales_quotations", sa.Column("follow_up_date", sa.Date(), nullable=True))
    op.add_column("sales_quotations", sa.Column("outcome", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_quotations", "outcome")
    op.drop_column("sales_quotations", "follow_up_date")
    op.drop_column("sales_quotations", "deadline")
    op.drop_column("sales_quotations", "date_received")
    op.drop_column("sales_quotations", "oem")
