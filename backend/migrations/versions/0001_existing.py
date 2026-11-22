"""Esquema original congelado; adopta instalaciones previas sin borrar datos."""
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None

def upgrade():
    metadata = sa.MetaData()
    sa.Table("incidents", metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("correlation_key", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("destination_ip", sa.String(45)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("events", metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fingerprint", sa.String(64), unique=True, index=True, nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_ip", sa.String(45)),
        sa.Column("destination_ip", sa.String(45)),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("severity", sa.Integer, nullable=False),
        sa.Column("asset_criticality", sa.Integer, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("raw_event", sa.Text, nullable=False),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), index=True, nullable=False))
    metadata.create_all(op.get_bind(), checkfirst=True)

def downgrade():
    raise RuntimeError("Downgrade destructivo deshabilitado; restaurar respaldo")
