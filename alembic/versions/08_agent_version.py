"""Agent version snapshot table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '08_agent_version'
down_revision = '07_rag_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_version',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('snapshot', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id']),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.UniqueConstraint('agent_id', 'version_no', name='uq_agent_version_no'),
    )
    op.create_index('ix_agent_version_agent_id', 'agent_version', ['agent_id'])
    op.create_index('ix_agent_version_version_no', 'agent_version', ['version_no'])


def downgrade() -> None:
    op.drop_index('ix_agent_version_version_no', table_name='agent_version')
    op.drop_index('ix_agent_version_agent_id', table_name='agent_version')
    op.drop_table('agent_version')
