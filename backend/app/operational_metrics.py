"""Auditable intervals, never infer detection from event or reception time."""
from sqlalchemy import select
from .models import IncidentHistory, AssignmentHistory, IncidentTimeEvidence
from .lifecycle import utc, iso


def metric(start,end,reason):
    if start is None or end is None:
        return {"value":None,"unit":"seconds","status":"No calculable","reason":reason}
    delta=(utc(end)-utc(start)).total_seconds()
    if delta<0:return {"value":None,"unit":"seconds","status":"No calculable","reason":"Orden temporal inválido"}
    return {"value":delta,"unit":"seconds","status":"Calculable","reason":None}


def details(db,inc):
    history=db.scalars(select(IncidentHistory).where(IncidentHistory.incident_id==inc.id)
        .order_by(IncidentHistory.created_at,IncidentHistory.id)).all()
    assignments=db.scalars(select(AssignmentHistory).where(AssignmentHistory.incident_id==inc.id,
        AssignmentHistory.assigned_user_id.is_not(None)).order_by(AssignmentHistory.created_at,AssignmentHistory.id)).all()
    timestamps={}
    for label,state in (("analysis","En análisis"),("response","En respuesta"),("resolution","Resuelto"),("closure","Cerrado")):
        dates=[h.created_at for h in history if h.status==state]
        timestamps[label]={"first_recorded":iso(dates[0]) if dates else None,"latest_recorded":iso(dates[-1]) if dates else None}
    timestamps["assignment"]={"first_recorded":iso(assignments[0].created_at) if assignments else None,
                              "latest_recorded":iso(assignments[-1].created_at) if assignments else None}
    baseline=inc.lifecycle_started_at
    def first(state):
        return next((h.created_at for h in history if h.status==state),None)
    reason="Falta baseline de seguimiento completo o transición registrada; los datos heredados no se reconstruyen"
    result={"time_to_assignment":metric(baseline,assignments[0].created_at if assignments else None,reason),
            "time_to_response":metric(baseline,first("En respuesta"),reason),
            "time_to_resolution":metric(baseline,first("Resuelto"),reason)}
    evidence=db.scalar(select(IncidentTimeEvidence).where(IncidentTimeEvidence.incident_id==inc.id,
        IncidentTimeEvidence.cycle_number==inc.cycle_number).order_by(IncidentTimeEvidence.created_at.desc(),IncidentTimeEvidence.id.desc()).limit(1))
    missing="Se requiere evidencia temporal operacional revisada por administrador para el ciclo actual"
    valid=evidence is not None and evidence.source_kind=="operational"
    result["mttd"]=metric(evidence.occurred_at if valid else None,evidence.detected_at if valid else None,missing)
    result["mttr"]=metric(evidence.detected_at if valid else None,evidence.response_completed_at if valid else None,missing)
    current=[h for h in history if h.cycle_number==inc.cycle_number and h.policy_version is not None]
    cycle_start=baseline if inc.cycle_number==1 and baseline else next((h.created_at for h in current if h.status=="En análisis" and h.previous_status in ("Resuelto","Cerrado")),None)
    cycle_assignments=[a for a in assignments if a.cycle_number==inc.cycle_number and cycle_start and utc(a.created_at)>=utc(cycle_start)]
    cycle_metrics={"time_to_assignment":metric(cycle_start,cycle_assignments[0].created_at if cycle_assignments else None,"No existe nueva asignación registrada en este ciclo")}
    for key,state in (("time_to_response","En respuesta"),("time_to_resolution","Resuelto")):
        cycle_metrics[key]=metric(cycle_start,next((h.created_at for h in current if h.status==state),None),"Ciclo sin baseline o transición registrada")
    return {"cycle_number":inc.cycle_number,"tracking_baseline":iso(baseline),"timestamps":timestamps,
            "metrics":result,"current_cycle_baseline":iso(cycle_start),"current_cycle_metrics":cycle_metrics,"evidence_id":evidence.id if evidence else None,
            "timestamp_scope":"First/latest recorded, not guaranteed first-ever for legacy incidents",
            "attribution":"Transaction timestamps and declared documentary evidence, not measured operator performance"}
