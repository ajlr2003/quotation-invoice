# =============================================================================
# migrations/versions/c8e2a1f4b7d3_add_activity_logs_table.py
# -----------------------------------------------------------------------------
# Adds the activity_logs table — a generic "who did what, when" timeline
# attached to any entity via entity_type/entity_id, same pattern as the
# existing Document/Approval generic joins. Powers the chatter-style
# activity feed on RFQ, Supplier, Sales Quotation, and CRM Lead detail views.
# =============================================================================

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = 'c8e2a1f4b7d3'
down_revision: Union[str, Sequence[str], None] = 'a4f81c2e9b33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVITY_ENTITY_TYPE = sa.Enum(
    'rfq', 'supplier', 'sales_quotation', 'crm_lead',
    name='activity_entity_type',
)


def upgrade() -> None:
    _ACTIVITY_ENTITY_TYPE.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'activity_logs',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('entity_type', _ACTIVITY_ENTITY_TYPE, nullable=False),
        sa.Column('entity_id', PG_UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('user_id', PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_index('ix_activity_logs_entity_type', 'activity_logs', ['entity_type'])
    op.create_index('ix_activity_logs_entity_id', 'activity_logs', ['entity_id'])
    op.create_index('ix_activity_logs_user_id', 'activity_logs', ['user_id'])
    op.create_index('ix_activity_logs_id', 'activity_logs', ['id'])
    op.create_foreign_key(
        'activity_logs_user_id_fkey', 'activity_logs', 'users',
        ['user_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_table('activity_logs')
    _ACTIVITY_ENTITY_TYPE.drop(op.get_bind(), checkfirst=True)
