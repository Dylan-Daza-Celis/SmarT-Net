from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, CheckConstraint, Index, false
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(100))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    destination_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60))
    severity: Mapped[int] = mapped_column(Integer)
    asset_criticality: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    raw_event: Mapped[str] = mapped_column(Text)
    asset_criticality_observed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    adapter_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)

class EventEvidence(Base):
    __tablename__ = "event_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    import_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    sensor_id: Mapped[str] = mapped_column(String(100))
    line_number: Mapped[int] = mapped_column(Integer)
    raw_line: Mapped[str] = mapped_column(Text)
    raw_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("uq_incident_window", "correlation_key", "window_start", "window_seconds", unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    correlation_key: Mapped[str] = mapped_column(String(255), index=True)
    correlation_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(60))
    destination_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="Nuevo")
    score: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[str] = mapped_column(String(16), default="Baja")
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cycle_number: Mapped[int] = mapped_column(Integer, default=1, server_default="0")
    lifecycle_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events: Mapped[list[Event]] = relationship()

class RiskEvaluation(Base):
    __tablename__ = "risk_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    algorithm_version: Mapped[str] = mapped_column(String(40))
    explanation: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(16))
    event_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('administrador','analista','observador')", name="valid_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    eve_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class IncidentHistory(Base):
    __tablename__ = "incident_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    previous_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    justification: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    policy_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cycle_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

class ResponseAction(Base):
    __tablename__ = "response_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    category: Mapped[str | None] = mapped_column(String(24), nullable=True)
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_basis: Mapped[str | None] = mapped_column(String(24), nullable=True)

class AssignmentHistory(Base):
    __tablename__ = "assignment_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    previous_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    justification: Mapped[str] = mapped_column(Text)
    cycle_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class IncidentReviewSignal(Base):
    __tablename__ = "incident_review_signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), unique=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class ReviewAcknowledgement(Base):
    __tablename__ = "review_acknowledgements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    signal_id: Mapped[str] = mapped_column(ForeignKey("incident_review_signals.id"), unique=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    justification: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class IncidentTimeEvidence(Base):
    __tablename__ = "incident_time_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    cycle_number: Mapped[int] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(24))
    evidence_reference: Mapped[str] = mapped_column(Text)
    review_note: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    data_kind: Mapped[str] = mapped_column(String(20))
    configuration: Mapped[str] = mapped_column(Text)
    feature_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (Index("uq_evaluation_case_key", "dataset_id", "case_key", unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("evaluation_datasets.id"), index=True)
    case_key: Mapped[str] = mapped_column(String(36))
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    features: Mapped[str] = mapped_column(Text)

class EvaluationReference(Base):
    __tablename__ = "evaluation_references"
    case_id: Mapped[str] = mapped_column(ForeignKey("evaluation_cases.id"), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)

class EvaluationEventLink(Base):
    __tablename__ = "evaluation_event_links"
    case_id: Mapped[str] = mapped_column(ForeignKey("evaluation_cases.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)

class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("evaluation_datasets.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    configuration: Mapped[str] = mapped_column(Text)
    rankings: Mapped[str] = mapped_column(Text)
    results: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class MLRun(Base):
    __tablename__ = "ml_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("evaluation_datasets.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30))
    configuration: Mapped[str] = mapped_column(Text)
    artifacts: Mapped[str] = mapped_column(Text)
    results: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RiskReassessment(Base):
    __tablename__ = "risk_reassessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("risk_evaluations.id"), unique=True)
    justification: Mapped[str] = mapped_column(Text)
    previous_revision: Mapped[int] = mapped_column(Integer)
    resulting_revision: Mapped[int] = mapped_column(Integer)
    cycle_number: Mapped[int] = mapped_column(Integer)
    signal_ids: Mapped[str] = mapped_column(Text)
    event_ids: Mapped[str] = mapped_column(Text)
    parameters: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalyticsReport(Base):
    __tablename__ = "analytics_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))


class RiskReassessmentSignal(Base):
    __tablename__ = "risk_reassessment_signals"
    signal_id: Mapped[str] = mapped_column(ForeignKey("incident_review_signals.id"), primary_key=True)
    reassessment_id: Mapped[str] = mapped_column(ForeignKey("risk_reassessments.id"), index=True)
