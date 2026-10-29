"""Private bounded analyst investigations and tool evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="0008_analyst"
down_revision="0007_simulations"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("analyst_investigations",
        sa.Column("id",sa.Uuid(),nullable=False),
        sa.Column("business_id",sa.Uuid(),nullable=False),
        sa.Column("user_id",sa.Uuid(),nullable=False),
        sa.Column("captured_role",sa.String(16),nullable=False),
        sa.Column("question",sa.Text(),nullable=False),
        sa.Column("status",sa.String(16),nullable=False),
        sa.Column("request_id",sa.String(36),nullable=False),
        sa.Column("implementation_version",sa.String(24),nullable=False),
        sa.Column("chat_model",sa.String(200),nullable=False),
        sa.Column("parameters",postgresql.JSONB(),nullable=False),
        sa.Column("inputs",postgresql.JSONB(),nullable=False),
        sa.Column("input_hash",sa.String(64),nullable=False),
        sa.Column("plan",postgresql.JSONB(),nullable=False),
        sa.Column("executions",postgresql.JSONB(),nullable=False),
        sa.Column("response",postgresql.JSONB(),nullable=True),
        sa.Column("error",sa.String(300),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("finished_at",sa.DateTime(timezone=True),nullable=True),
        sa.CheckConstraint("status IN ('running','completed','partial','failed')",name="analyst_status_valid"),
        sa.CheckConstraint("length(input_hash) = 64",name="analyst_input_hash_valid"),
        sa.ForeignKeyConstraint(["business_id"],["businesses.id"],ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_analyst_investigations_business_id","analyst_investigations",["business_id"])
    op.create_index("analyst_tenant_user_created","analyst_investigations",["business_id","user_id","created_at"])
    op.execute("""CREATE FUNCTION guard_analyst_investigation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status <> 'running' AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Final analyst evidence is immutable';
      END IF;
      IF NEW.id IS DISTINCT FROM OLD.id OR NEW.business_id IS DISTINCT FROM OLD.business_id
        OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.captured_role IS DISTINCT FROM OLD.captured_role
        OR NEW.question IS DISTINCT FROM OLD.question OR NEW.request_id IS DISTINCT FROM OLD.request_id
        OR NEW.implementation_version IS DISTINCT FROM OLD.implementation_version OR NEW.chat_model IS DISTINCT FROM OLD.chat_model
        OR NEW.parameters IS DISTINCT FROM OLD.parameters OR NEW.inputs IS DISTINCT FROM OLD.inputs
        OR NEW.input_hash IS DISTINCT FROM OLD.input_hash OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Analyst source inputs are immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER analyst_investigation_immutable BEFORE UPDATE ON analyst_investigations FOR EACH ROW EXECUTE FUNCTION guard_analyst_investigation()")


def downgrade():
    op.drop_table("analyst_investigations")
    op.execute("DROP FUNCTION guard_analyst_investigation()")
