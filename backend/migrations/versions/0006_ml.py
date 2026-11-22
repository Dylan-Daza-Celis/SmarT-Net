"""Persist server-trained numeric models without changing operational tables."""
from alembic import op
import sqlalchemy as sa
revision = "0006"
down_revision = "0005"


def upgrade():
    op.create_table("ml_runs",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("dataset_id",sa.String(36),sa.ForeignKey("evaluation_datasets.id"),nullable=False),
        sa.Column("author_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("status",sa.String(30),nullable=False),
        sa.Column("configuration",sa.Text,nullable=False),
        sa.Column("artifacts",sa.Text,nullable=False),
        sa.Column("results",sa.Text,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_ml_runs_dataset_id","ml_runs",["dataset_id"])


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore backup")
