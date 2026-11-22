from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, CheckConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(100))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    destination_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60))
    severity: Mapped[int] = mapped_column(Integer)
    asset_criticality: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    raw_event: Mapped[str] = mapped_column(Text)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
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

class ResponseAction(Base):
    __tablename__ = "response_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
