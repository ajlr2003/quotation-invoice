"""add_billable_to_projects

Adds a billable column to projects. The New Project form has always sent
this flag, but the schema/model silently dropped it (Pydantic ignores
unknown fields by default), so it never persisted.

Revision ID: a8c1e5f7d902
Revises: b7d2e5f9a813
Create Date: 2026-07-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8c1e5f7d902"
down_revision: Union[str, Sequence[str], None] = "b7d2e5f9a813"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("billable", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("projects", "billable")
