"""SQL cohorts shared by indicators, trends, pagination and immutable reports."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator
from fastapi import HTTPException
from sqlalchemy import select, func, case, and_
from .lifecycle import LifecycleInput, iso
from .models import (Incident, Event, User, IncidentHistory, AssignmentHistory,
                     IncidentTimeEvidence, IncidentReviewSignal, ReviewAcknowledgement)

VERSION = "analytics-v1"
PRIORITIES = ["Baja", "Media", "Alta", "Crítica"]
STATES = ["Nuevo", "Asignado", "En análisis", "En respuesta", "Resuelto", "Cerrado"]
LIMITATIONS = [
    "Datos del flujo operativo con procedencia no certificada: pueden incluir ejemplos sintéticos; no acreditan eficacia real.",
    "Se cuentan eventos deduplicados, no líneas importadas ni apariciones de evidencia.",
    "Estado, prioridad y responsable son actuales, no una reconstrucción histórica al final del periodo.",
    "Los intervalos describen registros o evidencia documental; no son mediciones de trabajo humano.",
    "Las comparaciones experimentales conservan su cohorte independiente y no se mezclan con este reporte operativo.",
]


class Filters(LifecycleInput):
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    time_basis: Literal["incident_created", "event_timestamp", "received_at"] = "incident_created"
    priority: Literal["Baja", "Media", "Alta", "Crítica"] | None = None
    event_type: str | None = Field(default=None, min_length=1, max_length=60)
    status: Literal["Nuevo", "Asignado", "En análisis", "En respuesta", "Resuelto", "Cerrado"] | None = None
    assignee: UUID | Literal["unassigned"] | None = None
    source: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def period(self):
        self.end = (self.end or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.start = (self.start or self.end-timedelta(days=30)).astimezone(timezone.utc)
        if not timedelta(0) < self.end-self.start <= timedelta(days=366):
            raise ValueError("El intervalo [start,end) debe ser positivo y no superar 366 días")
        return self


class QueryFilters(Filters):
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=50, ge=1, le=100)


def normalized(q):
    return q.model_dump(mode="json", exclude={"offset", "limit"})


def cohorts(q):
    clock = Event.event_timestamp if q.time_basis == "event_timestamp" else Event.received_at
    event_conditions = []
    if q.source is not None:
        event_conditions.append(Event.source == q.source)
    if q.time_basis != "incident_created":
        event_conditions += [clock >= q.start, clock < q.end]
    matching = select(Event.id, Event.incident_id, Event.source, clock.label("clock")).where(*event_conditions).cte("matching_events")
    predicates = []
    for column, value in ((Incident.priority, q.priority), (Incident.event_type, q.event_type), (Incident.status, q.status)):
        if value is not None:
            predicates.append(column == value)
    if q.assignee == "unassigned":
        predicates.append(Incident.assigned_to_id.is_(None))
    elif q.assignee is not None:
        predicates.append(Incident.assigned_to_id == str(q.assignee))
    if q.time_basis == "incident_created":
        predicates += [Incident.created_at >= q.start, Incident.created_at < q.end]
        if q.source is not None:
            predicates.append(select(matching.c.id).where(matching.c.incident_id == Incident.id).exists())
        cohort = select(Incident.id, Incident.created_at.label("clock")).where(*predicates).cte("cohort")
    else:
        matched = select(matching.c.incident_id, func.min(matching.c.clock).label("clock")).group_by(matching.c.incident_id).subquery()
        cohort = select(Incident.id, matched.c.clock).join(matched, matched.c.incident_id == Incident.id).where(*predicates).cte("cohort")
    selected_events = select(matching.c.id, matching.c.incident_id, matching.c.source,
        (cohort.c.clock if q.time_basis == "incident_created" else matching.c.clock).label("clock")
        ).join(cohort, cohort.c.id == matching.c.incident_id).cte("selected_events")
    return cohort, selected_events


def review_exists():
    return select(IncidentReviewSignal.id).outerjoin(ReviewAcknowledgement,
        ReviewAcknowledgement.signal_id == IncidentReviewSignal.id).where(
        IncidentReviewSignal.incident_id == Incident.id, ReviewAcknowledgement.id.is_(None)).exists()


def grouped(db, column, from_clause, labels=()):
    rows = dict(db.execute(select(column, func.count()).select_from(from_clause).group_by(column).order_by(column).limit(201)).all())
    if len(rows) > 200:
        raise HTTPException(422, 'Más de 200 categorías; reduzca periodo/filtros. No se truncan indicadores.')
    return [{"name": name, "count": rows.get(name, 0)} for name in list(labels)+sorted(set(rows)-set(labels))]


def seconds(db, start, end):
    if db.bind.dialect.name == "postgresql":
        return func.extract("epoch", end-start)
    return func.round((func.julianday(end)-func.julianday(start))*86400, 6)


def response_metrics(db, cohort):
    history = select(IncidentHistory.incident_id,
        func.min(case((IncidentHistory.status == "En respuesta", IncidentHistory.created_at))).label("response"),
        func.min(case((IncidentHistory.status == "Resuelto", IncidentHistory.created_at))).label("resolution")
        ).join(cohort, cohort.c.id == IncidentHistory.incident_id).group_by(IncidentHistory.incident_id).subquery()
    assignment = select(AssignmentHistory.incident_id, func.min(AssignmentHistory.created_at).label("assigned")
        ).join(cohort, cohort.c.id == AssignmentHistory.incident_id).where(AssignmentHistory.assigned_user_id.is_not(None)
        ).group_by(AssignmentHistory.incident_id).subquery()
    ranked = select(IncidentTimeEvidence.incident_id, IncidentTimeEvidence.source_kind,
        IncidentTimeEvidence.occurred_at, IncidentTimeEvidence.detected_at, IncidentTimeEvidence.response_completed_at,
        func.row_number().over(partition_by=IncidentTimeEvidence.incident_id,
            order_by=(IncidentTimeEvidence.created_at.desc(), IncidentTimeEvidence.id.desc())).label("rn")
        ).join(Incident, Incident.id == IncidentTimeEvidence.incident_id).join(cohort, cohort.c.id == Incident.id
        ).where(IncidentTimeEvidence.cycle_number == Incident.cycle_number).subquery()
    pairs = {"time_to_assignment": (Incident.lifecycle_started_at, assignment.c.assigned),
             "time_to_response": (Incident.lifecycle_started_at, history.c.response),
             "time_to_resolution": (Incident.lifecycle_started_at, history.c.resolution),
             "mttd": (ranked.c.occurred_at, ranked.c.detected_at),
             "mttr": (ranked.c.detected_at, ranked.c.response_completed_at)}
    expressions = []
    for key, (start, end) in pairs.items():
        conditions = [start.is_not(None), end.is_not(None), end >= start]
        if key in ("mttd", "mttr"):
            conditions.append(ranked.c.source_kind == "operational")
        expressions.append(case((and_(*conditions), seconds(db, start, end))).label(key))
    values = select(*expressions).select_from(Incident).join(cohort, cohort.c.id == Incident.id
        ).outerjoin(history, history.c.incident_id == Incident.id
        ).outerjoin(assignment, assignment.c.incident_id == Incident.id
        ).outerjoin(ranked, and_(ranked.c.incident_id == Incident.id, ranked.c.rn == 1)).subquery()
    aggregates = [func.count().label("total")]
    for key in pairs:
        aggregates += [func.count(values.c[key]).label(key+"_valid"), func.avg(values.c[key]).label(key+"_mean")]
    row = db.execute(select(*aggregates).select_from(values)).mappings().one()
    return {key: {"value": float(row[key+"_mean"]) if row['total'] and row[key+"_valid"] == row['total'] else None,
        "valid": row[key+"_valid"], "total": row['total'], "unit": "seconds",
        "status": "Calculable" if row['total'] and row[key+"_valid"] == row['total'] else "No calculable",
        "reason": None if row['total'] and row[key+"_valid"] == row['total'] else "Cohorte vacía o incompleta; faltan transiciones/baseline o evidencia operacional revisada. No se promedian subconjuntos."}
        for key in pairs}


def day(db, clock):
    return func.to_char(func.timezone("UTC", clock), "YYYY-MM-DD") if db.bind.dialect.name == "postgresql" else func.strftime("%Y-%m-%d", clock)


def dashboard(db, q):
    cohort, events = cohorts(q)
    selected = Incident.__table__.join(cohort, cohort.c.id == Incident.id)
    counts = db.execute(select(func.count().label("incidents"),
        func.count(case((Incident.assigned_to_id.is_not(None), 1))).label("assigned"),
        func.count(case((Incident.status.not_in(["Resuelto", "Cerrado"]), 1))).label("open"),
        func.count(case((Incident.status == "Resuelto", 1))).label("resolved"),
        func.count(case((Incident.status == "Cerrado", 1))).label("closed"),
        func.count(case((review_exists(), 1))).label("needs_review"),
        func.count(case((and_(Incident.priority == "Crítica", Incident.status.not_in(["Resuelto", "Cerrado"])), 1))).label("critical_open"),
        func.count(case((and_(Incident.priority.in_(["Alta", "Crítica"]), Incident.assigned_to_id.is_(None), Incident.status.not_in(["Resuelto", "Cerrado"])), 1))).label("urgent_unassigned")
        ).select_from(selected)).mappings().one()
    totals = dict(counts); totals['unassigned'] = totals['incidents']-totals['assigned']
    totals['events'] = db.scalar(select(func.count()).select_from(events))
    event_day, incident_day = day(db, events.c.clock), day(db, cohort.c.clock)
    event_days = dict(db.execute(select(event_day, func.count()).group_by(event_day)).all())
    incident_days = {d: (n, critical) for d, n, critical in db.execute(select(incident_day, func.count(),
        func.count(case((Incident.priority == "Crítica", 1)))).select_from(selected).group_by(incident_day))}
    trends = []
    cursor = q.start.date()
    while cursor <= (q.end-timedelta(microseconds=1)).date():
        key = cursor.isoformat(); n, critical = incident_days.get(key, (0, 0))
        trends.append({"date": key, "events": event_days.get(key, 0), "incidents": n, "critical": critical})
        cursor += timedelta(days=1)
    return {"version": VERSION, "filters": normalized(q), "totals": totals,
        "distributions": {"priority": grouped(db, Incident.priority, selected, PRIORITIES),
            "type": grouped(db, Incident.event_type, selected), "status": grouped(db, Incident.status, selected, STATES),
            "source": grouped(db, events.c.source, events)},
        "trends": trends, "response_metrics": response_metrics(db, cohort),
        "provenance": {"data_kind": "unverified", "reason": "El esquema de eventos no certifica origen sintético/operacional; no se infiere de source."},
        "methodology": {"period": "UTC [start,end)", "incident_denominator": totals['incidents'],
            "event_denominator": totals['events'], "trend_unit": "deduplicated events / distinct incidents per UTC day",
            "incident_trend": "Una vez por incidente: creación o primer evento coincidente según time_basis",
            "event_trend": "En incident_created los eventos se atribuyen a la fecha de creación del incidente; en los otros ejes se usa su propio timestamp",
            "response_cohort": "Primera transición registrada; evidencia temporal vigente del ciclo actual. Media solo con cobertura completa."},
        "limitations": LIMITATIONS}


def incident_page(db, q, offset=0, limit=50, public=False):
    cohort, events = cohorts(q)
    counts = select(events.c.incident_id, func.count().label("n")).group_by(events.c.incident_id).subquery()
    query = select(Incident.id, Incident.event_type, Incident.priority, Incident.score, Incident.status,
        Incident.revision, Incident.created_at, cohort.c.clock.label("cohort_at"),
        Incident.assigned_to_id, User.username.label("assignee"), func.coalesce(counts.c.n, 0).label("event_count"),
        review_exists().label("needs_review")).join(cohort, cohort.c.id == Incident.id
        ).outerjoin(User, User.id == Incident.assigned_to_id).outerjoin(counts, counts.c.incident_id == Incident.id
        ).order_by(Incident.created_at.desc(), Incident.id).offset(offset).limit(limit)
    rows = []
    for row in db.execute(query).mappings():
        item = dict(row)
        item['created_at'], item['cohort_at'] = iso(item['created_at']), iso(item['cohort_at'])
        item['assigned'] = item['assigned_to_id'] is not None
        if public:
            item.pop('assignee'); item.pop('assigned_to_id')
        rows.append(item)
    total = db.scalar(select(func.count()).select_from(cohort))
    return {"items": rows, "total": total, "offset": offset, "limit": limit, "filters": normalized(q)}
