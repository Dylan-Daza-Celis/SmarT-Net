"""Add EVE evidence and provenance; preserve all prior rows and evaluations."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"


def upgrade():
    op.add_column("events", sa.Column("asset_criticality_observed", sa.Boolean, nullable=True))
    op.add_column("events", sa.Column("adapter_metadata", sa.Text, nullable=True))
    op.create_table("event_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("import_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sensor_id", sa.String(100), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("raw_line", sa.Text, nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_event_evidence_event_id", "event_evidence", ["event_id"])
    op.create_index("ix_event_evidence_import_id", "event_evidence", ["import_id"])


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore backup")
