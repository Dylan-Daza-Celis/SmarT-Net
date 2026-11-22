"""Validated feature/reference boundary and independent synthetic scenario labels."""
from datetime import datetime, timedelta, timezone
import random
from uuid import UUID, uuid5, NAMESPACE_URL
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, StrictBool, model_validator, field_validator

TYPES = ["acceso_no_autorizado", "malware", "dos", "escaneo", "uso_indebido", "exfiltracion"]
GENERATOR_VERSION = "synthetic-scenarios-v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*")
    @classmethod
    def safe_text(cls, value):
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("NUL not supported")
            value.encode("utf-8")
        return value


class FeatureEvent(StrictModel):
    id: UUID
    operational_event_id: UUID | None = None
    event_timestamp: AwareDatetime
    received_at: AwareDatetime
    severity: int = Field(ge=0, le=100, strict=True)
    asset_criticality: int = Field(ge=0, le=100, strict=True)


class FeatureCase(StrictModel):
    id: UUID
    incident_id: UUID | None = None
    event_type: str
    events: list[FeatureEvent] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_case(self):
        if self.event_type not in TYPES or len({e.id for e in self.events}) != len(self.events):
            raise ValueError("Invalid taxonomy or duplicate event IDs")
        return self


class Reference(StrictModel):
    case_id: UUID
    priority: str | None = None
    malicious: StrictBool | None = None
    rationale: str = Field(min_length=1, max_length=1000)
    occurred_at: AwareDatetime | None = None
    detected_at: AwareDatetime | None = None
    response_completed_at: AwareDatetime | None = None
    timing_evidence: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def valid_priority(self):
        if self.priority not in (None, "Baja", "Media", "Alta", "Crítica"):
            raise ValueError("Unknown reference class")
        return self


class ExternalDataset(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    data_kind: str
    provenance: str = Field(min_length=1, max_length=2000)
    authorized: StrictBool
    cases: list[FeatureCase] = Field(min_length=1, max_length=500)
    references: list[Reference] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_cohort(self):
        ids = [c.id for c in self.cases]
        ref_ids = [r.case_id for r in self.references]
        event_ids = [e.id for c in self.cases for e in c.events]
        if self.data_kind not in ("synthetic", "controlled", "real") or not self.authorized:
            raise ValueError("Authorized data and explicit kind are required")
        if len(set(ids)) != len(ids) or len(set(ref_ids)) != len(ref_ids) or not set(ref_ids).issubset(ids) or len(set(event_ids)) != len(event_ids):
            raise ValueError("Duplicate IDs or references outside cohort")
        return self


class GenerateIn(StrictModel):
    seed: int = Field(default=202605, ge=0, le=4294967295, strict=True)
    count: int = Field(default=60, ge=6, le=500, strict=True)


class ExperimentIn(StrictModel):
    dataset_id: UUID
    budget: int = Field(default=10, ge=0, le=500, strict=True)


def synthetic(seed=202605, count=60):
    features_rng = random.Random(seed)
    reference_rng = random.Random(seed ^ 0x5EED)
    cases, references = [], []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    labels = ["Baja", "Media", "Alta", "Crítica"]
    scenarios = ["benign activity, no confirmed harm", "contained malicious attempt, no confirmed compromise",
                 "confirmed local compromise, limited impact", "confirmed essential-service outage or regulated-data exposure"]
    for index in range(count):
        case_id = uuid5(NAMESPACE_URL, f"smartir-eval-v1:{seed}:{index}")
        events = []
        received = base + timedelta(seconds=features_rng.randrange(3600))
        for j in range(features_rng.randint(1, 5)):
            events.append(FeatureEvent(id=uuid5(case_id, str(j)), event_timestamp=received-timedelta(seconds=30),
                received_at=received+timedelta(seconds=j), severity=features_rng.randrange(101),
                asset_criticality=features_rng.randrange(101)))
        cases.append(FeatureCase(id=case_id, event_type=TYPES[index % 6], events=events))
        scenario = reference_rng.randrange(4)
        references.append(Reference(case_id=case_id, priority=labels[scenario], malicious=scenario != 0,
                                    rationale=scenarios[scenario]))
    return ExternalDataset(name="Synthetic scenarios v1", data_kind="synthetic", authorized=True,
        provenance="Generated scenarios, not IDS captures or human operator measurements", cases=cases, references=references)
