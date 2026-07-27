"""add_vendor_pricelists_table

Adds vendor_pricelists — per-supplier product pricing (Odoo-style Vendor
Pricelist): vendor product name/code, lead time, quantity break, unit price,
validity window, and discount %.

Revision ID: b1e4f6a9c103
Revises: a8c1e5f7d902
Create Date: 2026-07-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1e4f6a9c103"
down_revision: Union[str, Sequence[str], None] = "a8c1e5f7d902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_pricelists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vendor_product_name", sa.String(length=255), nullable=True),
        sa.Column("vendor_product_code", sa.String(length=100), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), server_default="1", nullable=False),
        sa.Column("stock_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stock_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 2), server_default="1", nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("discount_pct", sa.Numeric(5, 2), server_default="0", nullable=False),
    )
    op.create_index("ix_vendor_pricelists_supplier_id", "vendor_pricelists", ["supplier_id"])
    op.create_index("ix_vendor_pricelists_stock_item_id", "vendor_pricelists", ["stock_item_id"])


def downgrade() -> None:
    op.drop_index("ix_vendor_pricelists_stock_item_id", table_name="vendor_pricelists")
    op.drop_index("ix_vendor_pricelists_supplier_id", table_name="vendor_pricelists")
    op.drop_table("vendor_pricelists")
