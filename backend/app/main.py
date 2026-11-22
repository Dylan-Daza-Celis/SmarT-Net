"""SmartIR-Net: prototipo inicial de ingestión, correlación y riesgo.
Uso exclusivo en laboratorios autorizados. Autenticación y permisos en backend.
"""
import hashlib
import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from .models import Event, Incident, User, IncidentHistory, ResponseAction
from .database import Session
from .security import current_user, writers, administrators, password_hasher, issue_token
from fastapi import Depends
from typing import Literal
from argon2.exceptions import VerificationError, InvalidHashError

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

app = FastAPI(title="SmartIR-Net API", version="0.1.0", description="Gestión de incidentes con autenticación y roles")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization"])

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
def import_events(batch: BatchIn, user: User = Depends(writers)):
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
                db.add(IncidentHistory(incident_id=inc.id, author_id=user.id, status="Nuevo", justification="Creado por importación de eventos"))
            if item.event_timestamp.tzinfo is None:
                raise HTTPException(422, "event_timestamp requiere zona horaria")
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
        result["events"] = [{"id": e.id, "source": e.source, "event_timestamp": e.event_timestamp.isoformat(), "source_ip": e.source_ip, "message": e.message, "severity": e.severity} for e in inc.events]
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
