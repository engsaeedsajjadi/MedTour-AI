"""Section 25: metadata-only audited voice samples; no voice binary or text stored."""
from alembic import op
import sqlalchemy as sa

revision="a25e720d9b10"
down_revision="a24f703c9b62"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("voice_sample_jobs",
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("request_key",sa.String(100),nullable=False),
        sa.Column("kind",sa.String(12),nullable=False),
        sa.Column("locale",sa.String(10),nullable=False),
        sa.Column("source_format",sa.String(16),nullable=False),
        sa.Column("audio_sha256",sa.String(64),nullable=False),
        sa.Column("transcript_sha256",sa.String(64),nullable=True),
        sa.Column("duration_ms",sa.Integer(),nullable=False),
        sa.Column("status",sa.String(32),nullable=False),
        sa.Column("author_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("reviewer_id",sa.String(36),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("review_reference",sa.String(100),nullable=True),
        sa.UniqueConstraint("tenant_id","request_key"))
    op.create_index("ix_voice_sample_jobs_tenant_id","voice_sample_jobs",["tenant_id"])
    op.create_index("ix_voice_samples_tenant_state","voice_sample_jobs",["tenant_id","status","created_at"])
def downgrade():
    op.drop_index("ix_voice_samples_tenant_state",table_name="voice_sample_jobs")
    op.drop_index("ix_voice_sample_jobs_tenant_id",table_name="voice_sample_jobs")
    op.drop_table("voice_sample_jobs")
