"""Create metrics tables for agent performance monitoring."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '04_metrics_tables'
down_revision = '03_public_market'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AgentMetricsSession table
    op.create_table(
        'agentmetricssession',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('total_duration_ms', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    )
    op.create_index(op.f('ix_agentmetricssession_session_id'), 'agentmetricssession', ['session_id'], unique=False)
    op.create_index(op.f('ix_agentmetricssession_agent_id'), 'agentmetricssession', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agentmetricssession_user_id'), 'agentmetricssession', ['user_id'], unique=False)

    # AgentMetricsLLM table
    op.create_table(
        'agentmetricsllm',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metrics_session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('llm_model', sa.String(), nullable=False),
        sa.Column('inference_duration_ms', sa.Integer(), nullable=False),
        sa.Column('ttft_ms', sa.Integer(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('token_cost', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['metrics_session_id'], ['agentmetricssession.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
    )
    op.create_index(op.f('ix_agentmetricsllm_metrics_session_id'), 'agentmetricsllm', ['metrics_session_id'], unique=False)
    op.create_index(op.f('ix_agentmetricsllm_session_id'), 'agentmetricsllm', ['session_id'], unique=False)

    # AgentMetricsVector table
    op.create_table(
        'agentmetricsvector',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metrics_session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('search_duration_ms', sa.Integer(), nullable=False),
        sa.Column('results_count', sa.Integer(), nullable=False),
        sa.Column('query_length', sa.Integer(), nullable=True),
        sa.Column('memory_type', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['metrics_session_id'], ['agentmetricssession.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
    )
    op.create_index(op.f('ix_agentmetricsvector_metrics_session_id'), 'agentmetricsvector', ['metrics_session_id'], unique=False)
    op.create_index(op.f('ix_agentmetricsvector_session_id'), 'agentmetricsvector', ['session_id'], unique=False)

    # AgentMetricsTool table
    op.create_table(
        'agentmetricstool',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metrics_session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('tool_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('call_duration_ms', sa.Integer(), nullable=False),
        sa.Column('input_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_result', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['metrics_session_id'], ['agentmetricssession.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
        sa.ForeignKeyConstraint(['tool_id'], ['tool.id'], ),
    )
    op.create_index(op.f('ix_agentmetricstool_metrics_session_id'), 'agentmetricstool', ['metrics_session_id'], unique=False)
    op.create_index(op.f('ix_agentmetricstool_session_id'), 'agentmetricstool', ['session_id'], unique=False)
    op.create_index(op.f('ix_agentmetricstool_tool_name'), 'agentmetricstool', ['tool_name'], unique=False)

    # AgentMetricsNode table
    op.create_table(
        'agentmetricsnode',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metrics_session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('node_name', sa.String(), nullable=False),
        sa.Column('node_type', sa.String(), nullable=False),
        sa.Column('execution_order', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('input_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['metrics_session_id'], ['agentmetricssession.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
    )
    op.create_index(op.f('ix_agentmetricsnode_metrics_session_id'), 'agentmetricsnode', ['metrics_session_id'], unique=False)
    op.create_index(op.f('ix_agentmetricsnode_session_id'), 'agentmetricsnode', ['session_id'], unique=False)
    op.create_index(op.f('ix_agentmetricsnode_execution_order'), 'agentmetricsnode', ['execution_order'], unique=False)

    # AgentMetricsConcurrent table
    op.create_table(
        'agentmetricsconcurrent',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('active_sessions', sa.Integer(), nullable=False),
        sa.Column('active_tasks', sa.Integer(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ),
    )
    op.create_index(op.f('ix_agentmetricsconcurrent_agent_id'), 'agentmetricsconcurrent', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agentmetricsconcurrent_recorded_at'), 'agentmetricsconcurrent', ['recorded_at'], unique=False)

    # AgentMetricsTokenSummary table
    op.create_table(
        'agentmetricstokensummary',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('total_input_tokens', sa.Integer(), nullable=False),
        sa.Column('total_output_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('total_cost', sa.Float(), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    )
    op.create_index(op.f('ix_agentmetricstokensummary_agent_id'), 'agentmetricstokensummary', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agentmetricstokensummary_user_id'), 'agentmetricstokensummary', ['user_id'], unique=False)
    op.create_index(op.f('ix_agentmetricstokensummary_date'), 'agentmetricstokensummary', ['date'], unique=False)


def downgrade() -> None:
    op.drop_table('agentmetricstokensummary')
    op.drop_table('agentmetricsconcurrent')
    op.drop_table('agentmetricsnode')
    op.drop_table('agentmetricstool')
    op.drop_table('agentmetricsvector')
    op.drop_table('agentmetricsllm')
    op.drop_table('agentmetricssession')