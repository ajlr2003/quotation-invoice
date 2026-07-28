"""add sales role to user_role enum

Revision ID: f2b3c4d5e006
Revises: f1a2b3c4d005
Create Date: 2026-05-04
"""
from alembic import op

revision = 'f2b3c4d5e006'
down_revision = 'f1a2b3c4d005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'sales'")


def downgrade() -> None:
    pass  # PostgreSQL does not support removing enum values
