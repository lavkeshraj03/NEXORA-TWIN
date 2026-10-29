"""Identity, business memberships, server-side sessions and tenant audit history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_identity"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("email", sa.String(254), nullable=False, unique=True), sa.Column("name", sa.String(100), nullable=False), sa.Column("password_hash", sa.Text(), nullable=False), sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("auth_sessions", sa.Column("token_hash", sa.String(64), primary_key=True), sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("csrf_token", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table("businesses", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("name", sa.String(100), nullable=False), sa.Column("business_type", sa.String(30), nullable=False), sa.Column("country", sa.String(2), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("timezone", sa.String(80), nullable=False), sa.Column("reporting_month", sa.Integer(), nullable=False), sa.Column("modules", postgresql.JSONB(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.CheckConstraint("business_type IN ('retail','restaurant','manufacturing','services','wholesale')", name="business_type_valid"), sa.CheckConstraint("reporting_month BETWEEN 1 AND 12", name="reporting_month_valid"))
    op.create_table("business_memberships", sa.Column("business_id", sa.Uuid(), sa.ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True), sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), sa.Column("role", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.CheckConstraint("role IN ('owner','administrator','analyst','viewer')", name="membership_role_valid"))
    op.create_index("membership_user_business", "business_memberships", ["user_id", "business_id"])
    op.create_table("audit_logs", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("business_id", sa.Uuid(), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True), sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True), sa.Column("event", sa.String(80), nullable=False), sa.Column("target_id", sa.String(80), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("audit_business_created", "audit_logs", ["business_id", "created_at"])


def downgrade():
    for table in ["audit_logs", "business_memberships", "businesses", "auth_sessions", "users"]:
        op.drop_table(table)
