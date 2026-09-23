"""Add agent and tool tables

Revision ID: 02_agent_tool_tables
Revises: cdc4715fc54e
Create Date: 2026-06-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '02_agent_tool_tables'
down_revision = 'cdc4715fc54e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tool table
    op.create_table(
        'tool',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('function_name', sa.String(), nullable=False),
        sa.Column('input_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('example', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tool_name'), 'tool', ['name'], unique=False)
    op.create_index(op.f('ix_tool_function_name'), 'tool', ['function_name'], unique=False)

    # Create agent table
    op.create_table(
        'agent',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('graph_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_name'), 'agent', ['name'], unique=False)

    # Create agent_tool association table
    op.create_table(
        'agenttool',
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tool_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ),
        sa.ForeignKeyConstraint(['tool_id'], ['tool.id'], ),
        sa.PrimaryKeyConstraint('agent_id', 'tool_id')
    )

    # Add agent_id to session table
    op.add_column('session', sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(None, 'session', 'agent', ['agent_id'], ['id'])

    # Create execution_log table
    op.create_table(
        'executionlog',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('node_name', sa.String(), nullable=False),
        sa.Column('node_type', sa.String(), nullable=False),
        sa.Column('input_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('execution_time', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_executionlog_session_id'), 'executionlog', ['session_id'], unique=False)
    op.create_index(op.f('ix_executionlog_node_name'), 'executionlog', ['node_name'], unique=False)
    op.create_index(op.f('ix_executionlog_node_type'), 'executionlog', ['node_type'], unique=False)


def downgrade() -> None:
    # Drop execution_log table
    op.drop_index(op.f('ix_executionlog_node_type'), table_name='executionlog')
    op.drop_index(op.f('ix_executionlog_node_name'), table_name='executionlog')
    op.drop_index(op.f('ix_executionlog_session_id'), table_name='executionlog')
    op.drop_table('executionlog')

    # Remove foreign key and column from session
    op.drop_constraint(None, 'session', type_='foreignkey')
    op.drop_column('session', 'agent_id')

    # Drop agent_tool table
    op.drop_table('agenttool')

    # Drop agent table
    op.drop_index(op.f('ix_agent_name'), table_name='agent')
    op.drop_table('agent')

    # Drop tool table
    op.drop_index(op.f('ix_tool_function_name'), table_name='tool')
    op.drop_index(op.f('ix_tool_name'), table_name='tool')
    op.drop_table('tool')