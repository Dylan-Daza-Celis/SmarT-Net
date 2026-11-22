from sqlalchemy import select
from .models import IncidentReviewSignal, RiskReassessmentSignal


def pending_query(incident_id):
    return select(IncidentReviewSignal.id).outerjoin(RiskReassessmentSignal,
        RiskReassessmentSignal.signal_id == IncidentReviewSignal.id).where(
            IncidentReviewSignal.incident_id == incident_id, RiskReassessmentSignal.signal_id.is_(None))


def pending(db, incident_id):
    return db.scalar(pending_query(incident_id).limit(1)) is not None
