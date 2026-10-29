"""Deterministic what-if runs against tenant-scoped twin snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_simulations"
down_revision = "0006_twin"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_twin_snapshot_tenant_id", "twin_snapshots", ["business_id","id"])
    op.create_table("simulation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("implementation_version", sa.String(24), nullable=False),
        sa.Column("baseline_hash", sa.String(64), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["business_id","baseline_snapshot_id"], ["twin_snapshots.business_id","twin_snapshots.id"], name="fk_simulation_tenant_snapshot", ondelete="CASCADE"))
    op.create_index("ix_simulation_runs_business_id", "simulation_runs", ["business_id"])
    op.create_index("simulation_runs_tenant_created", "simulation_runs", ["business_id","created_at"])
    op.execute("""CREATE FUNCTION guard_simulation_run() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.id IS DISTINCT FROM OLD.id OR NEW.business_id IS DISTINCT FROM OLD.business_id
        OR NEW.baseline_snapshot_id IS DISTINCT FROM OLD.baseline_snapshot_id OR NEW.name IS DISTINCT FROM OLD.name
        OR NEW.implementation_version IS DISTINCT FROM OLD.implementation_version OR NEW.baseline_hash IS DISTINCT FROM OLD.baseline_hash
        OR NEW.parameters IS DISTINCT FROM OLD.parameters OR NEW.result IS DISTINCT FROM OLD.result
        OR NEW.content_hash IS DISTINCT FROM OLD.content_hash OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Simulation evidence is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER simulation_run_immutable BEFORE UPDATE ON simulation_runs FOR EACH ROW EXECUTE FUNCTION guard_simulation_run()")


def downgrade():
    op.drop_table("simulation_runs")
    op.execute("DROP FUNCTION guard_simulation_run()")
    op.drop_constraint("uq_twin_snapshot_tenant_id", "twin_snapshots", type_="unique")
