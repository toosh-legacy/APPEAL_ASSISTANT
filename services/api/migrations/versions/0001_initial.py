"""Initial schema (SPEC section 12): all tables, pgvector extension, FTS + HNSW indexes.

Expand/contract: later migrations only add columns/tables first (expand), and drop old ones in a
separate, later release (contract).

Revision ID: 0001
"""

from alembic import op
from appeal_core.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    # Snapshot of the section-12 models at revision 0001. Later revisions use explicit op.* calls.
    Base.metadata.create_all(bind=bind)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_chunk_tsv ON kb_chunk USING gin (tsv)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_precedent_chunk_tsv ON precedent_chunk USING gin (tsv)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_chunk_embedding ON kb_chunk USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_precedent_chunk_embedding ON precedent_chunk "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
