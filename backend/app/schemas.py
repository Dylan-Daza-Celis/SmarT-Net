from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from .correlation import normalize_ip


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=100)
    event_timestamp: AwareDatetime
    source_ip: str | None = None
    destination_ip: str | None = None
    event_type: str = Field(min_length=1, max_length=60)
    severity: int = Field(ge=0, le=100)
    asset_criticality: int = Field(default=50, ge=0, le=100)
    message: str = Field(default="", max_length=2000)

    @field_validator("source_ip", "destination_ip")
    @classmethod
    def valid_ip(cls, value):
        # Keep serialization unchanged for historical fingerprints.
        normalize_ip(value)
        return value


class BatchIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=1000)
