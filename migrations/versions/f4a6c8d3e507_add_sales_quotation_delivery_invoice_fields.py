"""add_sales_quotation_delivery_invoice_fields

Adds delivery_date, invoice_address, and delivery_address columns to
sales_quotations. These fields are captured in the Quotation Builder UI
(header.deliveryDate, customer.invoiceAddress, customer.deliveryAddress)
but were previously silently dropped since no matching column existed.

Revision ID: f4a6c8d3e507
Revises: d3f7a9b1c204
Create Date: 2026-07-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a6c8d3e507"
down_revision: Union[str, Sequence[str], None] = "d3f7a9b1c204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sales_quotations", sa.Column("delivery_date", sa.Date(), nullable=True))
    op.add_column("sales_quotations", sa.Column("invoice_address", sa.Text(), nullable=True))
    op.add_column("sales_quotations", sa.Column("delivery_address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_quotations", "delivery_address")
    op.drop_column("sales_quotations", "invoice_address")
    op.drop_column("sales_quotations", "delivery_date")
