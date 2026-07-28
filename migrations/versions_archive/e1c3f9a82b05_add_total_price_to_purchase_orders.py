"""add_total_price_to_purchase_orders_and_fix_unit_price

Adds total_price column (the supplier's whole-RFQ quotation total) and
recalculates unit_price = total_price / ordered_quantity for all existing rows.

Revision ID: e1c3f9a82b05
Revises: 2fab356a3a47
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1c3f9a82b05"
down_revision: Union[str, Sequence[str], None] = "2fab356a3a47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1 — Add total_price column (nullable first so we can backfill, then make NOT NULL)
    op.add_column(
        "purchase_orders",
        sa.Column(
            "total_price",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
    )

    # 2 — Backfill total_price from supplier_quotations and recalculate unit_price.
    #
    #     Logic:
    #       total_price = supplier_quotations.price  (whole-RFQ bid)
    #       unit_price  = total_price / ordered_quantity
    #                     (or 0 when ordered_quantity is zero / no quotation found)
    #
    #     Rows where no matching quotation exists keep total_price = 0, unit_price = 0.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE purchase_orders AS po
            SET
                total_price = COALESCE(sq.price, 0),
                unit_price  = CASE
                                  WHEN po.ordered_quantity > 0 THEN
                                      COALESCE(sq.price, 0) / po.ordered_quantity
                                  ELSE 0
                              END
            FROM supplier_quotations sq
            WHERE sq.rfq_id      = po.rfq_id
              AND sq.supplier_id = po.supplier_id
            """
        )
    )


def downgrade() -> None:
    # Restore unit_price to raw quotation price (pre-fix behaviour) and drop total_price.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE purchase_orders AS po
            SET unit_price = COALESCE(sq.price, 0)
            FROM supplier_quotations sq
            WHERE sq.rfq_id      = po.rfq_id
              AND sq.supplier_id = po.supplier_id
            """
        )
    )
    op.drop_column("purchase_orders", "total_price")
