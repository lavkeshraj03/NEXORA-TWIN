"""Source-backed knowledge graph snapshots and private frozen reports."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision="0009_insights"
down_revision="0008_analyst"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("graph_builds",
        sa.Column("id",sa.Uuid(),nullable=False),sa.Column("business_id",sa.Uuid(),nullable=False),sa.Column("created_by",sa.Uuid()),
        sa.Column("implementation_version",sa.String(24),nullable=False),sa.Column("source_hash",sa.String(64),nullable=False),sa.Column("manifest",pg.JSONB(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.PrimaryKeyConstraint("id"),sa.ForeignKeyConstraint(["business_id"],["businesses.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["created_by"],["users.id"],ondelete="SET NULL"),sa.UniqueConstraint("business_id","id",name="uq_graph_build_tenant"))
    op.create_index("ix_graph_builds_business_id","graph_builds",["business_id"])
    op.create_table("knowledge_nodes",
        sa.Column("id",sa.Uuid(),nullable=False),sa.Column("business_id",sa.Uuid(),nullable=False),sa.Column("build_id",sa.Uuid(),nullable=False),sa.Column("kind",sa.String(24),nullable=False),sa.Column("source_key",sa.String(100),nullable=False),sa.Column("label",sa.String(260),nullable=False),sa.Column("source",pg.JSONB(),nullable=False),sa.Column("document_id",sa.Uuid()),sa.Column("visibility",sa.String(24),nullable=False),
        sa.PrimaryKeyConstraint("id"),sa.ForeignKeyConstraint(["business_id"],["businesses.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["business_id","build_id"],["graph_builds.business_id","graph_builds.id"],ondelete="CASCADE",name="fk_node_tenant_build"),sa.UniqueConstraint("business_id","build_id","id",name="uq_graph_node_tenant"),sa.UniqueConstraint("build_id","source_key",name="uq_graph_node_source"))
    op.create_index("ix_knowledge_nodes_business_id","knowledge_nodes",["business_id"])
    op.create_index("graph_nodes_tenant_kind","knowledge_nodes",["business_id","build_id","kind"])
    op.create_table("knowledge_edges",
        sa.Column("id",sa.Uuid(),nullable=False),sa.Column("business_id",sa.Uuid(),nullable=False),sa.Column("build_id",sa.Uuid(),nullable=False),sa.Column("source_id",sa.Uuid(),nullable=False),sa.Column("target_id",sa.Uuid(),nullable=False),sa.Column("relationship",sa.String(40),nullable=False),sa.Column("provenance",pg.JSONB(),nullable=False),sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["business_id"],["businesses.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["business_id","build_id"],["graph_builds.business_id","graph_builds.id"],ondelete="CASCADE",name="fk_edge_tenant_build"),sa.ForeignKeyConstraint(["business_id","build_id","source_id"],["knowledge_nodes.business_id","knowledge_nodes.build_id","knowledge_nodes.id"],ondelete="CASCADE",name="fk_edge_tenant_source"),sa.ForeignKeyConstraint(["business_id","build_id","target_id"],["knowledge_nodes.business_id","knowledge_nodes.build_id","knowledge_nodes.id"],ondelete="CASCADE",name="fk_edge_tenant_target"))
    op.create_index("ix_knowledge_edges_business_id","knowledge_edges",["business_id"])
    op.create_index("graph_edges_tenant_build","knowledge_edges",["business_id","build_id"])
    op.create_table("generated_reports",
        sa.Column("id",sa.Uuid(),nullable=False),sa.Column("business_id",sa.Uuid(),nullable=False),sa.Column("user_id",sa.Uuid(),nullable=False),sa.Column("captured_role",sa.String(16),nullable=False),sa.Column("name",sa.String(100),nullable=False),sa.Column("kind",sa.String(24),nullable=False),sa.Column("implementation_version",sa.String(24),nullable=False),sa.Column("payload",pg.JSONB(),nullable=False),sa.Column("content_hash",sa.String(64),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.PrimaryKeyConstraint("id"),sa.ForeignKeyConstraint(["business_id"],["businesses.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"))
    op.create_index("ix_generated_reports_business_id","generated_reports",["business_id"])
    op.create_index("reports_tenant_user_created","generated_reports",["business_id","user_id","created_at"])
    op.execute("""CREATE FUNCTION guard_insight_evidence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'Saved graph and report evidence is immutable'; END IF;
      RETURN NEW;
    END $$""")
    for table in ["knowledge_nodes","knowledge_edges","generated_reports"]:
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_insight_evidence()")
    op.execute("""CREATE FUNCTION guard_graph_build() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NEW.id IS DISTINCT FROM OLD.id OR NEW.business_id IS DISTINCT FROM OLD.business_id
        OR NEW.implementation_version IS DISTINCT FROM OLD.implementation_version OR NEW.source_hash IS DISTINCT FROM OLD.source_hash
        OR NEW.manifest IS DISTINCT FROM OLD.manifest OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Saved graph build evidence is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER graph_build_immutable BEFORE UPDATE ON graph_builds FOR EACH ROW EXECUTE FUNCTION guard_graph_build()")


def downgrade():
    for table in ["generated_reports","knowledge_edges","knowledge_nodes","graph_builds"]:op.drop_table(table)
    op.execute("DROP FUNCTION guard_insight_evidence()")
    op.execute("DROP FUNCTION guard_graph_build()")
