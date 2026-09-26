"""Persist a redacted per-source adapter error category."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision="0002_camera_error_category";down_revision="0001_initial";branch_labels=None;depends_on=None
def upgrade():
    if "error_category" not in {c["name"] for c in inspect(op.get_bind()).get_columns("cameras")}:
        op.add_column("cameras",sa.Column("error_category",sa.String(48),nullable=False,server_default=""))
def downgrade():
    if "error_category" in {c["name"] for c in inspect(op.get_bind()).get_columns("cameras")}:
        op.drop_column("cameras","error_category")
