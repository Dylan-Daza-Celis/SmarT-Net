"""Temporal correlation and append-only risk evaluations, preserving legacy rows."""
from uuid import uuid4
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    for column in (
        sa.Column("correlation_version", sa.String(40)),
        sa.Column("source_ip", sa.String(45)),
        sa.Column("window_start", sa.DateTime(timezone=True)),
        sa.Column("window_seconds", sa.Integer),
        sa.Column("risk_parameters", sa.Text),
    ):
        op.add_column("incidents", column)
    # Original uniqueness is an index (unique=True,index=True), not a table constraint.
    op.drop_index("ix_incidents_correlation_key", table_name="incidents")
    op.create_index("ix_incidents_correlation_key", "incidents", ["correlation_key"])
    # A unique index also works on SQLite without rebuilding the incidents table.
    op.create_index("uq_incident_window", "incidents", ["correlation_key", "window_start", "window_seconds"], unique=True)
    table = op.create_table("risk_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("event_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_risk_evaluations_incident_id", "risk_evaluations", ["incident_id"])
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT i.id,i.score,i.priority,i.explanation, (SELECT count(*) FROM events e WHERE e.incident_id=i.id) AS n FROM incidents i")).mappings()
    for row in rows:
        connection.execute(table.insert().values(id=str(uuid4()), incident_id=row["id"],
            algorithm_version="legacy-unknown", explanation=row["explanation"], score=row["score"],
            priority=row["priority"], event_count=row["n"], created_at=datetime.now(timezone.utc)))


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore backup")
