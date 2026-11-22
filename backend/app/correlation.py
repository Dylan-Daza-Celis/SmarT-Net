"""Deterministic UTC tumbling windows; no arrival-time dependency."""
import hashlib
import ipaddress
import json
import os
from datetime import datetime, timedelta, timezone

WINDOW_SECONDS = int(os.environ.get("CORRELATION_WINDOW_SECONDS", "900"))
if not 1 <= WINDOW_SECONDS <= 86400:
    raise RuntimeError("CORRELATION_WINDOW_SECONDS must be between 1 and 86400")
VERSION = "utc-tumbling-v1"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def normalize_ip(value):
    return str(ipaddress.ip_address(value)) if value else None


def correlate(item, seconds=WINDOW_SECONDS):
    timestamp = item.event_timestamp.astimezone(timezone.utc)
    elapsed = (timestamp - EPOCH) // timedelta(seconds=1)
    start = EPOCH + timedelta(seconds=(elapsed // seconds) * seconds)
    attributes = [item.event_type, normalize_ip(item.source_ip), normalize_ip(item.destination_ip)]
    key = hashlib.sha256(json.dumps([VERSION, *attributes], ensure_ascii=True).encode()).hexdigest()
    return key, start, attributes
