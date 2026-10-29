"""Reproducible digital twin snapshots.

Revision ID: 0006_twin
Revises: 0005_models
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_twin"
down_revision = "0005_models"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("twin_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("implementation_version", sa.String(24), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(content_hash) = 64", name="twin_hash_length"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_twin_snapshots_business_id", "twin_snapshots", ["business_id"])
    op.create_index("twin_snapshots_tenant_created", "twin_snapshots", ["business_id", "created_at"])
    # Preserve user deletion's SET NULL while refusing changes to captured evidence.
    op.execute("""CREATE FUNCTION guard_twin_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.id IS DISTINCT FROM OLD.id OR NEW.business_id IS DISTINCT FROM OLD.business_id
        OR NEW.name IS DISTINCT FROM OLD.name OR NEW.implementation_version IS DISTINCT FROM OLD.implementation_version
        OR NEW.content_hash IS DISTINCT FROM OLD.content_hash OR NEW.payload IS DISTINCT FROM OLD.payload
        OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Twin snapshot evidence is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER twin_snapshot_immutable BEFORE UPDATE ON twin_snapshots FOR EACH ROW EXECUTE FUNCTION guard_twin_snapshot()")


def downgrade():
    op.drop_table("twin_snapshots")
    op.execute("DROP FUNCTION guard_twin_snapshot()")
