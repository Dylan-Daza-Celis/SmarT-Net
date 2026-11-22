from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator
from sqlalchemy import select, func
from . import database, lifecycle as service
from .operational_metrics import details
from .models import User, Incident, AssignmentHistory, IncidentHistory, ResponseAction, IncidentReviewSignal, ReviewAcknowledgement, IncidentTimeEvidence
from .security import current_user, writers, administrators

router=APIRouter(tags=["Incident lifecycle"])


class AssignmentIn(service.LifecycleInput):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    assigned_to_id:str|None=Field(min_length=1,max_length=36)
    justification:str=Field(min_length=1,max_length=4000)
    expected_revision:int|None=Field(default=None,ge=0,strict=True)


class EvidenceIn(service.LifecycleInput):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    expected_revision:int=Field(ge=0,strict=True)
    source_kind:Literal["operational","laboratory","synthetic"]
    evidence_reference:str=Field(min_length=1,max_length=2000)
    review_note:str=Field(min_length=10,max_length=2000)
    occurred_at:AwareDatetime|None=None
    detected_at:AwareDatetime|None=None
    response_completed_at:AwareDatetime|None=None

    @model_validator(mode="after")
    def times(self):
        values=[t for t in (self.occurred_at,self.detected_at,self.response_completed_at) if t is not None]
        if not values or values!=sorted(values) or any(t>datetime.now(timezone.utc) for t in values):
            raise ValueError("Provide documented, nonfuture timestamps in chronological order")
        for field in ('occurred_at','detected_at','response_completed_at'):
            value=getattr(self,field)
            if value is not None:setattr(self,field,value.astimezone(timezone.utc))
        return self


class AckIn(service.LifecycleInput):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    expected_revision:int=Field(ge=0,strict=True)
    justification:str=Field(min_length=1,max_length=4000)


@router.get("/api/assignees")
def assignees(user:User=Depends(current_user)):
    with database.Session() as db:
        return [{"id":u.id,"username":u.username,"role":u.role} for u in db.scalars(select(User).where(
            User.active.is_(True),User.role.in_(["administrador","analista"])).order_by(User.username)).all()]


@router.patch("/api/incidents/{incident_id}/assignment")
def assign(incident_id:str,data:AssignmentIn,user:User=Depends(writers)):
    with database.Session.begin() as db:
        service.mutation_lock(db);actor=service.actor(db,user.id)
        inc=service.incident(db,incident_id,data.expected_revision)
        service.assign(db,inc,actor,data.assigned_to_id,data.justification)
        db.flush()
        return {"id":inc.id,"status":inc.status,**service.summary(db,inc)}


@router.get("/api/incidents/{incident_id}/lifecycle")
def lifecycle(incident_id:str,user:User=Depends(current_user)):
    with database.Session() as db:
        service.read_snapshot(db)
        inc=db.get(Incident,incident_id)
        if inc is None:raise HTTPException(404,"Incidente no encontrado")
        return {**service.summary(db,inc),**details(db,inc),"allowed_transitions":service.TRANSITIONS.get(inc.status,[])}


@router.get("/api/incidents/{incident_id}/timeline")
def timeline(incident_id:str,user:User=Depends(current_user)):
    with database.Session() as db:
        service.read_snapshot(db)
        if db.get(Incident,incident_id) is None:raise HTTPException(404,"Incidente no encontrado")
        names=dict(db.execute(select(User.id,User.username)).all())
        items=[]
        for h in db.scalars(select(IncidentHistory).where(IncidentHistory.incident_id==incident_id)).all():
            items.append({"id":h.id,"kind":"state","at":service.iso(h.created_at),"author_id":h.author_id,"author":names[h.author_id],
                "previous_status":h.previous_status,"status":h.status,"justification":h.justification,
                "cycle_number":h.cycle_number,"policy_version":h.policy_version})
        for h in db.scalars(select(AssignmentHistory).where(AssignmentHistory.incident_id==incident_id)).all():
            items.append({"id":h.id,"kind":"assignment","at":service.iso(h.created_at),"author_id":h.author_id,"author":names[h.author_id],
                "previous_user_id":h.previous_user_id,"assigned_user_id":h.assigned_user_id,
                "previous_assignee":names.get(h.previous_user_id),"assignee":names.get(h.assigned_user_id),
                "justification":h.justification,"cycle_number":h.cycle_number})
        for h in db.scalars(select(ResponseAction).where(ResponseAction.incident_id==incident_id)).all():
            items.append({"id":h.id,"kind":"action","at":service.iso(h.created_at),"author_id":h.author_id,"author":names[h.author_id],
                "description":h.description,"category":h.category or "legacy_unclassified",
                "performed_at":service.iso(h.performed_at),"date_basis":h.date_basis})
        for h in db.scalars(select(IncidentReviewSignal).where(IncidentReviewSignal.incident_id==incident_id)).all():
            ack=db.scalar(select(ReviewAcknowledgement).where(ReviewAcknowledgement.signal_id==h.id))
            items.append({"id":h.id,"kind":"review_signal","at":service.iso(h.created_at),"author_id":h.author_id,"author":names[h.author_id],
                "event_id":h.event_id,"reason":h.reason,"acknowledged":ack is not None})
            if ack:items.append({"id":ack.id,"kind":"review_acknowledgement","at":service.iso(ack.created_at),
                "author_id":ack.author_id,"author":names[ack.author_id],"signal_id":h.id,"justification":ack.justification})
        for h in db.scalars(select(IncidentTimeEvidence).where(IncidentTimeEvidence.incident_id==incident_id)).all():
            items.append({"id":h.id,"kind":"time_evidence","at":service.iso(h.created_at),"author_id":h.author_id,"author":names[h.author_id],
                "source_kind":h.source_kind,"evidence_reference":h.evidence_reference,"review_note":h.review_note,
                "occurred_at":service.iso(h.occurred_at),"detected_at":service.iso(h.detected_at),
                "response_completed_at":service.iso(h.response_completed_at),"cycle_number":h.cycle_number})
        return sorted(items,key=lambda h:(h['at'],h['kind'],h['id']))


@router.post("/api/incidents/{incident_id}/time-evidence",status_code=201)
def time_evidence(incident_id:str,data:EvidenceIn,user:User=Depends(administrators)):
    with database.Session.begin() as db:
        service.mutation_lock(db);actor=service.actor(db,user.id,admin=True)
        inc=service.incident(db,incident_id,data.expected_revision)
        evidence=IncidentTimeEvidence(incident_id=inc.id,author_id=actor.id,cycle_number=inc.cycle_number,
            created_at=service.now(),**data.model_dump(exclude={'expected_revision'}))
        db.add(evidence);inc.revision+=1;db.flush()
        return {"id":evidence.id,"revision":inc.revision,"metrics":details(db,inc)['metrics']}


@router.post("/api/incidents/{incident_id}/review-signals/{signal_id}/acknowledge",status_code=201)
def acknowledge(incident_id:str,signal_id:str,data:AckIn,user:User=Depends(writers)):
    with database.Session.begin() as db:
        service.mutation_lock(db);actor=service.actor(db,user.id)
        inc=service.incident(db,incident_id,data.expected_revision);service.owner_or_admin(inc,actor)
        signal=db.get(IncidentReviewSignal,signal_id)
        if signal is None or signal.incident_id!=inc.id:raise HTTPException(404,"Señal no encontrada")
        if db.scalar(select(ReviewAcknowledgement.id).where(ReviewAcknowledgement.signal_id==signal_id)):
            raise HTTPException(409,"Señal ya reconocida")
        db.add(ReviewAcknowledgement(signal_id=signal_id,author_id=actor.id,justification=data.justification,created_at=service.now()))
        inc.revision+=1;db.flush()
        return {"revision":inc.revision,"needs_review":service.needs_review(db,inc.id)}


@router.get("/api/operations/metrics")
def metrics(user:User=Depends(current_user)):
    with database.Session() as db:
        service.read_snapshot(db)
        incidents=db.scalars(select(Incident)).all()
        rows=[details(db,i)['metrics'] for i in incidents]
        result={}
        for key in ('time_to_assignment','time_to_response','time_to_resolution','mttd','mttr'):
            valid=[r[key]['value'] for r in rows if r[key]['value'] is not None]
            complete=bool(rows) and len(valid)==len(rows)
            result[key]={"value":sum(valid)/len(valid) if complete else None,"unit":"seconds",
                "status":"Calculable" if complete else "No calculable","valid":len(valid),"total":len(rows),
                "reason":None if complete else "Cohorte vacía o incompleta; no se promedia un subconjunto oculto"}
        return {"mean_intervals":result,"incidents":len(rows),"unassigned":sum(i.assigned_to_id is None for i in incidents),
                "needs_review":sum(service.needs_review(db,i.id) for i in incidents),
                "attribution":"Descriptive transaction/documentary data, not measured human performance"}
