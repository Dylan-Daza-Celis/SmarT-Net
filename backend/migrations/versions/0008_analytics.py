"""Immutable analytical snapshots and explicit risk reassessment audit, additive."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"


def upgrade():
    op.create_table("risk_reassessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("evaluation_id", sa.String(36), sa.ForeignKey("risk_evaluations.id"), nullable=False, unique=True),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column("previous_revision", sa.Integer, nullable=False),
        sa.Column("resulting_revision", sa.Integer, nullable=False),
        sa.Column("cycle_number", sa.Integer, nullable=False),
        sa.Column("signal_ids", sa.Text, nullable=False),
        sa.Column("event_ids", sa.Text, nullable=False),
        sa.Column("parameters", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_risk_reassessments_incident_id", "risk_reassessments", ["incident_id"])
    op.create_table("risk_reassessment_signals",
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("incident_review_signals.id"), primary_key=True),
        sa.Column("reassessment_id", sa.String(36), sa.ForeignKey("risk_reassessments.id"), nullable=False))
    op.create_index("ix_risk_reassessment_signals_reassessment_id", "risk_reassessment_signals", ["reassessment_id"])
    op.create_table("analytics_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False))
    op.create_index("ix_analytics_reports_created_at", "analytics_reports", ["created_at"])
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])
    op.create_index("ix_events_received_at", "events", ["received_at"])


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore backup")
