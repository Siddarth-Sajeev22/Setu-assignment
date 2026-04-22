"""Initial schema migration - create tables and indexes.

Revision ID: 001
Revises: 
Create Date: 2026-01-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade: create initial schema."""
    op.create_table(
        'merchants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('merchant_id', sa.String(100), nullable=False),
        sa.Column('merchant_name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        # UNIQUE already creates a B-tree index — no separate idx needed
        sa.UniqueConstraint('merchant_id', name='uq_merchants_merchant_id'),
    )

    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.String(36), nullable=False),
        sa.Column('merchant_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        # UNIQUE already creates a B-tree index — no separate idx needed
        sa.UniqueConstraint('transaction_id', name='uq_transactions_transaction_id'),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id']),
    )
    op.create_index('idx_transactions_merchant_id', 'transactions', ['merchant_id'])
    op.create_index('idx_transactions_status', 'transactions', ['status'])
    op.create_index('idx_transactions_created_at', 'transactions', ['created_at'])
    # Composite indexes for the two most common filter combinations
    op.create_index('idx_transaction_merchant_status', 'transactions', ['merchant_id', 'status'])
    op.create_index('idx_transaction_created_status', 'transactions', ['created_at', 'status'])

    op.create_table(
        'payment_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(36), nullable=False),
        sa.Column('transaction_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        # UNIQUE already creates a B-tree index — no separate idx needed
        sa.UniqueConstraint('event_id', name='uq_payment_events_event_id'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id']),
    )
    # Composite index: all discrepancy subqueries filter on (transaction_id, event_type) together
    op.create_index(
        'idx_payment_events_transaction_event_type',
        'payment_events',
        ['transaction_id', 'event_type'],
    )


def downgrade() -> None:
    """Downgrade: drop all tables."""
    op.drop_table('payment_events')
    op.drop_table('transactions')
    op.drop_table('merchants')
