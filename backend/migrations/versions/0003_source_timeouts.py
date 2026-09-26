"""Store per-source decoder timeout and reconnect bounds."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision="0003_source_timeouts";down_revision="0002_camera_error_category";branch_labels=None;depends_on=None
def upgrade():
    names={c["name"] for c in inspect(op.get_bind()).get_columns("cameras")}
    for name,value in (("timeout_seconds","5"),("reconnect_min_seconds","1"),("reconnect_max_seconds","30")):
        if name not in names:op.add_column("cameras",sa.Column(name,sa.Integer(),nullable=False,server_default=value))
def downgrade():
    names={c["name"] for c in inspect(op.get_bind()).get_columns("cameras")}
    for name in ("reconnect_max_seconds","reconnect_min_seconds","timeout_seconds"):
        if name in names:op.drop_column("cameras",name)
