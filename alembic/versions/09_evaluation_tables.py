"""Evaluation tables (test set / case / run / case result)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '09_evaluation_tables'
down_revision = '08_agent_version'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'evaluation_test_set',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('case_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_evaluation_test_set_name', 'evaluation_test_set', ['name'])
    op.create_index('ix_evaluation_test_set_owner_id', 'evaluation_test_set', ['owner_id'])

    op.create_table(
        'evaluation_case',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('testset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluation_test_set.id'), nullable=False),
        sa.Column('type', sa.String(), nullable=False, server_default='answer'),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('expected_answer', sa.Text(), nullable=True),
        sa.Column('expected_tool', sa.String(), nullable=True),
        sa.Column('expected_arguments', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('expected_document_ids', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_evaluation_case_testset_id', 'evaluation_case', ['testset_id'])

    op.create_table(
        'evaluation_run',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('testset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluation_test_set.id'), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent.id'), nullable=False),
        sa.Column('version_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_version.id'), nullable=False),
        sa.Column('judge_model', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('stats', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_evaluation_run_testset_id', 'evaluation_run', ['testset_id'])
    op.create_index('ix_evaluation_run_agent_id', 'evaluation_run', ['agent_id'])
    op.create_index('ix_evaluation_run_status', 'evaluation_run', ['status'])

    op.create_table(
        'evaluation_case_result',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluation_run.id'), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluation_case.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('agent_answer', sa.Text(), nullable=True),
        sa.Column('actual_tool_calls', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('actual_document_ids', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('scores', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('judged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('run_id', 'case_id', name='uq_eval_result_case'),
    )
    op.create_index('ix_evaluation_case_result_run_id', 'evaluation_case_result', ['run_id'])
    op.create_index('ix_evaluation_case_result_case_id', 'evaluation_case_result', ['case_id'])
    op.create_index('ix_evaluation_case_result_status', 'evaluation_case_result', ['status'])


def downgrade() -> None:
    op.drop_table('evaluation_case_result')
    op.drop_table('evaluation_run')
    op.drop_table('evaluation_case')
    op.drop_table('evaluation_test_set')
