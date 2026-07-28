"""sales_quotation_full_workflow

Revision ID: fa3c9d12e001
Revises: 155f47726edf
Create Date: 2026-04-23 12:00:00.000000

Adds:
  - sales_quotations.sent_at column
  - sales_quotation_status enum: accepted, rejected, converted values
  - sales_order_status enum + sales_orders table
  - sales_order_items table
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "fa3c9d12e001"
down_revision: Union[str, None] = "155f47726edf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Extend sales_quotation_status enum ──────────────────────────────
    op.execute("ALTER TYPE sales_quotation_status ADD VALUE IF NOT EXISTS 'accepted'")
    op.execute("ALTER TYPE sales_quotation_status ADD VALUE IF NOT EXISTS 'rejected'")
    op.execute("ALTER TYPE sales_quotation_status ADD VALUE IF NOT EXISTS 'converted'")

    bind = op.get_bind()
    inspector = sa_inspect(bind)

    # ── 2. Add sent_at to sales_quotations (skip if already exists) ───────
    existing_cols = [c["name"] for c in inspector.get_columns("sales_quotations")]
    if "sent_at" not in existing_cols:
        op.add_column(
            "sales_quotations",
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ── 3. Create sales_order_status enum ────────────────────────────────
    sa.Enum(
        "confirmed", "in_progress", "delivered", "cancelled",
        name="sales_order_status",
    ).create(bind, checkfirst=True)

    existing_tables = inspector.get_table_names()

    # ── 4. Create sales_orders table (skip if already exists) ────────────
    if "sales_orders" not in existing_tables:
        op.create_table(
            "sales_orders",
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
            sa.Column("order_number", sa.String(50), unique=True, nullable=False, index=True),
            sa.Column("quotation_id", sa.UUID(), sa.ForeignKey("sales_quotations.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("customer_name", sa.String(255), nullable=True),
            sa.Column("department", sa.String(255), nullable=True),
            sa.Column("contact_person", sa.String(255), nullable=True),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("subject", sa.String(500), nullable=True),
            sa.Column("currency", sa.String(3), nullable=False, server_default="SAR"),
            sa.Column("payment_terms", sa.String(255), nullable=True),
            sa.Column("delivery_location", sa.String(255), nullable=True),
            sa.Column("subtotal", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("vat", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("status", sa.Enum("confirmed", "in_progress", "delivered", "cancelled", name="sales_order_status"), nullable=False, server_default="confirmed"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )

    # ── 5. Create sales_order_items table (skip if already exists) ────────
    if "sales_order_items" not in existing_tables:
        op.create_table(
            "sales_order_items",
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
            sa.Column("order_id", sa.UUID(), sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("line_no", sa.Integer(), nullable=False),
            sa.Column("catalog_no", sa.String(100), nullable=True),
            sa.Column("item_name", sa.String(255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("qty", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("unit", sa.String(20), nullable=False, server_default="EA"),
            sa.Column("unit_price", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("discount", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("net_price", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("sales_order_items")
    op.drop_table("sales_orders")
    op.drop_column("sales_quotations", "sent_at")
    # Note: removing enum values from PostgreSQL requires recreating the type
    # For safety, the downgrade leaves the enum values intact
