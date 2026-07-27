"""add_image_url_to_stock_items

Adds an optional image_url column to stock_items so the Products page can
attach a photo (stored via the existing /api/v1/documents/upload endpoint;
this column just holds the resulting download path).

Revision ID: d3f7a9b1c204
Revises: c8e2a1f4b7d3
Create Date: 2026-07-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3f7a9b1c204"
down_revision: Union[str, Sequence[str], None] = "c8e2a1f4b7d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stock_items",
        sa.Column("image_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stock_items", "image_url")
