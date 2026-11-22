"""Usuarios, acciones e historial: cambios aditivos congelados."""
from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"

def upgrade():
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('administrador','analista','observador')", name="valid_role"))
    op.create_table("incident_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("previous_status", sa.String(24)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_incident_history_incident_id", "incident_history", ["incident_id"])
    op.create_table("response_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_response_actions_incident_id", "response_actions", ["incident_id"])

def downgrade():
    raise RuntimeError("Downgrade destructivo deshabilitado; restaurar respaldo")
