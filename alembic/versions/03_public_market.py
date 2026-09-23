"""Add public market fields

Revision ID: 03_public_market
Revises: 02_agent_tool_tables
Create Date: 2026-06-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '03_public_market'
down_revision = '02_agent_tool_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User table: add role field
    op.add_column('user', sa.Column('role', sa.String(20), server_default='user'))
    op.create_index('ix_user_role', 'user', ['role'], unique=False)

    # Agent table: add public market fields
    op.add_column('agent', sa.Column('is_public', sa.Boolean(), server_default='false'))
    op.add_column('agent', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.add_column('agent', sa.Column('copy_count', sa.Integer(), server_default='0'))
    op.add_column('agent', sa.Column('session_count', sa.Integer(), server_default='0'))
    op.add_column('agent', sa.Column('published_at', sa.DateTime(), nullable=True))
    op.add_column('agent', sa.Column('published_by', sa.Integer(), nullable=True))
    op.add_column('agent', sa.Column('source_agent_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    op.create_foreign_key('fk_agent_owner_id', 'agent', 'user', ['owner_id'], ['id'])
    op.create_foreign_key('fk_agent_published_by', 'agent', 'user', ['published_by'], ['id'])
    op.create_foreign_key('fk_agent_source', 'agent', 'agent', ['source_agent_id'], ['id'])
    
    op.create_index('ix_agent_is_public', 'agent', ['is_public'], unique=False)
    op.create_index('ix_agent_owner_id', 'agent', ['owner_id'], unique=False)
    op.create_index('ix_agent_source', 'agent', ['source_agent_id'], unique=False)

    # Tool table: add public market fields
    op.add_column('tool', sa.Column('is_public', sa.Boolean(), server_default='false'))
    op.add_column('tool', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.add_column('tool', sa.Column('copy_count', sa.Integer(), server_default='0'))
    op.add_column('tool', sa.Column('source_tool_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    op.create_foreign_key('fk_tool_owner_id', 'tool', 'user', ['owner_id'], ['id'])
    op.create_foreign_key('fk_tool_source', 'tool', 'tool', ['source_tool_id'], ['id'])
    
    op.create_index('ix_tool_is_public', 'tool', ['is_public'], unique=False)
    op.create_index('ix_tool_owner_id', 'tool', ['owner_id'], unique=False)
    op.create_index('ix_tool_source', 'tool', ['source_tool_id'], unique=False)

    # AgentTool table: add is_public_binding field
    op.add_column('agenttool', sa.Column('is_public_binding', sa.Boolean(), server_default='false'))

    # Data migration: migrate created_by to owner_id
    op.execute("UPDATE agent SET owner_id = created_by WHERE created_by IS NOT NULL")
    
    # Mark existing tools as public (no owner)
    op.execute("UPDATE tool SET is_public = true WHERE owner_id IS NULL")


def downgrade() -> None:
    # AgentTool table
    op.drop_column('agenttool', 'is_public_binding')

    # Tool table
    op.drop_index('ix_tool_source', table_name='tool')
    op.drop_index('ix_tool_owner_id', table_name='tool')
    op.drop_index('ix_tool_is_public', table_name='tool')
    
    op.drop_constraint('fk_tool_source', 'tool', type_='foreignkey')
    op.drop_constraint('fk_tool_owner_id', 'tool', type_='foreignkey')
    
    op.drop_column('tool', 'source_tool_id')
    op.drop_column('tool', 'copy_count')
    op.drop_column('tool', 'owner_id')
    op.drop_column('tool', 'is_public')

    # Agent table
    op.drop_index('ix_agent_source', table_name='agent')
    op.drop_index('ix_agent_owner_id', table_name='agent')
    op.drop_index('ix_agent_is_public', table_name='agent')
    
    op.drop_constraint('fk_agent_source', 'agent', type_='foreignkey')
    op.drop_constraint('fk_agent_published_by', 'agent', type_='foreignkey')
    op.drop_constraint('fk_agent_owner_id', 'agent', type_='foreignkey')
    
    op.drop_column('agent', 'source_agent_id')
    op.drop_column('agent', 'published_by')
    op.drop_column('agent', 'published_at')
    op.drop_column('agent', 'session_count')
    op.drop_column('agent', 'copy_count')
    op.drop_column('agent', 'owner_id')
    op.drop_column('agent', 'is_public')

    # User table
    op.drop_index('ix_user_role', table_name='user')
    op.drop_column('user', 'role')