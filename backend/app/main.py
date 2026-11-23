"""SmartIR-Net: prototipo inicial de ingestión, correlación y riesgo.
Uso exclusivo en laboratorios autorizados. Autenticación y permisos en backend.
"""
import json

from fastapi import FastAPI, HTTPException, Request, Query, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict, AwareDatetime
from sqlalchemy import select, func, case
from sqlalchemy.exc import IntegrityError, OperationalError

from .models import Event, Incident, User, IncidentHistory, ResponseAction, RiskEvaluation, EventEvidence
from .database import Session
from .schemas import EventIn, BatchIn
from .ingestion import ingest, ImportRecord
from . import eve_import, lifecycle
from .security import current_user, writers, administrators, password_hasher, issue_token
from fastapi import Depends
from typing import Literal
from argon2.exceptions import VerificationError, InvalidHashError
from .abuse import AbuseController, RequestGuard, importer, password_admin, analytics_reader
from .analytics import review_exists
from .risk_audit import pending_query
from .validation import SafeInput
from .web_session import COOKIE, browser_request, set_session, clear_session

app = FastAPI(title="SmartIR-Net API", version="0.9.0", description="Gestión de incidentes con autenticación y roles")
app.state.abuse = AbuseController()
app.add_middleware(RequestGuard)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization"], expose_headers=["Content-Disposition", "X-Content-SHA256", "Retry-After"])

@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse({'detail':[{'loc':e['loc'],'type':e['type'],'msg':'Entrada inválida'} for e in exc.errors()]},status_code=422)

@app.exception_handler(OperationalError)
async def database_error(request, exc):
    transient=getattr(exc.orig,'sqlstate',None) in ('57014','55P03') or 'locked' in str(exc.orig).lower()
    return JSONResponse({'detail':'Base de datos ocupada; reintente después' if transient else 'Error de almacenamiento'},
        status_code=503 if transient else 500,headers={'Retry-After':'1'} if transient else {})

def serialize(inc: Incident, db, count: int | None = None, metadata=None):
    return {**(lifecycle.summary(db,inc) if metadata is None else metadata), "source_ip": inc.source_ip, "correlation_version": inc.correlation_version or "legacy",
            "window_start": inc.window_start.isoformat() if inc.window_start else None,
            "window_seconds": inc.window_seconds,
            "id": inc.id, "event_type": inc.event_type, "destination_ip": inc.destination_ip, "status": inc.status, "score": inc.score, "priority": inc.priority, "explanation": json.loads(inc.explanation or "{}"), "event_count": count if count is not None else len(inc.events), "created_at": lifecycle.iso(inc.created_at)}

@app.get("/health")
def health():
    return {"status": "ok", "service": "smartir-net"}

@app.post("/api/events/import")
def import_events(batch: BatchIn, user: User = Depends(importer)):
    return ingest([ImportRecord(event=item) for item in batch.events], user.id, Session)

@app.get("/api/incidents")
def list_incidents(offset:int=Query(0,ge=0,le=100000),limit:int=Query(100,ge=1,le=1000),user: User = Depends(analytics_reader)):
    with Session() as db:
        lifecycle.read_snapshot(db)
        count=select(func.count()).select_from(Event).where(Event.incident_id==Incident.id).scalar_subquery()
        rows=db.execute(select(Incident,count,User.username,User.active,User.role,review_exists(),pending_query(Incident.id).exists())
            .outerjoin(User,User.id==Incident.assigned_to_id).order_by(Incident.score.desc(),Incident.created_at.desc(),Incident.id)
            .offset(offset).limit(limit)).all()
        return [serialize(i,db,n,{'revision':i.revision,'assigned_to_id':i.assigned_to_id,
            'assignee':None if i.assigned_to_id is None else {'id':i.assigned_to_id,'username':name,'active':active,'role':role},
            'needs_review':review,'risk_reevaluation_pending':pending,'lifecycle_legacy':i.lifecycle_started_at is None})
            for i,n,name,active,role,review,pending in rows]

@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str, events_offset:int=Query(0,ge=0,le=100000),events_limit:int=Query(100,ge=1,le=500),user: User = Depends(analytics_reader)):
    with Session() as db:
        lifecycle.read_snapshot(db)
        inc = db.get(Incident, incident_id)
        if not inc:
            raise HTTPException(status_code=404, detail="Incidente no encontrado")
        count=db.scalar(select(func.count()).select_from(Event).where(Event.incident_id==inc.id))
        result = serialize(inc,db,count)
        events=db.scalars(select(Event).where(Event.incident_id==inc.id).order_by(Event.id).offset(events_offset).limit(events_limit)).all()
        result.update(events_offset=events_offset,events_limit=events_limit)
        result["events"] = [{"id": e.id, "source": e.source, "event_timestamp": e.event_timestamp.isoformat(), "source_ip": e.source_ip, "message": e.message, "severity": e.severity, "asset_criticality": e.asset_criticality, "asset_criticality_observed": e.asset_criticality_observed, "adapter_metadata": json.loads(e.adapter_metadata) if e.adapter_metadata else None} for e in events]
        return result

@app.get("/api/stats")
def stats(user: User = Depends(analytics_reader)):
    with Session() as db:
        total_events = db.scalar(select(func.count()).select_from(Event))
        total,critical,high=db.execute(select(func.count(),func.count(case((Incident.priority=='Crítica',1))),
            func.count(case((Incident.priority=='Alta',1)))).select_from(Incident)).one()
        return {"events": total_events, "incidents": total, "critical": critical, "high": high}


Role = Literal["administrador", "analista", "observador"]
Status = Literal["Nuevo", "Asignado", "En análisis", "En respuesta", "Resuelto", "Cerrado"]

class LoginIn(SafeInput):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)

class UserIn(SafeInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Role
    eve_only: bool = Field(default=False, strict=True)

class UserPatch(SafeInput):
    model_config = ConfigDict(extra="forbid")
    role: Role | None = None
    active: bool | None = None
    eve_only: bool | None = Field(default=None, strict=True)
    password: str | None = Field(default=None, min_length=12, max_length=128)

class StatusIn(lifecycle.LifecycleInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int | None = Field(default=None, ge=0, strict=True)
    status: Status
    justification: str = Field(min_length=1, max_length=4000)

class ActionIn(lifecycle.LifecycleInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int | None = Field(default=None, ge=0, strict=True)
    category: Literal["comentario","contencion","erradicacion","recuperacion","verificacion"] = "comentario"
    performed_at: AwareDatetime | None = None
    description: str = Field(min_length=1, max_length=4000)

def user_out(user):
    return {"id": user.id, "username": user.username, "role": user.role, "active": user.active, "eve_only": user.eve_only}

@app.post("/api/auth/login")
def login(data: LoginIn, request: Request):
    from .security import DUMMY_HASH
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.username == data.username))
        with request.app.state.abuse.work('password'):
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


@app.post('/api/auth/session', tags=['Browser session'])
def create_web_session(data: LoginIn, request: Request, response: Response):
    from .security import decode_token
    browser_request(request, mutation=True)
    result = login(data, request)  # Same Argon2 verification and admission controls as Bearer login.
    payload = decode_token(result['access_token'])
    with Session() as db:
        user = db.get(User, payload['sub'])
        if user is None or not user.active:
            raise HTTPException(401, 'Sesión inválida o expirada')
        if user.eve_only:
            raise HTTPException(403, 'Cuenta exclusiva del agente EVE; no dispone de acceso interactivo')
        identity = user_out(user)
    set_session(response, request, result['access_token'])
    return {'user': identity, 'expires_at': payload['exp'], 'expires_in': 900}


@app.get('/api/auth/session', tags=['Browser session'])
def restore_web_session(request: Request, user: User = Depends(current_user)):
    from datetime import datetime, timezone
    from .security import decode_token
    # This endpoint restores a COOKIE session, never returns its JWT, never extends its lifetime.
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, 'No existe sesión web')
    import jwt
    try:
        payload = decode_token(token)
        if payload['sub'] != user.id:
            raise jwt.InvalidTokenError()
    except jwt.InvalidTokenError:
        raise HTTPException(401, 'Sesión inválida o expirada') from None
    return {'user': user_out(user), 'expires_at': payload['exp'],
            'expires_in': max(0, payload['exp']-int(datetime.now(timezone.utc).timestamp()))}


@app.delete('/api/auth/session', status_code=204, tags=['Browser session'])
def end_web_session(request: Request, response: Response):
    browser_request(request, mutation=True)
    clear_session(response, request)

@app.get("/api/users")
def list_users(user: User = Depends(administrators)):
    with Session() as db:
        return [user_out(u) for u in db.scalars(select(User).order_by(User.username)).all()]

@app.post("/api/users", status_code=201)
def create_user(data: UserIn, user: User = Depends(password_admin)):
    if data.eve_only and data.role != 'analista':
        raise HTTPException(422, 'Una cuenta solo EVE requiere rol analista')
    try:
        with Session.begin() as db:
            created = User(username=data.username, password_hash=password_hasher.hash(data.password), role=data.role, eve_only=data.eve_only)
            lifecycle.mutation_lock(db)
            lifecycle.actor(db,user.id,admin=True)
            db.add(created)
            db.flush()
            result = user_out(created)
        return result
    except IntegrityError:
        raise HTTPException(409, "El usuario ya existe")

@app.patch("/api/users/{user_id}")
def update_user(user_id: str, data: UserPatch, user: User = Depends(password_admin)):
    new_hash=password_hasher.hash(data.password) if data.password is not None else None
    with Session.begin() as db:
        lifecycle.mutation_lock(db)
        lifecycle.actor(db,user.id,admin=True)
        target = db.get(User, user_id)
        if target is None:
            raise HTTPException(404, "Usuario no encontrado")
        if user.id == user_id and (data.active is False or data.role not in (None, "administrador")):
            raise HTTPException(409, "No puede retirar su propio acceso administrativo")
        if (target.eve_only if data.eve_only is None else data.eve_only) and (data.role or target.role) != 'analista':
            raise HTTPException(422, 'Una cuenta solo EVE requiere rol analista')
        if data.active is False or data.role == "observador" or data.eve_only is True:
            if db.scalar(select(Incident.id).where(Incident.assigned_to_id==user_id,Incident.status!="Cerrado").limit(1)):
                raise HTTPException(409,"Reasigne los incidentes abiertos antes de retirar este responsable activo")
        for field in ("role", "active", "eve_only"):
            if getattr(data, field) is not None:
                setattr(target, field, getattr(data, field))
        if data.password is not None:
            target.password_hash = new_hash
        db.flush()
        return user_out(target)

@app.patch("/api/incidents/{incident_id}/status")
def change_status(incident_id: str, data: StatusIn, user: User = Depends(writers)):
    with Session.begin() as db:
        lifecycle.mutation_lock(db)
        actor=lifecycle.actor(db,user.id)
        inc=lifecycle.incident(db,incident_id,data.expected_revision)
        lifecycle.transition(db,inc,actor,data.status,data.justification)
        db.flush()
        return serialize(inc,db)

@app.get("/api/incidents/{incident_id}/history")
def history(incident_id: str, user: User = Depends(current_user)):
    with Session() as db:
        if db.get(Incident, incident_id) is None:
            raise HTTPException(404, "Incidente no encontrado")
        rows = db.execute(select(IncidentHistory, User.username).join(User, User.id == IncidentHistory.author_id).where(IncidentHistory.incident_id == incident_id).order_by(IncidentHistory.created_at, IncidentHistory.id)).all()
        return [{"id": h.id, "author_id": h.author_id, "author": name, "previous_status": h.previous_status, "status": h.status, "justification": h.justification, "created_at": lifecycle.iso(h.created_at)} for h, name in rows]

@app.post("/api/incidents/{incident_id}/actions", status_code=201)
def add_action(incident_id: str, data: ActionIn, user: User = Depends(writers)):
    with Session.begin() as db:
        lifecycle.mutation_lock(db)
        actor=lifecycle.actor(db,user.id)
        inc=lifecycle.incident(db,incident_id,data.expected_revision)
        if data.category!="comentario":
            lifecycle.owner_or_admin(inc,actor)
            lifecycle.eligible(db,inc.assigned_to_id)
            allowed=("En respuesta","Resuelto") if data.category=="verificacion" else ("En respuesta",)
            if inc.status not in allowed:raise HTTPException(409,"La categoria requiere un estado de respuesta compatible")
        timestamp=lifecycle.now()
        if data.performed_at and data.performed_at>timestamp:raise HTTPException(422,"La accion no puede tener fecha futura")
        action=ResponseAction(incident_id=incident_id,author_id=actor.id,description=data.description,
            category=data.category,performed_at=lifecycle.utc(data.performed_at) if data.performed_at else timestamp,
            date_basis="declared" if data.performed_at else "recorded_at",created_at=timestamp)
        db.add(action);inc.revision+=1;db.flush()
        return {"id":action.id,"incident_id":inc.id,"author_id":actor.id,"description":action.description,
            "category":action.category,"performed_at":lifecycle.iso(action.performed_at),
            "date_basis":action.date_basis,"created_at":lifecycle.iso(action.created_at),"revision":inc.revision}

@app.get("/api/incidents/{incident_id}/actions")
def actions(incident_id: str, user: User = Depends(current_user)):
    with Session() as db:
        if db.get(Incident, incident_id) is None:
            raise HTTPException(404, "Incidente no encontrado")
        rows = db.execute(select(ResponseAction, User.username).join(User, User.id == ResponseAction.author_id).where(ResponseAction.incident_id == incident_id).order_by(ResponseAction.created_at, ResponseAction.id)).all()
        return [{"id": a.id, "incident_id": a.incident_id, "author_id": a.author_id, "author": name, "description": a.description, "category": a.category or "legacy_unclassified", "performed_at": lifecycle.iso(a.performed_at), "date_basis": a.date_basis, "created_at": lifecycle.iso(a.created_at)} for a, name in rows]


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
                     user: User = Depends(importer)):
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

from .ml_api import router as ml_router
app.include_router(ml_router)

from .lifecycle_api import router as lifecycle_router
app.include_router(lifecycle_router)

from .reassessment import router as reassessment_router
app.include_router(reassessment_router)

from .analytics_api import router as analytics_router
app.include_router(analytics_router)
