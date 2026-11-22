"""State machine and shared mutation lock; no network response execution."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, text
from pydantic import BaseModel, ConfigDict, field_validator
from .models import User, Incident, IncidentHistory, AssignmentHistory, IncidentReviewSignal, ReviewAcknowledgement

VERSION="lifecycle-v1"
TRANSITIONS={"Nuevo":[],"Asignado":["En análisis"],"En análisis":["Asignado","En respuesta"],
             "En respuesta":["En análisis","Resuelto"],"Resuelto":["En análisis","Cerrado"],"Cerrado":["En análisis"]}


class LifecycleInput(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)

    @field_validator("*")
    @classmethod
    def safe_text(cls,value):
        if isinstance(value,str):
            if "\x00" in value:raise ValueError("NUL not supported")
            try:value.encode("utf-8")
            except UnicodeError:raise HTTPException(422,"Texto UTF-8 inválido")
        return value


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return utc(value).isoformat() if value else None


def mutation_lock(db):
    # Same lock as ingestion: serializes close/import, assignment/user-role changes.
    if db.bind.dialect.name=="postgresql":db.execute(text("SELECT pg_advisory_xact_lock(739031503)"))
    elif db.bind.dialect.name=="sqlite":db.execute(text("BEGIN IMMEDIATE"))


def read_snapshot(db):
    if db.bind.dialect.name=="postgresql":db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    elif db.bind.dialect.name=="sqlite":db.execute(text("BEGIN"))


def actor(db,actor_id,admin=False):
    user=db.get(User,actor_id)
    if user is None or not user.active:raise HTTPException(401,"Usuario inactivo")
    if user.role not in (("administrador",) if admin else ("administrador","analista")):
        raise HTTPException(403,"Permisos insuficientes")
    return user


def incident(db,incident_id,expected_revision):
    inc=db.scalar(select(Incident).where(Incident.id==incident_id).with_for_update())
    if inc is None:raise HTTPException(404,"Incidente no encontrado")
    if expected_revision is None:raise HTTPException(428,"Se requiere expected_revision; vuelva a consultar el incidente")
    if inc.revision!=expected_revision:raise HTTPException(409,"Revisión obsoleta; recargue el incidente")
    return inc


def eligible(db,user_id):
    user=db.get(User,user_id) if user_id else None
    if user is None or not user.active or user.role not in ("administrador","analista"):
        raise HTTPException(409,"El responsable debe ser un administrador o analista activo")
    return user


def owner_or_admin(inc,user):
    if user.role!="administrador" and inc.assigned_to_id!=user.id:
        raise HTTPException(403,"Solo el responsable actual o un administrador puede operar este incidente")


def state_record(db,inc,status,user_id,reason,timestamp):
    db.add(IncidentHistory(incident_id=inc.id,author_id=user_id,previous_status=inc.status,status=status,
        justification=reason,created_at=timestamp,policy_version=VERSION,cycle_number=inc.cycle_number))
    inc.status=status


def assign(db,inc,user,target,reason):
    if user.role!="administrador":
        if inc.status=="Cerrado":raise HTTPException(403,"Asignación de casos cerrados reservada al administrador")
        if inc.assigned_to_id is None:
            if target!=user.id:raise HTTPException(403,"Un analista solo puede tomar para sí un caso sin responsable")
        else:owner_or_admin(inc,user)
    if target==inc.assigned_to_id:raise HTTPException(409,"Asignación sin cambios")
    if target:eligible(db,target)
    if target is None and inc.status not in ("Asignado","Cerrado"):
        raise HTTPException(409,"Retire la asignación desde Asignado; un caso en trabajo debe volver antes a triage")
    timestamp=now()
    db.add(AssignmentHistory(incident_id=inc.id,author_id=user.id,previous_user_id=inc.assigned_to_id,
        assigned_user_id=target,justification=reason,created_at=timestamp,cycle_number=inc.cycle_number))
    inc.assigned_to_id=target
    if target and inc.status=="Nuevo":state_record(db,inc,"Asignado",user.id,reason,timestamp)
    elif target is None and inc.status=="Asignado":state_record(db,inc,"Nuevo",user.id,reason,timestamp)
    inc.revision+=1


def transition(db,inc,user,target,reason):
    owner_or_admin(inc,user)
    if target not in TRANSITIONS.get(inc.status,[]):raise HTTPException(409,"Transición no permitida")
    eligible(db,inc.assigned_to_id)
    if inc.status=="Cerrado" and user.role!="administrador":raise HTTPException(403,"Reapertura de Cerrado reservada al administrador")
    if inc.status in ("Resuelto","Cerrado") and target=="En análisis":
        inc.cycle_number+=1
    state_record(db,inc,target,user.id,reason,now())
    inc.revision+=1


def needs_review(db,incident_id):
    return db.scalar(select(IncidentReviewSignal.id).outerjoin(ReviewAcknowledgement,
        ReviewAcknowledgement.signal_id==IncidentReviewSignal.id).where(IncidentReviewSignal.incident_id==incident_id,
        ReviewAcknowledgement.id.is_(None)).limit(1)) is not None


def summary(db,inc):
    user=db.get(User,inc.assigned_to_id) if inc.assigned_to_id else None
    return {"revision":inc.revision,"assigned_to_id":inc.assigned_to_id,
            "assignee":None if user is None else {"id":user.id,"username":user.username,"active":user.active,"role":user.role},
            "needs_review":needs_review(db,inc.id),"lifecycle_legacy":inc.lifecycle_started_at is None}
