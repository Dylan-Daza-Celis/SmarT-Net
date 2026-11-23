"""Suricata EVE JSON adapter. Classification is an explicit, conservative policy."""
from datetime import datetime, timezone
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from .correlation import normalize_ip
from .ingestion import ImportRecord
from .schemas import EventIn
from .suricata_policy import alert_criticality, classification

ADAPTER_VERSION = "suricata-eve-v2"
FINGERPRINT_VERSION = "suricata-eve-fp-v1"
# EVE contains the human-readable category, not necessarily a classtype shortname.
# Exfiltration uses an explicit custom category: generic information leaks are ambiguous.
CATEGORY_GROUPS = {
    "acceso_no_autorizado": ["attempted-admin", "Attempted Administrator Privilege Gain",
        "successful-admin", "Successful Administrator Privilege Gain", "attempted-user",
        "Attempted User Privilege Gain", "successful-user", "Successful User Privilege Gain"],
    "malware": ["trojan-activity", "A Network Trojan was detected",
        "command-and-control", "Malware Command and Control Activity Detected"],
    "dos": ["attempted-dos", "Attempted Denial of Service", "successful-dos",
        "Denial of Service", "denial-of-service", "Detection of a Denial of Service Attack"],
    "escaneo": ["network-scan", "Detection of a Network Scan"],
    "uso_indebido": ["policy-violation", "Potential Corporate Privacy Violation",
        "inappropriate-content", "Inappropriate Content was Detected"],
    "exfiltracion": ["data-exfiltration", "Data Exfiltration"],
}
CATEGORY_MAP = {alias.casefold(): kind for kind, aliases in CATEGORY_GROUPS.items() for alias in aliases}


class Alert(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    signature: str | None = Field(default=None, max_length=2000)
    signature_id: int | None = Field(default=None, ge=0, le=4294967295)
    category: str | None = Field(default=None, max_length=255)
    severity: int | None = Field(default=None, ge=0, le=255)


class EveRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    timestamp: str
    event_type: str
    src_ip: str | None = None
    dest_ip: str | None = None
    src_port: int | None = Field(default=None, ge=0, le=65535)
    dest_port: int | None = Field(default=None, ge=0, le=65535)
    proto: str | None = Field(default=None, min_length=1, max_length=32)
    alert: Alert

    @field_validator("src_ip", "dest_ip")
    @classmethod
    def ip_address(cls, value):
        if value == "":
            raise ValueError("Empty EVE IP")
        return normalize_ip(value)


class EveLineError(ValueError):
    def __init__(self, code, fields=None):
        self.code, self.fields = code, fields or []
        super().__init__(code)


def reject_constant(value):
    raise ValueError("Non-finite JSON number")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def validate_text(value):
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("NUL not supported")
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key, item in value.items():
            validate_text(key)
            validate_text(item)
    elif isinstance(value, list):
        for item in value:
            validate_text(item)


def adapt_line(raw_bytes, *, sensor_id, filename, import_id, line_number):
    try:
        raw_line = raw_bytes.decode("utf-8")
        # Accept UTF-8 BOM only on the first physical line; evidence keeps it.
        parsed = json.loads(raw_line.lstrip("\ufeff") if line_number == 1 else raw_line,
                            parse_constant=reject_constant, object_pairs_hook=unique_keys)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("event_type"), str):
            raise ValueError("Expected EVE object")
        if parsed["event_type"] != "alert":
            return None
        eve = EveRecord.model_validate(parsed)
        timestamp = datetime.fromisoformat(eve.timestamp.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Timestamp timezone required")
        timestamp = timestamp.astimezone(timezone.utc)
        # Namespace and sensor are part of the fingerprint, not filename or adapter policy.
        canonical = json.dumps([FINGERPRINT_VERSION, sensor_id, parsed], sort_keys=True,
                               ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        # Ensure PostgreSQL text can store both original and decoded values.
        validate_text(parsed)
    except ValidationError as exc:
        raise EveLineError("invalid_fields", [".".join(map(str, e["loc"])) for e in exc.errors()]) from exc
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise EveLineError("invalid_json_or_timestamp") from exc
    interpreted = classification(eve.alert.category, eve.alert.signature, eve.proto, CATEGORY_MAP)
    kind = interpreted['type']
    severity = eve.alert.severity
    criticality = alert_criticality(severity)
    normalized_severity = criticality['value']
    event = EventIn(source=f"suricata:{sensor_id}", event_timestamp=timestamp,
        source_ip=eve.src_ip, destination_ip=eve.dest_ip, event_type=kind,
        severity=normalized_severity, message=eve.alert.signature or "Suricata alert")
    metadata = {"adapter_version": ADAPTER_VERSION, "fingerprint_version": FINGERPRINT_VERSION,
        "source_port": eve.src_port, "destination_port": eve.dest_port, "protocol": eve.proto,
        "signature": eve.alert.signature, "signature_id": eve.alert.signature_id,
        "category": eve.alert.category, "suricata_severity": severity,
        "input_event_type": eve.event_type, "original_timestamp": eve.timestamp,
        "category_status": "missing" if "category" not in parsed['alert'] else
            "null" if eve.alert.category is None else "empty" if not eve.alert.category.strip() else "provided",
        "classification": interpreted,
        "alert_criticality": criticality,
        "severity_policy": "priority_0_1_100_2_70_3_40_4plus_10_missing_50",
        "severity_defaulted": severity is None,
        "asset_criticality": {"value": 50, "observed": False, "policy": "unknown_default_50"}}
    return ImportRecord(event=event, fingerprint=hashlib.sha256(canonical.encode()).hexdigest(),
        raw_event=raw_line, attributes={"adapter_metadata": json.dumps(metadata)},
        evidence={"import_id": import_id, "filename": filename, "sensor_id": sensor_id,
                  "line_number": line_number, "raw_line": raw_line,
                  "raw_sha256": hashlib.sha256(raw_bytes).hexdigest()})
