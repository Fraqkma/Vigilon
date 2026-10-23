"""Add floor plans, camera placements and optional device context."""
from alembic import op
import sqlalchemy as sa

revision = "0004_control_center"
down_revision = "0003_source_timeouts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cameras", sa.Column("manufacturer", sa.String(120), nullable=True))
    op.add_column("cameras", sa.Column("model", sa.String(120), nullable=True))
    op.add_column("cameras", sa.Column("specifications", sa.String(500), nullable=True))
    op.add_column("cameras", sa.Column("responsible_contact", sa.String(200), nullable=True))
    op.add_column("cameras", sa.Column("response_notes", sa.String(1000), nullable=True))
    op.create_table(
        "floor_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("location_label", sa.String(160), nullable=False, server_default=""),
        sa.Column("image_name", sa.String(80), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "camera_placements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("floor_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.UniqueConstraint("camera_id", name="uq_camera_placement_camera"),
    )
    op.create_index("ix_camera_placements_plan_id", "camera_placements", ["plan_id"])
    op.create_index("ix_camera_placements_camera_id", "camera_placements", ["camera_id"])


def downgrade():
    op.drop_index("ix_camera_placements_camera_id", table_name="camera_placements")
    op.drop_index("ix_camera_placements_plan_id", table_name="camera_placements")
    op.drop_table("camera_placements")
    op.drop_table("floor_plans")
    for name in ("response_notes", "responsible_contact", "specifications", "model", "manufacturer"):
        op.drop_column("cameras", name)
