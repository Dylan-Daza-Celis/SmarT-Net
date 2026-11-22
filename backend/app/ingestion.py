"""Single persistence/correlation/risk pipeline for normalized and EVE inputs."""
from dataclasses import dataclass, field
from datetime import timezone
import hashlib
import json

from sqlalchemy import select, text
from .correlation import correlate, WINDOW_SECONDS, VERSION as CORRELATION_VERSION
from .models import Event, EventEvidence, Incident, IncidentHistory, RiskEvaluation, IncidentReviewSignal
from .risk import evaluate, parameters
from .lifecycle import mutation_lock, now, actor, VERSION as LIFECYCLE_VERSION
from .schemas import EventIn
from .risk_audit import pending


@dataclass
class ImportRecord:
    event: EventIn
    fingerprint: str | None = None
    raw_event: str | None = None
    attributes: dict = field(default_factory=dict)
    evidence: dict | None = None


def ingest(records, author_id, session_factory):
    created, duplicates = 0, 0
    affected = set()
    with session_factory.begin() as db:
        mutation_lock(db)
        actor(db,author_id)
        for record in records:
            item = record.event
            raw = item.model_dump(mode="json")
            # Exact legacy algorithm, including defaults and timestamp representation.
            fp = record.fingerprint or hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
            existing = db.scalar(select(Event.id).where(Event.fingerprint == fp))
            if existing:
                duplicates += 1
                event_id = existing
            else:
                key, start, attributes = correlate(item)
                inc = db.scalar(select(Incident).where(
                    Incident.correlation_key == key, Incident.window_start == start,
                    Incident.window_seconds == WINDOW_SECONDS,
                    Incident.correlation_version == CORRELATION_VERSION).with_for_update())
                if inc is None:
                    timestamp=now()
                    inc = Incident(correlation_key=key, event_type=item.event_type,
                        created_at=timestamp,lifecycle_started_at=timestamp,cycle_number=1,
                        source_ip=attributes[1], destination_ip=attributes[2],
                        correlation_version=CORRELATION_VERSION, window_start=start,
                        window_seconds=WINDOW_SECONDS, risk_parameters=json.dumps(parameters()))
                    db.add(inc)
                    db.flush()
                    db.add(IncidentHistory(incident_id=inc.id, author_id=author_id,
                        status="Nuevo", created_at=timestamp,policy_version=LIFECYCLE_VERSION,cycle_number=1, justification="Creado por importación de eventos"))
                ev = Event(fingerprint=fp, source=item.source,
                    event_timestamp=item.event_timestamp.astimezone(timezone.utc),
                    source_ip=item.source_ip, destination_ip=item.destination_ip,
                    event_type=item.event_type, severity=item.severity,
                    asset_criticality=item.asset_criticality,
                    asset_criticality_observed="asset_criticality" in item.model_fields_set,
                    message=item.message,
                    raw_event=record.raw_event if record.raw_event is not None else json.dumps(raw, ensure_ascii=False),
                    incident_id=inc.id, **record.attributes)
                db.add(ev)
                db.flush()
                event_id = ev.id
                if inc.status=="Cerrado":
                    db.add(IncidentReviewSignal(incident_id=inc.id,event_id=ev.id,author_id=author_id,
                        reason="new_event_after_closure: risk and state preserved; review required",created_at=now()))
                created += 1
                affected.add(inc.id)
            if record.evidence is not None:
                db.add(EventEvidence(event_id=event_id, author_id=author_id, **record.evidence))
        db.flush()
        for inc_id in affected:
            inc = db.get(Incident, inc_id)
            inc.revision+=1
            if inc.status=="Cerrado" or pending(db,inc.id):
                continue
            events = db.scalars(select(Event).where(Event.incident_id == inc_id)).all()
            explanation = evaluate(events, json.loads(inc.risk_parameters))
            inc.score, inc.priority = explanation["score"], explanation["priority"]
            inc.explanation = json.dumps(explanation, ensure_ascii=False)
            db.add(RiskEvaluation(incident_id=inc.id, algorithm_version=explanation["algorithm_version"],
                explanation=inc.explanation, score=inc.score, priority=inc.priority, event_count=len(events)))
    return {"imported": created, "duplicates": duplicates, "incidents_updated": len(affected)}
