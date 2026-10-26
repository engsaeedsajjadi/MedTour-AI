"""Section 23: versioned CMS review, safe replacement of legacy direct-publish.

Existing published text is deliberately unpublished until independent
stage review under the new workflow. Legacy content snapshots are retained.
"""
from alembic import op
import sqlalchemy as sa
import hashlib
from uuid import uuid4
from datetime import datetime,timezone

revision="a23e674c5b20"
down_revision="a21c493b5e70"
branch_labels=None
depends_on=None

def base():
    return [
        sa.Column("tenant_id",sa.String(36),sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("id",sa.String(36),primary_key=True,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
    ]

def upgrade():
    op.add_column("content_pages",sa.Column("published_version_no",sa.Integer(),nullable=True))
    op.create_table("cms_versions",*base(),
        sa.Column("page_id",sa.String(36),sa.ForeignKey("content_pages.id"),nullable=False),
        sa.Column("version_no",sa.Integer(),nullable=False),
        sa.Column("title",sa.String(250),nullable=False),
        sa.Column("body",sa.Text(),nullable=False),
        sa.Column("content_hash",sa.String(64),nullable=False),
        sa.Column("author_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("reason",sa.String(200),nullable=False),
        sa.Column("status",sa.String(30),nullable=False),
        sa.UniqueConstraint("tenant_id","page_id","version_no"))
    op.create_index("ix_cms_versions_tenant_id","cms_versions",["tenant_id"])
    op.create_index("ix_cms_versions_page","cms_versions",["tenant_id","page_id","version_no"])
    op.create_table("cms_reviews",*base(),
        sa.Column("version_id",sa.String(36),sa.ForeignKey("cms_versions.id"),nullable=False),
        sa.Column("stage",sa.String(30),nullable=False),
        sa.Column("decision",sa.String(30),nullable=False),
        sa.Column("reviewer_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("evidence_reference",sa.String(100),nullable=False),
        sa.UniqueConstraint("tenant_id","version_id","stage"))
    op.create_index("ix_cms_reviews_tenant_id","cms_reviews",["tenant_id"])
    op.create_index("ix_cms_reviews_version","cms_reviews",["tenant_id","version_id"])
    op.create_table("cms_workflow_events",*base(),
        sa.Column("page_id",sa.String(36),sa.ForeignKey("content_pages.id"),nullable=False),
        sa.Column("version_id",sa.String(36),sa.ForeignKey("cms_versions.id"),nullable=True),
        sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("action",sa.String(55),nullable=False),
        sa.Column("reference",sa.String(100),nullable=False))
    op.create_index("ix_cms_workflow_events_tenant_id","cms_workflow_events",["tenant_id"])
    op.create_index("ix_cms_workflow_events_page","cms_workflow_events",["tenant_id","page_id","created_at"])
    conn=op.get_bind()
    old=conn.execute(sa.text("SELECT id,tenant_id,title,body,created_at FROM content_pages")).mappings().all()
    for row in old:
        author=conn.execute(sa.text(
            "SELECT id FROM users WHERE tenant_id=:tenant ORDER BY created_at,id LIMIT 1"),
            {"tenant":row["tenant_id"]}).scalar()
        if not author:
            continue
        title=row["title"] or ""
        body=row["body"] or ""
        digest=hashlib.sha256((title+"\x00"+body).encode("utf-8")).hexdigest()
        conn.execute(sa.text("""INSERT INTO cms_versions
            (tenant_id,id,created_at,page_id,version_no,title,body,content_hash,author_id,reason,status)
            VALUES (:tenant,:id,:created_at,:page_id,1,:title,:body,:digest,:author,:reason,'draft')"""),
            {"tenant":row["tenant_id"],"id":str(uuid4()),
             "created_at":row["created_at"] or datetime.now(timezone.utc),
             "page_id":row["id"],"title":title,"body":body,"digest":digest,
             "author":author,"reason":"legacy_content_requires_review"})
    # Fail closed: old published content did not pass the new approval quorum.
    conn.execute(sa.text("UPDATE content_pages SET status='draft', approved_by=NULL, published_version_no=NULL"))

def downgrade():
    # Do not silently restore pre-migration live publications.
    for name in ("cms_workflow_events","cms_reviews","cms_versions"):
        if name=="cms_workflow_events":
            op.drop_index("ix_cms_workflow_events_page",table_name=name)
        if name=="cms_reviews":
            op.drop_index("ix_cms_reviews_version",table_name=name)
        if name=="cms_versions":
            op.drop_index("ix_cms_versions_page",table_name=name)
        op.drop_index("ix_"+name+"_tenant_id",table_name=name)
        op.drop_table(name)
    op.drop_column("content_pages","published_version_no")
