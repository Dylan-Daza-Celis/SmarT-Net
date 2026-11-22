"""Paired offline replay. Ranking accepts features only; labels are post-hoc."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from sqlalchemy import select
from fastapi import HTTPException
from . import evaluation_metrics as metrics
from .evaluation_data import ExternalDataset, FeatureCase, GENERATOR_VERSION
from .models import EvaluationDataset, EvaluationCase, EvaluationReference, EvaluationEventLink, Experiment, Incident, Event
from .risk import evaluate, parameters

VERSION = "paired-offline-v1"


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def save_dataset(db, data: ExternalDataset, author_id, generator=None):
    features = sorted([c.model_dump(mode="json") for c in data.cases], key=lambda c: c["id"])
    config = {"provenance": data.provenance, "authorization_declared": data.authorized,
              "generator": generator, "references_hash": digest([r.model_dump(mode="json") for r in data.references])}
    dataset = EvaluationDataset(author_id=author_id, name=data.name, data_kind=data.data_kind,
                                configuration=canonical(config), feature_hash=digest(features))
    db.add(dataset)
    db.flush()
    refs = {str(r.case_id): r for r in data.references}
    for feature in data.cases:
        if feature.incident_id and db.get(Incident, str(feature.incident_id)) is None:
            raise HTTPException(422, "Linked incident does not exist")
        case = EvaluationCase(dataset_id=dataset.id, case_key=str(feature.id),
            incident_id=str(feature.incident_id) if feature.incident_id else None,
            features=canonical(feature.model_dump(mode="json")))
        db.add(case)
        db.flush()
        if str(feature.id) in refs:
            db.add(EvaluationReference(case_id=case.id, payload=canonical(refs[str(feature.id)].model_dump(mode="json"))))
        for e in feature.events:
            if e.operational_event_id:
                event = db.get(Event, str(e.operational_event_id))
                if event is None or not feature.incident_id or event.incident_id != str(feature.incident_id):
                    raise HTTPException(422, "Event/incident provenance mismatch")
                if (event.severity, event.asset_criticality, event.event_type, utc(event.event_timestamp), utc(event.received_at)) != (
                    e.severity, e.asset_criticality, feature.event_type, utc(e.event_timestamp), utc(e.received_at)):
                    raise HTTPException(422, "Linked features do not match operational evidence")
                db.add(EvaluationEventLink(case_id=case.id, event_id=event.id))
    return dataset


def snapshot(db, dataset_id):
    rows = db.scalars(select(EvaluationCase).where(EvaluationCase.dataset_id == dataset_id).order_by(EvaluationCase.case_key)).all()
    features = [FeatureCase.model_validate_json(c.features) for c in rows]
    references = {}
    for row in rows:
        ref = db.get(EvaluationReference, row.id)
        if ref:
            references[row.case_key] = json.loads(ref.payload)
    return features, references


def rank_cases(cases: list[FeatureCase], params):
    predictions = {}
    for case in cases:
        events = [SimpleNamespace(severity=e.severity, asset_criticality=e.asset_criticality,
                                  event_type=case.event_type, asset_criticality_observed=True) for e in case.events]
        result = evaluate(events, params)
        predictions[str(case.id)] = {"score": result["score"], "priority": result["priority"],
            "received_at": min(e.received_at for e in case.events).astimezone(timezone.utc).isoformat()}
    # Datetimes rather than strings avoid lexical differences across offset formats.
    reception = lambda key: datetime.fromisoformat(predictions[key]["received_at"])
    fifo = sorted(predictions, key=lambda key: (reception(key), key))
    smart = sorted(predictions, key=lambda key: (-predictions[key]["score"], reception(key), key))
    return {"chronological": fifo, "smartir": smart}, predictions


def run_experiment(db, dataset, budget, author_id):
    cases, references = snapshot(db, dataset.id)
    params = parameters()
    # This boundary never receives references, rationale or outcome timestamps.
    orders, predictions = rank_cases(cases, params)
    predicted = {k: p["priority"] for k, p in predictions.items()}
    counts = {str(c.id): len(c.events) for c in cases}
    effective = min(budget, len(cases))
    results = {"classification": metrics.classification(predicted, references),
        "binary": metrics.false_positive_rate(predicted, references),
        "timing": metrics.timing(list(predictions), references, dataset.data_kind),
        "strategies": {name: metrics.attention(order, references, effective, counts) for name, order in orders.items()},
        "baseline_classification": metrics.metric(None, reason="FIFO no es un clasificador; las predicciones SmartIR son comunes a ambas colas"),
        "limitations": ["Offline replay, not a human operator trial", "All cases available at snapshot; unit cost per incident",
                        "No statistical significance or causal time improvement is inferred", "Imported times describe source data only"]}
    config = {"execution_kind": "simulation", "design": VERSION, "strategy": "paired_chronological_vs_smartir",
        "runtime_python": sys.version.split()[0], "application_version": "0.5.0",
        "dataset_kind": dataset.data_kind, "dataset_id": dataset.id, "feature_hash": dataset.feature_hash,
        "risk_parameters": params, "metrics_version": metrics.VERSION,
        "ranking_versions": {"chronological": "received-asc-id-v1", "smartir": "score-desc-received-id-v1"},
        "requested_budget": budget, "effective_budget": effective, "unit": "one incident selection",
        "correlation_applied": False, "cohort_size": len(cases), "dataset_configuration": json.loads(dataset.configuration)}
    experiment = Experiment(dataset_id=dataset.id, author_id=author_id, configuration=canonical(config),
        rankings=canonical({"orders": orders, "predictions": predictions}), results=canonical(results))
    db.add(experiment)
    db.flush()
    return experiment
