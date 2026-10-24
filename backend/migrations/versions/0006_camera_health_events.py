"""Add recorded camera health transitions for uptime history and health alerts."""
from alembic import op
import sqlalchemy as sa

revision = "0006_camera_health_events"
down_revision = "0005_map_revision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "camera_health_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("from_status", sa.String(24), nullable=False, server_default=""),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("error_category", sa.String(48), nullable=False, server_default=""),
    )
    op.create_index("ix_camera_health_events_camera_id", "camera_health_events", ["camera_id"])
    op.create_index("ix_camera_health_events_at", "camera_health_events", ["at"])


def downgrade():
    op.drop_index("ix_camera_health_events_at", table_name="camera_health_events")
    op.drop_index("ix_camera_health_events_camera_id", table_name="camera_health_events")
    op.drop_table("camera_health_events")
