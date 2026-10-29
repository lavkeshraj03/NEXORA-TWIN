"""Enable vector storage. No application tables are created at startup."""
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade():
    # Preserve the extension: other schemas may use it. Downgrade only the revision.
    pass
