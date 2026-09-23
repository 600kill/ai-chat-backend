"""Add agent runtime config columns (system_prompt/model_name/temperature/max_tokens)."""

from alembic import op
import sqlalchemy as sa

revision = '06_agent_runtime_config'
down_revision = '05_add_updated_at_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agent', sa.Column('system_prompt', sa.Text(), nullable=True))
    op.add_column('agent', sa.Column('model_name', sa.String(length=255), nullable=True))
    op.add_column('agent', sa.Column('temperature', sa.Float(), nullable=True))
    op.add_column('agent', sa.Column('max_tokens', sa.Integer(), nullable=True))
    op.create_index('ix_agent_model_name', 'agent', ['model_name'])


def downgrade() -> None:
    op.drop_index('ix_agent_model_name', table_name='agent')
    op.drop_column('agent', 'max_tokens')
    op.drop_column('agent', 'temperature')
    op.drop_column('agent', 'model_name')
    op.drop_column('agent', 'system_prompt')
