"""SmartIR-Net: prototipo inicial de ingestión, correlación y riesgo.
Uso exclusivo en laboratorios autorizados. Autenticación y permisos en backend.
"""
import json

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from .models import Event, Incident, User, IncidentHistory, ResponseAction, RiskEvaluation, EventEvidence
from .database import Session
from .schemas import EventIn, BatchIn
from .ingestion import ingest, ImportRecord
from . import eve_import
from .security import current_user, writers, administrators, password_hasher, issue_token
from fastapi import Depends
from typing import Literal
from argon2.exceptions import VerificationError, InvalidHashError

app = FastAPI(title="SmartIR-Net API", version="0.5.0", description="Gestión de incidentes con autenticación y roles")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization"])

def serialize(inc: Incident, count: int | None = None):
    return {"source_ip": inc.source_ip, "correlation_version": inc.correlation_version or "legacy",
            "window_start": inc.window_start.isoformat() if inc.window_start else None,
            "window_seconds": inc.window_seconds,
            "id": inc.id, "event_type": inc.event_type, "destination_ip": inc.destination_ip, "status": inc.status, "score": inc.score, "priority": inc.priority, "explanation": json.loads(inc.explanation or "{}"), "event_count": count if count is not None else len(inc.events), "created_at": inc.created_at.isoformat()}

@app.get("/health")
def health():
    return {"status": "ok", "service": "smartir-net"}

@app.post("/api/events/import")
def import_events(batch: BatchIn, user: User = Depends(writers)):
    return ingest([ImportRecord(event=item) for item in batch.events], user.id, Session)

@app.get("/api/incidents")
def list_incidents(user: User = Depends(current_user)):
    with Session() as db:
        incidents = db.scalars(select(Incident).order_by(Incident.score.desc(), Incident.created_at.desc())).all()
        return [serialize(i) for i in incidents]

@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str, user: User = Depends(current_user)):
    with Session() as db:
        inc = db.get(Incident, incident_id)
        if not inc:
            raise HTTPException(status_code=404, detail="Incidente no encontrado")
        result = serialize(inc)
        result["events"] = [{"id": e.id, "source": e.source, "event_timestamp": e.event_timestamp.isoformat(), "source_ip": e.source_ip, "message": e.message, "severity": e.severity, "asset_criticality": e.asset_criticality, "asset_criticality_observed": e.asset_criticality_observed, "adapter_metadata": json.loads(e.adapter_metadata) if e.adapter_metadata else None} for e in inc.events]
        return result

@app.get("/api/stats")
def stats(user: User = Depends(current_user)):
    with Session() as db:
        total_events = db.scalar(select(func.count()).select_from(Event))
        incidents = db.scalars(select(Incident)).all()
        return {"events": total_events, "incidents": len(incidents), "critical": sum(i.priority == "Crítica" for i in incidents), "high": sum(i.priority == "Alta" for i in incidents)}


Role = Literal["administrador", "analista", "observador"]
Status = Literal["Nuevo", "Asignado", "En análisis", "En respuesta", "Resuelto", "Cerrado"]

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)

class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Role

class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)

class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Status
    justification: str = Field(min_length=1, max_length=4000)

class ActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=4000)

def user_out(user):
    return {"id": user.id, "username": user.username, "role": user.role, "active": user.active}

@app.post("/api/auth/login")
def login(data: LoginIn):
    from .security import DUMMY_HASH
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.username == data.username))
        try:
            password_hasher.verify(user.password_hash if user else DUMMY_HASH, data.password)
        except (VerificationError, InvalidHashError):
            raise HTTPException(401, "Credenciales inválidas", headers={"WWW-Authenticate": "Bearer"})
        if user is None or not user.active:
            raise HTTPException(401, "Credenciales inválidas")
        if password_hasher.check_needs_rehash(user.password_hash):
            user.password_hash = password_hasher.hash(data.password)
        return {"access_token": issue_token(user), "token_type": "bearer", "expires_in": 900}

@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)

@app.get("/api/users")
def list_users(user: User = Depends(administrators)):
    with Session() as db:
        return [user_out(u) for u in db.scalars(select(User).order_by(User.username)).all()]

@app.post("/api/users", status_code=201)
def create_user(data: UserIn, user: User = Depends(administrators)):
    try:
        with Session.begin() as db:
            created = User(username=data.username, password_hash=password_hasher.hash(data.password), role=data.role)
            db.add(created)
            db.flush()
            result = user_out(created)
        return result
    except IntegrityError:
        raise HTTPException(409, "El usuario ya existe")

@app.patch("/api/users/{user_id}")
def update_user(user_id: str, data: UserPatch, user: User = Depends(administrators)):
    with Session.begin() as db:
        target = db.get(User, user_id)
        if target is None:
            raise HTTPException(404, "Usuario no encontrado")
        if user.id == user_id and (data.active is False or data.role not in (None, "administrador")):
            raise HTTPException(409, "No puede retirar su propio acceso administrativo")
        for field in ("role", "active"):
            if getattr(data, field) is not None:
                setattr(target, field, getattr(data, field))
        if data.password is not None:
            target.password_hash = password_hasher.hash(data.password)
        db.flush()
        return user_out(target)

@app.patch("/api/incidents/{incident_id}/status")
def change_status(incident_id: str, data: StatusIn, user: User = Depends(writers)):
    with Session.begin() as db:
        inc = db.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
        if inc is None:
            raise HTTPException(404, "Incidente no encontrado")
        if inc.status == data.status:
            raise HTTPException(409, "El incidente ya tiene ese estado")
        db.add(IncidentHistory(incident_id=inc.id, author_id=user.id, previous_status=inc.status, status=data.status, justification=data.justification))
        inc.status = data.status
        db.flush()
        return serialize(inc)

@app.get("/api/incidents/{incident_id}/history")
def history(incident_id: str, user: User = Depends(current_user)):
    with Session() as db:
        if db.get(Incident, incident_id) is None:
            raise HTTPException(404, "Incidente no encontrado")
        rows = db.execute(select(IncidentHistory, User.username).join(User, User.id == IncidentHistory.author_id).where(IncidentHistory.incident_id == incident_id).order_by(IncidentHistory.created_at, IncidentHistory.id)).all()
        return [{"id": h.id, "author_id": h.author_id, "author": name, "previous_status": h.previous_status, "status": h.status, "justification": h.justification, "created_at": h.created_at.isoformat()} for h, name in rows]

@app.post("/api/incidents/{incident_id}/actions", status_code=201)
def add_action(incident_id: str, data: ActionIn, user: User = Depends(writers)):
    with Session.begin() as db:
        if db.get(Incident, incident_id) is None:
            raise HTTPException(404, "Incidente no encontrado")
        action = ResponseAction(incident_id=incident_id, author_id=user.id, description=data.description)
        db.add(action)
        db.flush()
        return {"id": action.id, "incident_id": incident_id, "author_id": user.id, "description": action.description, "created_at": action.created_at.isoformat()}

@app.get("/api/incidents/{incident_id}/actions")
def actions(incident_id: str, user: User = Depends(current_user)):
    with Session() as db:
        if db.get(Incident, incident_id) is None:
            raise HTTPException(404, "Incidente no encontrado")
        rows = db.execute(select(ResponseAction, User.username).join(User, User.id == ResponseAction.author_id).where(ResponseAction.incident_id == incident_id).order_by(ResponseAction.created_at, ResponseAction.id)).all()
        return [{"id": a.id, "incident_id": a.incident_id, "author_id": a.author_id, "author": name, "description": a.description, "created_at": a.created_at.isoformat()} for a, name in rows]


@app.get("/api/incidents/{incident_id}/evaluations")
def evaluations(incident_id: str, user: User = Depends(current_user)):
    with Session() as db:
        if db.get(Incident, incident_id) is None:
            raise HTTPException(404, "Incident not found")
        rows = db.scalars(select(RiskEvaluation).where(RiskEvaluation.incident_id == incident_id).order_by(RiskEvaluation.created_at, RiskEvaluation.id)).all()
        return [{"id": row.id, "algorithm_version": row.algorithm_version, "score": row.score,
                 "priority": row.priority, "event_count": row.event_count,
                 "explanation": json.loads(row.explanation or "{}"), "created_at": row.created_at.isoformat()} for row in rows]


@app.post("/api/events/import/eve", responses={413: {"description": "Import limit; partial report"}})
async def import_eve(request: Request, filename: str = Query(default="eve.json", min_length=1, max_length=255, pattern=r"^[^\x00-\x1f]+$"),
                     sensor_id: str = Query(default="suricata", min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.:-]+$"),
                     user: User = Depends(writers)):
    # Raw file body avoids multipart spooling before application size validation.
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in ("application/x-ndjson", "application/jsonl", "application/octet-stream", "application/json", "text/plain"):
        raise HTTPException(415, "Send a UTF-8 JSON Lines file as the request body")
    report = await eve_import.import_stream(request.stream(), author_id=user.id, sensor_id=sensor_id,
                                           filename=filename, session_factory=Session)
    return JSONResponse(report, status_code=200 if report["complete"] else 413)


@app.get("/api/events/{event_id}")
def event_detail(event_id: str, user: User = Depends(current_user)):
    with Session() as db:
        event = db.get(Event, event_id)
        if event is None:
            raise HTTPException(404, "Event not found")
        return {"id": event.id, "incident_id": event.incident_id, "source": event.source,
                "event_timestamp": event.event_timestamp.isoformat(), "event_type": event.event_type,
                "source_ip": event.source_ip, "destination_ip": event.destination_ip,
                "severity": event.severity, "asset_criticality": event.asset_criticality,
                "asset_criticality_observed": event.asset_criticality_observed,
                "adapter_metadata": json.loads(event.adapter_metadata) if event.adapter_metadata else None,
                "raw_event": event.raw_event, "fingerprint": event.fingerprint}


@app.get("/api/events/{event_id}/evidence")
def event_evidence(event_id: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
                   user: User = Depends(current_user)):
    with Session() as db:
        if db.get(Event, event_id) is None:
            raise HTTPException(404, "Event not found")
        records = db.scalars(select(EventEvidence).where(EventEvidence.event_id == event_id)
            .order_by(EventEvidence.created_at, EventEvidence.id).offset(offset).limit(limit)).all()
        return [{"id": e.id, "author_id": e.author_id, "import_id": e.import_id, "filename": e.filename,
                 "sensor_id": e.sensor_id, "line_number": e.line_number, "raw_line": e.raw_line,
                 "raw_sha256": e.raw_sha256, "created_at": e.created_at.isoformat()} for e in records]

from .evaluation_api import router as evaluation_router
app.include_router(evaluation_router)
