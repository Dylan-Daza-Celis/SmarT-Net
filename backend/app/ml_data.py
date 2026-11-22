"""Explicit laboratory assumptions; outcomes never enter the feature contract."""
from datetime import datetime, timedelta, timezone
import random
from uuid import UUID, NAMESPACE_URL, uuid5
from pydantic import Field, model_validator
from .evaluation_data import StrictModel, ExternalDataset, FeatureCase, FeatureEvent, Reference, TYPES
from .evaluation_metrics import CLASSES

LAB_VERSION = "lab-outcomes-v1"
ANNOTATION = "Benign authorized/no compromise=Baja; malicious contained/no compromise=Media; confirmed local nonessential compromise=Alta; essential outage or regulated exposure=Crítica. No weighted scores used."


class LabIn(StrictModel):
    seed: int = Field(default=202606, ge=0, le=4294967295, strict=True)
    groups: int = Field(default=96, ge=16, le=160, strict=True)


class MLDatasetIn(StrictModel):
    dataset: ExternalDataset
    groups: dict[UUID, UUID]
    annotation_policy: str = Field(min_length=20, max_length=2000)
    label_source: str

    @model_validator(mode="after")
    def validate_manifest(self):
        if set(self.groups) != {c.id for c in self.dataset.cases}:
            raise ValueError("Every case requires an explicit origin/scenario group")
        if self.label_source not in ("lab_outcomes", "independent_review"):
            raise ValueError("Labels must come from outcomes or independent review, never model scores")
        sources = {}
        for case in self.dataset.cases:
            group = self.groups[case.id]
            event_ids = [e.operational_event_id for e in case.events if e.operational_event_id]
            if len(event_ids) != len(set(event_ids)):
                raise ValueError("Repeated operational event within case")
            keys = (["incident:"+str(case.incident_id)] if case.incident_id else [])
            keys += ["event:"+str(e.operational_event_id) for e in case.events if e.operational_event_id]
            for key in keys:
                if key in sources and sources[key] != group:
                    raise ValueError("Dependent operational records must share a group")
                sources[key] = group
        return self


class TrainIn(StrictModel):
    dataset_id: UUID
    seed: int = Field(default=202606, ge=0, le=4294967294, strict=True)
    budget: int = Field(default=10, ge=0, le=500, strict=True)


def annotate(outcome):
    if outcome["essential_outage"] or outcome["regulated_exposure"]:
        return "Crítica"
    if outcome["compromise"]:
        return "Alta"
    return "Media" if outcome["malicious"] else "Baja"


def laboratory(seed=202606, groups=96):
    rng = random.Random(seed)
    cases, refs, membership = [], [], {}
    base = datetime(2026, 2, 1, tzinfo=timezone.utc)
    for g in range(groups):
        scenario = g % 4
        group = uuid5(NAMESPACE_URL, f"smartir-lab-v1:{seed}:{g}")
        outage = rng.random() < .5
        outcome = {"malicious": scenario > 0, "compromise": scenario >= 2,
                   "essential_outage": scenario == 3 and outage,
                   "regulated_exposure": scenario == 3 and not outage}
        label = annotate(outcome)
        # Signals overlap. These conditional distributions are assumptions, not measurements.
        center = rng.uniform(*[(5,35),(25,60),(45,85),(65,95)][scenario])
        asset = rng.uniform(*[(5,60),(10,70),(25,90),(55,100)][scenario])
        for replica in range(3):
            key = uuid5(group, str(replica))
            reception = base + timedelta(minutes=g*30, seconds=replica*120)
            n = rng.randint(*[(1,2),(1,4),(2,6),(3,8)][scenario])
            events = []
            for e in range(n):
                # False alarms / missed signals, not label corruption from weighted priorities.
                severity = rng.randrange(101) if rng.random() < .15 else round(rng.gauss(center,12))
                events.append(FeatureEvent(id=uuid5(key,str(e)),
                    event_timestamp=reception+timedelta(seconds=e*20-30),
                    received_at=reception+timedelta(seconds=e*20),
                    severity=max(0,min(100,severity)), asset_criticality=max(0,min(100,round(rng.gauss(asset,8))))))
            cases.append(FeatureCase(id=key,event_type=TYPES[(g//4)%6],events=events))
            refs.append(Reference(case_id=key,priority=label,malicious=outcome["malicious"],
                rationale="Synthetic lab oracle: "+str(outcome)+"; not an IDS capture or weighted label"))
            membership[key]=group
    return MLDatasetIn(dataset=ExternalDataset(name="Laboratory outcomes v1",data_kind="synthetic",
        provenance="Plausible scenario assumptions, not real observations or operator measurements",authorized=True,
        cases=cases,references=refs),groups=membership,annotation_policy=ANNOTATION,label_source="lab_outcomes")
