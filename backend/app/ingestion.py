"""Single persistence/correlation/risk pipeline for normalized and EVE inputs."""
from dataclasses import dataclass, field
from datetime import timezone
from uuid import uuid4
import hashlib
import json

from sqlalchemy import select, tuple_
from .correlation import correlate, WINDOW_SECONDS, VERSION as CORRELATION_VERSION
from .models import Event, EventEvidence, Incident, IncidentHistory, RiskEvaluation, IncidentReviewSignal, RiskReassessmentSignal
from .risk import evaluate, parameters
from .lifecycle import mutation_lock, now, actor, utc, VERSION as LIFECYCLE_VERSION
from .schemas import EventIn


@dataclass
class ImportRecord:
    event: EventIn
    fingerprint: str | None = None
    raw_event: str | None = None
    attributes: dict = field(default_factory=dict)
    evidence: dict | None = None


def ingest(records, author_id, session_factory):
    # Prepare exact historical fingerprints before entering the shared write transaction.
    prepared=[]
    for record in records:
        raw=record.event.model_dump(mode='json')
        fp=record.fingerprint or hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
        prepared.append((record,raw,fp))
    created, duplicates = 0, 0
    affected = set()
    def chunks(values):
        values=list(values)
        for start in range(0,len(values),400): yield values[start:start+400]
    with session_factory.begin() as db:
        mutation_lock(db)
        actor(db,author_id)
        known={}
        for group in chunks({fp for _,_,fp in prepared}):
            known.update(db.execute(select(Event.fingerprint,Event.id).where(Event.fingerprint.in_(group))).all())
        plans={}
        for record,raw,fp in prepared:
            if fp not in known and fp not in plans:
                key,start,attributes=correlate(record.event)
                plans[fp]=(key,start,attributes,record.event)
        cache={}
        for group in chunks({(p[0],p[1]) for p in plans.values()}):
            rows=db.scalars(select(Incident).where(tuple_(Incident.correlation_key,Incident.window_start).in_(group),
                Incident.window_seconds==WINDOW_SECONDS,Incident.correlation_version==CORRELATION_VERSION).with_for_update()).all()
            cache.update({(i.correlation_key,utc(i.window_start)):i for i in rows})
        new_incidents=[];histories=[]
        for key,start,attributes,item in plans.values():
            if (key,start) not in cache:
                timestamp=now()
                inc=Incident(id=str(uuid4()),correlation_key=key,event_type=item.event_type,
                    created_at=timestamp,lifecycle_started_at=timestamp,cycle_number=1,
                    source_ip=attributes[1],destination_ip=attributes[2],
                    correlation_version=CORRELATION_VERSION,window_start=start,window_seconds=WINDOW_SECONDS,
                    risk_parameters=json.dumps(parameters()))
                cache[key,start]=inc;new_incidents.append(inc)
                histories.append(IncidentHistory(incident_id=inc.id,author_id=author_id,status='Nuevo',
                    created_at=timestamp,policy_version=LIFECYCLE_VERSION,cycle_number=1,
                    justification='Creado por importación de eventos'))
        db.add_all(new_incidents);db.flush()
        new_events=[];evidence=[];signals=[]
        for record,raw,fp in prepared:
            item=record.event
            if fp in known:
                duplicates+=1;event_id=known[fp]
            else:
                key,start,_,_=plans[fp];inc=cache[key,start]
                event_id=str(uuid4());known[fp]=event_id
                ev = Event(id=event_id,fingerprint=fp, source=item.source,
                    event_timestamp=item.event_timestamp.astimezone(timezone.utc),
                    source_ip=item.source_ip, destination_ip=item.destination_ip,
                    event_type=item.event_type, severity=item.severity,
                    asset_criticality=item.asset_criticality,
                    asset_criticality_observed="asset_criticality" in item.model_fields_set,
                    message=item.message,
                    raw_event=record.raw_event if record.raw_event is not None else json.dumps(raw, ensure_ascii=False),
                    incident_id=inc.id, **record.attributes)
                new_events.append(ev)
                if inc.status=="Cerrado":
                    signals.append(IncidentReviewSignal(incident_id=inc.id,event_id=ev.id,author_id=author_id,
                        reason="new_event_after_closure: risk and state preserved; review required",created_at=now()))
                created += 1
                affected.add(inc.id)
            if record.evidence is not None:
                evidence.append(EventEvidence(event_id=event_id, author_id=author_id, **record.evidence))
        # Explicit FK stages; statements batch without changing per-import commit boundaries.
        db.add_all(new_events);db.flush()
        db.add_all(histories+evidence+signals)
        db.flush()
        by_id={i.id:i for i in cache.values()};pending=set()
        for group in chunks(affected):
            pending.update(db.scalars(select(IncidentReviewSignal.incident_id).outerjoin(RiskReassessmentSignal,
                RiskReassessmentSignal.signal_id==IncidentReviewSignal.id).where(
                IncidentReviewSignal.incident_id.in_(group),RiskReassessmentSignal.signal_id.is_(None)).distinct()).all())
        open_ids=[i for i in affected if by_id[i].status!='Cerrado' and i not in pending]
        events_by_incident={i:[] for i in open_ids}
        for group in chunks(open_ids):
            for event in db.scalars(select(Event).where(Event.incident_id.in_(group))):
                events_by_incident[event.incident_id].append(event)
        for inc_id in affected:
            inc = by_id[inc_id]
            inc.revision+=1
            if inc.status=="Cerrado" or inc_id in pending:
                continue
            events = events_by_incident[inc_id]
            explanation = evaluate(events, json.loads(inc.risk_parameters))
            inc.score, inc.priority = explanation["score"], explanation["priority"]
            inc.explanation = json.dumps(explanation, ensure_ascii=False)
            db.add(RiskEvaluation(incident_id=inc.id, algorithm_version=explanation["algorithm_version"],
                explanation=inc.explanation, score=inc.score, priority=inc.priority, event_count=len(events)))
    return {"imported": created, "duplicates": duplicates, "incidents_updated": len(affected)}
