"""tenant operational data and import previews"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003_operations'
down_revision = '0002_identity'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('businesses', sa.Column('data_status', sa.String(16), nullable=False, server_default='empty'))
    op.create_table('customers',
    sa.Column('external_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'external_id', name='uq_customers_external'),
    sa.UniqueConstraint('business_id', 'id', name='uq_customers_tenant_id')
    )
    op.create_index(op.f('ix_customers_business_id'), 'customers', ['business_id'], unique=False)
    op.create_table('expense_coverage',
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('complete', sa.Boolean(), nullable=False),
    sa.Column('confirmed_by', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('end_date >= start_date', name='coverage_period_valid'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('business_id', 'start_date', 'end_date')
    )
    op.create_table('expenses',
    sa.Column('external_id', sa.String(length=80), nullable=False),
    sa.Column('incurred_on', sa.Date(), nullable=False),
    sa.Column('category', sa.String(length=24), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('status_reason', sa.String(length=200), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('paid','voided')", name='expense_status_valid'),
    sa.CheckConstraint('amount > 0', name='expense_positive'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'external_id', name='uq_expenses_external'),
    sa.UniqueConstraint('business_id', 'id', name='uq_expenses_tenant_id')
    )
    op.create_index('expenses_tenant_date', 'expenses', ['business_id', 'incurred_on'], unique=False)
    op.create_index(op.f('ix_expenses_business_id'), 'expenses', ['business_id'], unique=False)
    op.create_table('import_batches',
    sa.Column('resource', sa.String(length=20), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('columns', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('raw_rows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('valid_count', sa.Integer(), nullable=False),
    sa.Column('imported_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('preview','validated','committed')", name='import_status_valid'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'resource', 'content_hash', name='uq_import_content')
    )
    op.create_index(op.f('ix_import_batches_business_id'), 'import_batches', ['business_id'], unique=False)
    op.create_table('suppliers',
    sa.Column('external_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'external_id', name='uq_suppliers_external'),
    sa.UniqueConstraint('business_id', 'id', name='uq_suppliers_tenant_id')
    )
    op.create_index(op.f('ix_suppliers_business_id'), 'suppliers', ['business_id'], unique=False)
    op.create_table('orders',
    sa.Column('external_id', sa.String(length=80), nullable=False),
    sa.Column('customer_id', sa.Uuid(), nullable=False),
    sa.Column('ordered_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status_reason', sa.String(length=200), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('paid','pending','cancelled','refunded')", name='order_status_valid'),
    sa.ForeignKeyConstraint(['business_id', 'customer_id'], ['customers.business_id', 'customers.id'], name='fk_order_tenant_customer'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'external_id', name='uq_orders_external'),
    sa.UniqueConstraint('business_id', 'id', name='uq_orders_tenant_id')
    )
    op.create_index(op.f('ix_orders_business_id'), 'orders', ['business_id'], unique=False)
    op.create_index('orders_tenant_date', 'orders', ['business_id', 'ordered_on'], unique=False)
    op.create_table('products',
    sa.Column('sku', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('supplier_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('unit_price >= 0 AND (unit_cost IS NULL OR unit_cost >= 0)', name='product_prices_valid'),
    sa.ForeignKeyConstraint(['business_id', 'supplier_id'], ['suppliers.business_id', 'suppliers.id'], name='fk_product_tenant_supplier'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'id', name='uq_products_tenant_id'),
    sa.UniqueConstraint('business_id', 'sku', name='uq_products_external')
    )
    op.create_index(op.f('ix_products_business_id'), 'products', ['business_id'], unique=False)
    op.create_table('inventory_balances',
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity >= 0', name='inventory_nonnegative'),
    sa.ForeignKeyConstraint(['business_id', 'product_id'], ['products.business_id', 'products.id'], name='fk_balance_tenant_product', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('business_id', 'product_id')
    )
    op.create_table('inventory_movements',
    sa.Column('external_id', sa.String(length=160), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('occurred_on', sa.Date(), nullable=False),
    sa.Column('quantity_delta', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('reason', sa.String(length=24), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity_delta <> 0', name='movement_nonzero'),
    sa.ForeignKeyConstraint(['business_id', 'product_id'], ['products.business_id', 'products.id'], name='fk_movement_tenant_product'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'external_id', name='uq_inventory_movements_external'),
    sa.UniqueConstraint('business_id', 'id', name='uq_inventory_movements_tenant_id')
    )
    op.create_index(op.f('ix_inventory_movements_business_id'), 'inventory_movements', ['business_id'], unique=False)
    op.create_table('order_items',
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('discount_amount', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('business_id', sa.Uuid(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity > 0 AND unit_price >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND (unit_cost IS NULL OR unit_cost >= 0)', name='order_item_amounts_valid'),
    sa.ForeignKeyConstraint(['business_id', 'order_id'], ['orders.business_id', 'orders.id'], name='fk_item_tenant_order', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['business_id', 'product_id'], ['products.business_id', 'products.id'], name='fk_item_tenant_product'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_unique_constraint('uq_order_product_line', 'order_items', ['business_id', 'order_id', 'product_id'])
    op.create_index('items_tenant_order', 'order_items', ['business_id', 'order_id'], unique=False)
    op.create_index(op.f('ix_order_items_business_id'), 'order_items', ['business_id'], unique=False)

def downgrade():
    op.drop_column('businesses', 'data_status')
    op.drop_index(op.f('ix_order_items_business_id'), table_name='order_items')
    op.drop_index('items_tenant_order', table_name='order_items')
    op.drop_table('order_items')
    op.drop_index(op.f('ix_inventory_movements_business_id'), table_name='inventory_movements')
    op.drop_table('inventory_movements')
    op.drop_table('inventory_balances')
    op.drop_index(op.f('ix_products_business_id'), table_name='products')
    op.drop_table('products')
    op.drop_index('orders_tenant_date', table_name='orders')
    op.drop_index(op.f('ix_orders_business_id'), table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_suppliers_business_id'), table_name='suppliers')
    op.drop_table('suppliers')
    op.drop_index(op.f('ix_import_batches_business_id'), table_name='import_batches')
    op.drop_table('import_batches')
    op.drop_index(op.f('ix_expenses_business_id'), table_name='expenses')
    op.drop_index('expenses_tenant_date', table_name='expenses')
    op.drop_table('expenses')
    op.drop_table('expense_coverage')
    op.drop_index(op.f('ix_customers_business_id'), table_name='customers')
    op.drop_table('customers')
