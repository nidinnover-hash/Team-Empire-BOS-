"""Add memory_embeddings table with pgvector.

Revision ID: 20260305_0074
Revises: 20260305_0073
"""
import sqlalchemy as sa
from alembic import op

revision = "20260305_0074"
down_revision = "20260305_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.create_table(
        "memory_embeddings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "workspace_id",
            sa.Integer,
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.Integer, nullable=False),
        sa.Column("content_text", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text, nullable=False),  # replaced by raw SQL below
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id", "source_type", "source_id",
            name="uq_embedding_org_source",
        ),
    )

    if dialect == "postgresql":
        # Enable pgvector extension (idempotent)
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # Replace the text placeholder with a real vector column.
        op.execute(
            "ALTER TABLE memory_embeddings "
            "ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)"
        )
        # HNSW index for fast cosine similarity searches.
        op.execute(
            "CREATE INDEX ix_memory_embeddings_hnsw "
            "ON memory_embeddings USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )


def downgrade() -> None:
    op.drop_table("memory_embeddings")
