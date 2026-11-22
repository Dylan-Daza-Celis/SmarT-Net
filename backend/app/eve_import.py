"""Bounded streaming JSONL reader. Commits each valid batch, reports partial limits."""
from uuid import uuid4
from starlette.concurrency import run_in_threadpool
from .ingestion import ingest
from .suricata import adapt_line, EveLineError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_RECORDS = 10000
BATCH_SIZE = 100
MAX_ERRORS = 100


async def import_stream(chunks, *, author_id, sensor_id, filename, session_factory):
    report = {"import_id": str(uuid4()), "imported": 0, "duplicates": 0, "discarded": 0,
              "processed": 0, "batches": 0, "bytes_received": 0, "unknown": 0,
              "errors": [], "errors_omitted": 0, "discard_reasons": {}, "complete": True}
    pending = []
    buffer = bytearray()
    oversized = False
    line_number = 0

    def error(code, line=None, fields=None):
        if len(report["errors"]) < MAX_ERRORS:
            report["errors"].append({"line": line, "code": code, "fields": fields or []})
        else:
            report["errors_omitted"] += 1

    def discard(code, fields=None, is_error=True):
        report["discarded"] += 1
        counts = report["discard_reasons"]
        counts[code] = counts.get(code, 0) + 1
        if is_error:
            error(code, line_number, fields)

    async def flush():
        if not pending:
            return
        result = await run_in_threadpool(ingest, pending, author_id, session_factory, eve_service=True)
        report["imported"] += result["imported"]
        report["duplicates"] += result["duplicates"]
        report["batches"] += 1
        pending.clear()

    async def line(raw, too_long=False):
        nonlocal line_number
        line_number += 1
        if not too_long and not raw.strip():
            return True
        if report["processed"] >= MAX_RECORDS:
            return False
        report["processed"] += 1
        if too_long:
            discard("line_too_large")
            return True
        try:
            record = adapt_line(raw, sensor_id=sensor_id, filename=filename,
                                import_id=report["import_id"], line_number=line_number)
        except EveLineError as exc:
            discard(exc.code, exc.fields)
            return True
        if record is None:
            discard("unsupported_event_type", is_error=False)
        else:
            if record.event.event_type == "desconocido":
                report["unknown"] += 1
            pending.append(record)
            if len(pending) >= BATCH_SIZE:
                await flush()
        return True

    stopped = False
    async for chunk in chunks:
        remaining = MAX_FILE_BYTES - report["bytes_received"]
        report["bytes_received"] += len(chunk)
        over_limit = len(chunk) > remaining
        if over_limit:
            chunk = chunk[:max(0, remaining)]
        cursor = 0
        while cursor < len(chunk):
            end = chunk.find(b"\n", cursor)
            terminated = end != -1
            end = end if terminated else len(chunk)
            length = end - cursor
            if len(buffer) + length > MAX_LINE_BYTES:
                oversized = True
                buffer.clear()
            if not oversized:
                buffer.extend(chunk[cursor:end])
            cursor = end + 1
            if terminated:
                accepted = await line(bytes(buffer), oversized)
                buffer.clear()
                oversized = False
                if not accepted:
                    error("too_many_records", line_number)
                    stopped = True
                    break
        if stopped:
            break
        if over_limit:
            error("file_too_large", line_number + 1)
            stopped = True
            break
    if not stopped and (buffer or oversized):
        if not await line(bytes(buffer), oversized):
            error("too_many_records", line_number)
            stopped = True
    await flush()
    report["complete"] = not stopped
    return report
