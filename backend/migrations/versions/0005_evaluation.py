"""Isolated, additive evaluation tables. No operational data changes."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"


def upgrade():
    op.create_table("evaluation_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("data_kind", sa.String(20), nullable=False),
        sa.Column("configuration", sa.Text, nullable=False),
        sa.Column("feature_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("evaluation_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("evaluation_datasets.id"), nullable=False),
        sa.Column("case_key", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id")),
        sa.Column("features", sa.Text, nullable=False))
    op.create_index("ix_evaluation_cases_dataset_id", "evaluation_cases", ["dataset_id"])
    op.create_index("uq_evaluation_case_key", "evaluation_cases", ["dataset_id", "case_key"], unique=True)
    op.create_table("evaluation_references",
        sa.Column("case_id", sa.String(36), sa.ForeignKey("evaluation_cases.id"), primary_key=True),
        sa.Column("payload", sa.Text, nullable=False))
    op.create_table("evaluation_event_links",
        sa.Column("case_id", sa.String(36), sa.ForeignKey("evaluation_cases.id"), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("events.id"), primary_key=True))
    op.create_table("experiments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("evaluation_datasets.id"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("configuration", sa.Text, nullable=False),
        sa.Column("rankings", sa.Text, nullable=False),
        sa.Column("results", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_experiments_dataset_id", "experiments", ["dataset_id"])


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore backup")
