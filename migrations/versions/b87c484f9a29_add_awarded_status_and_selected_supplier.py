"""add_awarded_status_and_selected_supplier

Revision ID: b87c484f9a29
Revises: 84713547c192
Create Date: 2026-04-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b87c484f9a29'
down_revision: Union[str, Sequence[str], None] = '84713547c192'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add AWARDED to the rfq_status enum if not already present.
    # ADD VALUE must run outside a transaction block in PostgreSQL.
    existing = [r[0] for r in conn.execute(
        sa.text("SELECT enumlabel FROM pg_enum "
                "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                "WHERE pg_type.typname = 'rfq_status'")
    )]
    if 'AWARDED' not in existing:
        op.execute("COMMIT")
        op.execute("ALTER TYPE rfq_status ADD VALUE 'AWARDED' AFTER 'EVALUATED'")
        op.execute("BEGIN")

    # Add selected_supplier_id column if not already present (may exist via create_all).
    cols = [r[0] for r in conn.execute(
        sa.text("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'rfqs'")
    )]
    if 'selected_supplier_id' not in cols:
        op.add_column('rfqs', sa.Column('selected_supplier_id', sa.Uuid(), nullable=True))
        op.create_foreign_key(
            'fk_rfqs_selected_supplier_id',
            'rfqs', 'suppliers',
            ['selected_supplier_id'], ['id'],
            ondelete='SET NULL',
        )
        op.create_index(
            'ix_rfqs_selected_supplier_id', 'rfqs', ['selected_supplier_id'], unique=False,
        )


def downgrade() -> None:
    op.drop_index('ix_rfqs_selected_supplier_id', table_name='rfqs')
    op.drop_constraint('fk_rfqs_selected_supplier_id', 'rfqs', type_='foreignkey')
    op.drop_column('rfqs', 'selected_supplier_id')
    # PostgreSQL does not support removing enum values natively.
