"""backfill_po_ordered_quantity_and_unit_price

Revision ID: 9ce3eafcf9a8
Revises: c6e105c69eb2
Create Date: 2026-04-22 10:16:47.148739

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '9ce3eafcf9a8'
down_revision: Union[str, Sequence[str], None] = 'c6e105c69eb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: fill ordered_quantity from the sum of rfq_items for the PO's RFQ.
    op.execute("""
        UPDATE purchase_orders po
        SET ordered_quantity = items.qty
        FROM (
            SELECT rfq_id, SUM(quantity) AS qty
            FROM rfq_items
            GROUP BY rfq_id
        ) items
        WHERE po.rfq_id = items.rfq_id
          AND po.ordered_quantity = 0
    """)

    # Step 2: fill unit_price from supplier_quotations where it is still 0.
    op.execute("""
        UPDATE purchase_orders po
        SET unit_price = sq.unit_price
        FROM supplier_quotations sq
        WHERE sq.rfq_id = po.rfq_id
          AND sq.supplier_id = po.supplier_id
          AND po.unit_price = 0
    """)

    # Step 3: recompute total_price = unit_price × ordered_quantity for rows
    # where the old total-bid formula left an inconsistent value.
    op.execute("""
        UPDATE purchase_orders
        SET total_price = unit_price * ordered_quantity
        WHERE unit_price > 0 AND ordered_quantity > 0
    """)


def downgrade() -> None:
    # Backfill data cannot be meaningfully reversed.
    op.execute("""
        UPDATE purchase_orders
        SET ordered_quantity = 0, unit_price = 0, total_price = 0
    """)
