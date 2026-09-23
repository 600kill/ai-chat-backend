"""Add updated_at columns to existing tables."""

from alembic import op
import sqlalchemy as sa

revision = '05_add_updated_at_columns'
down_revision = '04_metrics_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = ['user', 'session', 'thread', 'agent', 'tool', 'agenttool']
    
    for table in tables:
        try:
            op.add_column(
                table,
                sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'))
            )
        except Exception:
            pass


def downgrade() -> None:
    tables = ['user', 'session', 'thread', 'agent', 'tool', 'agenttool']
    
    for table in tables:
        try:
            op.drop_column(table, 'updated_at')
        except Exception:
            pass