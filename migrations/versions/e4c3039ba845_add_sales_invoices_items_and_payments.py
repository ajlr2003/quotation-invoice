"""add sales invoices, items and payments

NB: autogenerate also proposed dropping sales_quotations.payment_status —
that column is pre-existing model/DB drift unrelated to this change and is
still read by the app, so it is deliberately left alone.

Revision ID: e4c3039ba845
Revises: e78de05885d0
Create Date: 2026-09-20 13:04:36.879832

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4c3039ba845'
down_revision: Union[str, Sequence[str], None] = 'e78de05885d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Timeline entries for invoices (postgres enum labels use the member NAME).
    op.execute("ALTER TYPE activity_entity_type ADD VALUE IF NOT EXISTS 'SALES_INVOICE'")

    op.create_table('sales_invoices',
    sa.Column('invoice_number', sa.String(length=50), nullable=True),
    sa.Column('sales_order_id', sa.UUID(), nullable=True),
    sa.Column('customer_name', sa.String(length=255), nullable=False),
    sa.Column('customer_building_no', sa.String(length=100), nullable=True),
    sa.Column('customer_street', sa.String(length=255), nullable=True),
    sa.Column('customer_district', sa.String(length=255), nullable=True),
    sa.Column('customer_city', sa.String(length=255), nullable=True),
    sa.Column('customer_country', sa.String(length=100), nullable=True),
    sa.Column('customer_postal_code', sa.String(length=20), nullable=True),
    sa.Column('customer_tax_id', sa.String(length=100), nullable=True),
    sa.Column('customer_cr_no', sa.String(length=100), nullable=True),
    sa.Column('delivery_note_no', sa.String(length=255), nullable=True),
    sa.Column('delivery_date', sa.Date(), nullable=True),
    sa.Column('your_ref', sa.String(length=255), nullable=True),
    sa.Column('vendor_number', sa.String(length=100), nullable=True),
    sa.Column('internal_reference', sa.String(length=100), nullable=True),
    sa.Column('gr_ses', sa.String(length=100), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=14, scale=6), nullable=False),
    sa.Column('invoice_date', sa.Date(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('payment_terms', sa.String(length=255), nullable=True),
    sa.Column('vat_rate', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('discount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('vat', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('amount_paid', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('DRAFT', 'POSTED', 'PAID', 'CANCELLED', name='sales_invoice_status'), nullable=False),
    sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('posted_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['posted_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sales_order_id'], ['sales_orders.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sales_invoices_created_by_id'), 'sales_invoices', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_sales_invoices_customer_name'), 'sales_invoices', ['customer_name'], unique=False)
    op.create_index(op.f('ix_sales_invoices_due_date'), 'sales_invoices', ['due_date'], unique=False)
    op.create_index(op.f('ix_sales_invoices_id'), 'sales_invoices', ['id'], unique=False)
    op.create_index(op.f('ix_sales_invoices_invoice_number'), 'sales_invoices', ['invoice_number'], unique=True)
    op.create_index(op.f('ix_sales_invoices_sales_order_id'), 'sales_invoices', ['sales_order_id'], unique=False)
    op.create_index(op.f('ix_sales_invoices_status'), 'sales_invoices', ['status'], unique=False)
    op.create_table('sales_invoice_items',
    sa.Column('invoice_id', sa.Uuid(), nullable=False),
    sa.Column('line_no', sa.Integer(), nullable=False),
    sa.Column('catalog_no', sa.String(length=100), nullable=True),
    sa.Column('item_name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('qty', sa.Numeric(precision=14, scale=4), nullable=False),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=14, scale=4), nullable=False),
    sa.Column('discount', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('net_price', sa.Numeric(precision=14, scale=4), nullable=False),
    sa.Column('total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['sales_invoices.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sales_invoice_items_id'), 'sales_invoice_items', ['id'], unique=False)
    op.create_index(op.f('ix_sales_invoice_items_invoice_id'), 'sales_invoice_items', ['invoice_id'], unique=False)
    op.create_table('sales_invoice_payments',
    sa.Column('invoice_id', sa.Uuid(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=False),
    sa.Column('method', sa.String(length=30), nullable=False),
    sa.Column('reference', sa.String(length=100), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('recorded_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['sales_invoices.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recorded_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sales_invoice_payments_id'), 'sales_invoice_payments', ['id'], unique=False)
    op.create_index(op.f('ix_sales_invoice_payments_invoice_id'), 'sales_invoice_payments', ['invoice_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sales_invoice_payments_invoice_id'), table_name='sales_invoice_payments')
    op.drop_index(op.f('ix_sales_invoice_payments_id'), table_name='sales_invoice_payments')
    op.drop_table('sales_invoice_payments')
    op.drop_index(op.f('ix_sales_invoice_items_invoice_id'), table_name='sales_invoice_items')
    op.drop_index(op.f('ix_sales_invoice_items_id'), table_name='sales_invoice_items')
    op.drop_table('sales_invoice_items')
    op.drop_index(op.f('ix_sales_invoices_status'), table_name='sales_invoices')
    op.drop_index(op.f('ix_sales_invoices_sales_order_id'), table_name='sales_invoices')
    op.drop_index(op.f('ix_sales_invoices_invoice_number'), table_name='sales_invoices')
    op.drop_index(op.f('ix_sales_invoices_id'), table_name='sales_invoices')
    op.drop_index(op.f('ix_sales_invoices_due_date'), table_name='sales_invoices')
    op.drop_index(op.f('ix_sales_invoices_customer_name'), table_name='sales_invoices')
    op.drop_index(op.f('ix_sales_invoices_created_by_id'), table_name='sales_invoices')
    op.drop_table('sales_invoices')
    op.execute('DROP TYPE IF EXISTS sales_invoice_status')
    # NB: 'SALES_INVOICE' stays in activity_entity_type — postgres can't drop enum values.
