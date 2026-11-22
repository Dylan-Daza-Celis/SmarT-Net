"""SmartIR-Net: prototipo inicial de ingestión, correlación y riesgo.
Uso exclusivo en laboratorios autorizados. No ofrece autenticación todavía.
"""
import os
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, String, DateTime, Integer, ForeignKey, Text, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./smartir.db")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
Session = sessionmaker(bind=engine)

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
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    correlation_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    destination_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="Nuevo")
    score: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[str] = mapped_column(String(16), default="Baja")
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    events: Mapped[list[Event]] = relationship()

class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=100)
    event_timestamp: datetime
    source_ip: str | None = None
    destination_ip: str | None = None
    event_type: str = Field(min_length=1, max_length=60)
    severity: int = Field(ge=0, le=100)
    asset_criticality: int = Field(default=50, ge=0, le=100)
    message: str = Field(default="", max_length=2000)

class BatchIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=1000)

app = FastAPI(title="SmartIR-Net API", version="0.1.0", description="Prototipo académico: sin autenticación; uso local exclusivamente")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

@app.on_event("startup")
def setup():
    Base.metadata.create_all(engine)

ATTACK_WEIGHT = {"acceso_no_autorizado": 75, "malware": 90, "dos": 80, "escaneo": 45, "uso_indebido": 55, "exfiltracion": 100}

def score_incident(events: list[Event]):
    max_severity = max(e.severity for e in events)
    max_asset = max(e.asset_criticality for e in events)
    recurrence = min(100, len(events) * 20)
    attack = ATTACK_WEIGHT.get(events[0].event_type, 40)
    context = 50  # neutral provisional; reemplazar por contexto documentado
    score = round(0.35 * max_severity + 0.25 * max_asset + 0.15 * recurrence + 0.15 * attack + 0.10 * context)
    priority = "Crítica" if score >= 75 else "Alta" if score >= 50 else "Media" if score >= 25 else "Baja"
    reasons = {"severidad": max_severity, "criticidad_activo": max_asset, "recurrencia": recurrence, "tipo_ataque": attack, "contexto": context, "eventos": len(events)}
    return score, priority, json.dumps(reasons, ensure_ascii=False)

def serialize(inc: Incident, count: int | None = None):
    return {"id": inc.id, "event_type": inc.event_type, "destination_ip": inc.destination_ip, "status": inc.status, "score": inc.score, "priority": inc.priority, "explanation": json.loads(inc.explanation or "{}"), "event_count": count if count is not None else len(inc.events), "created_at": inc.created_at.isoformat()}

@app.get("/health")
def health():
    return {"status": "ok", "service": "smartir-net"}

@app.post("/api/events/import")
def import_events(batch: BatchIn):
    created, duplicates = 0, 0
    affected = set()
    with Session.begin() as db:
        for item in batch.events:
            raw = item.model_dump(mode="json")
            fp = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
            if db.scalar(select(Event.id).where(Event.fingerprint == fp)):
                duplicates += 1
                continue
            # Correlación MVP: mismo tipo y destino; no implica correlación temporal.
            # Se sustituirá por ventanas temporales configurables en la siguiente versión.
            key = f"{item.event_type}|{item.destination_ip or 'sin-destino'}"
            inc = db.scalar(select(Incident).where(Incident.correlation_key == key))
            if inc is None:
                inc = Incident(correlation_key=key, event_type=item.event_type, destination_ip=item.destination_ip)
                db.add(inc)
                db.flush()
            timestamp = item.event_timestamp.astimezone(timezone.utc)
            ev = Event(fingerprint=fp, source=item.source, event_timestamp=timestamp, source_ip=item.source_ip, destination_ip=item.destination_ip, event_type=item.event_type, severity=item.severity, asset_criticality=item.asset_criticality, message=item.message, raw_event=json.dumps(raw, ensure_ascii=False), incident_id=inc.id)
            db.add(ev)
            created += 1
            affected.add(inc.id)
        db.flush()
        for inc_id in affected:
            inc = db.get(Incident, inc_id)
            evs = db.scalars(select(Event).where(Event.incident_id == inc_id)).all()
            inc.score, inc.priority, inc.explanation = score_incident(evs)
    return {"imported": created, "duplicates": duplicates, "incidents_updated": len(affected)}

@app.get("/api/incidents")
def list_incidents():
    with Session() as db:
        incidents = db.scalars(select(Incident).order_by(Incident.score.desc(), Incident.created_at.desc())).all()
        return [serialize(i) for i in incidents]

@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    with Session() as db:
        inc = db.get(Incident, incident_id)
        if not inc:
            raise HTTPException(status_code=404, detail="Incidente no encontrado")
        result = serialize(inc)
        result["events"] = [{"id": e.id, "source": e.source, "event_timestamp": e.event_timestamp.isoformat(), "source_ip": e.source_ip, "message": e.message, "severity": e.severity} for e in inc.events]
        return result

@app.get("/api/stats")
def stats():
    with Session() as db:
        total_events = db.scalar(select(func.count()).select_from(Event))
        incidents = db.scalars(select(Incident)).all()
        return {"events": total_events, "incidents": len(incidents), "critical": sum(i.priority == "Crítica" for i in incidents), "high": sum(i.priority == "Alta" for i in incidents)}
