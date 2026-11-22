"""Add auditable lifecycle data without rewriting historical states or times."""
from alembic import op
import sqlalchemy as sa
revision = "0007"
down_revision = "0006"


def upgrade():
    # Inline nullable FK works on PostgreSQL and SQLite without table reconstruction.
    op.execute("ALTER TABLE incidents ADD COLUMN assigned_to_id VARCHAR(36) REFERENCES users(id)")
    op.create_index("ix_incidents_assigned_to_id","incidents",["assigned_to_id"])
    op.add_column("incidents",sa.Column("revision",sa.Integer,nullable=False,server_default="0"))
    op.add_column("incidents",sa.Column("cycle_number",sa.Integer,nullable=False,server_default="0"))
    op.add_column("incidents",sa.Column("lifecycle_started_at",sa.DateTime(timezone=True)))
    op.add_column("incident_history",sa.Column("policy_version",sa.String(30)))
    op.add_column("incident_history",sa.Column("cycle_number",sa.Integer))
    for col in (sa.Column("category",sa.String(24)),sa.Column("performed_at",sa.DateTime(timezone=True)),sa.Column("date_basis",sa.String(24))):
        op.add_column("response_actions",col)
    op.create_table("assignment_history",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("incident_id",sa.String(36),sa.ForeignKey("incidents.id"),nullable=False),
        sa.Column("author_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("previous_user_id",sa.String(36),sa.ForeignKey("users.id")),
        sa.Column("assigned_user_id",sa.String(36),sa.ForeignKey("users.id")),
        sa.Column("justification",sa.Text,nullable=False),sa.Column("cycle_number",sa.Integer,nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("incident_review_signals",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("incident_id",sa.String(36),sa.ForeignKey("incidents.id"),nullable=False),
        sa.Column("event_id",sa.String(36),sa.ForeignKey("events.id"),unique=True,nullable=False),
        sa.Column("author_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("reason",sa.Text,nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("review_acknowledgements",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("signal_id",sa.String(36),sa.ForeignKey("incident_review_signals.id"),unique=True,nullable=False),
        sa.Column("author_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("justification",sa.Text,nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("incident_time_evidence",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("incident_id",sa.String(36),sa.ForeignKey("incidents.id"),nullable=False),
        sa.Column("author_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("cycle_number",sa.Integer,nullable=False),sa.Column("source_kind",sa.String(24),nullable=False),
        sa.Column("evidence_reference",sa.Text,nullable=False),sa.Column("review_note",sa.Text,nullable=False),
        sa.Column("occurred_at",sa.DateTime(timezone=True)),sa.Column("detected_at",sa.DateTime(timezone=True)),
        sa.Column("response_completed_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    for table in ("assignment_history","incident_review_signals","incident_time_evidence"):
        op.create_index("ix_"+table+"_incident_id",table,["incident_id"])


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore backup")
