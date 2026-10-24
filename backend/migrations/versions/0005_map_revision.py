"""Add optimistic concurrency revision for floor-plan mutations."""
from alembic import op
import sqlalchemy as sa

revision = "0005_map_revision"
down_revision = "0004_control_center"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("floor_plans", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    op.drop_column("floor_plans", "revision")
