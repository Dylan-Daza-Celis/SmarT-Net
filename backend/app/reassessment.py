"""Explicit, append-only reevaluation after closed-case evidence and reopening."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from . import database, lifecycle
from .security import writers
from .models import User, Event, IncidentHistory, RiskEvaluation, RiskReassessment, RiskReassessmentSignal
from .risk import evaluate
from .risk_audit import pending_query

router = APIRouter(tags=["Explicit risk reassessment"])


class ReassessmentIn(lifecycle.LifecycleInput):
    expected_revision: int | None = Field(default=None, ge=0, strict=True)
    justification: str = Field(min_length=1, max_length=4000)


@router.post("/api/incidents/{incident_id}/reevaluate", status_code=201)
def reevaluate(incident_id: str, data: ReassessmentIn, user: User = Depends(writers)):
    with database.Session.begin() as db:
        lifecycle.mutation_lock(db)
        actor = lifecycle.actor(db, user.id)
        inc = lifecycle.incident(db, incident_id, data.expected_revision)
        lifecycle.owner_or_admin(inc, actor)
        lifecycle.eligible(db, inc.assigned_to_id)
        reopened = db.scalar(select(IncidentHistory.id).where(IncidentHistory.incident_id == inc.id,
            IncidentHistory.previous_status == "Cerrado", IncidentHistory.status == "En análisis",
            IncidentHistory.policy_version.is_not(None)))
        if inc.status not in ("En análisis", "En respuesta") or reopened is None:
            raise HTTPException(409, "Requiere reapertura explícita de Cerrado y estado de trabajo activo")
        fresh = sorted(db.scalars(pending_query(inc.id)).all())
        if not fresh:
            raise HTTPException(409, "No hay nueva evidencia recibida durante cierre pendiente de reevaluación explícita")
        if inc.risk_parameters is None:
            raise HTTPException(409, "Incidente heredado sin parámetros congelados; no se inventan")
        events = db.scalars(select(Event).where(Event.incident_id == inc.id).order_by(Event.id)).all()
        try:
            params = json.loads(inc.risk_parameters)
            explanation = evaluate(events, params)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            raise HTTPException(409, "Parámetros congelados no compatibles; se conserva evaluación previa")
        timestamp = lifecycle.now()
        result = RiskEvaluation(incident_id=inc.id, algorithm_version=explanation["algorithm_version"],
            explanation=json.dumps(explanation, ensure_ascii=False), score=explanation["score"],
            priority=explanation["priority"], event_count=len(events), created_at=timestamp)
        db.add(result); db.flush()
        audit = RiskReassessment(incident_id=inc.id, author_id=actor.id, evaluation_id=result.id,
            justification=data.justification, previous_revision=inc.revision, resulting_revision=inc.revision+1,
            cycle_number=inc.cycle_number, signal_ids=json.dumps(fresh), event_ids=json.dumps([e.id for e in events]),
            parameters=inc.risk_parameters, created_at=timestamp)
        inc.score, inc.priority, inc.explanation = result.score, result.priority, result.explanation
        inc.revision += 1
        db.add(audit); db.flush()
        db.add_all([RiskReassessmentSignal(signal_id=sid, reassessment_id=audit.id) for sid in fresh])
        return {"id": audit.id, "evaluation_id": result.id, "revision": inc.revision,
                "score": inc.score, "priority": inc.priority, "algorithm_version": result.algorithm_version}
