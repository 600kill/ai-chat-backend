"""RAG tables: knowledge_base / knowledge_document / knowledge_chunk (pgvector) / agent_knowledge_base."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.config import settings

revision = '07_rag_tables'
down_revision = '06_agent_runtime_config'
branch_labels = None
depends_on = None

# 向量维度跟随当前 embedding 配置（bge-small-zh=512；text-embedding-v2=1536）
DIM = settings.RAG_EMBEDDING_DIM


def upgrade() -> None:
    # pgvector 扩展（mem0 可能已建，IF NOT EXISTS 幂等）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'knowledge_base',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('chunk_size', sa.Integer(), nullable=True),
        sa.Column('chunk_overlap', sa.Integer(), nullable=True),
        sa.Column('top_k', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id']),
    )
    op.create_index('ix_knowledge_base_name', 'knowledge_base', ['name'])
    op.create_index('ix_knowledge_base_is_public', 'knowledge_base', ['is_public'])
    op.create_index('ix_knowledge_base_owner_id', 'knowledge_base', ['owner_id'])

    op.create_table(
        'knowledge_document',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kb_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='processing'),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('char_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['kb_id'], ['knowledge_base.id']),
    )
    op.create_index('ix_knowledge_document_kb_id', 'knowledge_document', ['kb_id'])
    op.create_index('ix_knowledge_document_file_hash', 'knowledge_document', ['file_hash'])
    op.create_index('ix_knowledge_document_status', 'knowledge_document', ['status'])

    op.create_table(
        'knowledge_chunk',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kb_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', pgvector_type(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_document.id']),
        sa.ForeignKeyConstraint(['kb_id'], ['knowledge_base.id']),
    )
    op.create_index('ix_knowledge_chunk_document_id', 'knowledge_chunk', ['document_id'])
    op.create_index('ix_knowledge_chunk_kb_id', 'knowledge_chunk', ['kb_id'])
    # HNSW 余弦相似度索引（与检索 <=> 操作符一致）
    op.execute(
        "CREATE INDEX ix_knowledge_chunk_embedding_hnsw ON knowledge_chunk "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        'agent_knowledge_base',
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kb_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint('agent_id', 'kb_id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent.id']),
        sa.ForeignKeyConstraint(['kb_id'], ['knowledge_base.id']),
    )


def pgvector_type():
    """延迟导入 pgvector 类型，避免无扩展环境下迁移模块导入失败。"""
    from pgvector.sqlalchemy import Vector
    return Vector(DIM)


def downgrade() -> None:
    op.drop_table('agent_knowledge_base')
    op.drop_index('ix_knowledge_chunk_embedding_hnsw', table_name='knowledge_chunk')
    op.drop_table('knowledge_chunk')
    op.drop_table('knowledge_document')
    op.drop_table('knowledge_base')
