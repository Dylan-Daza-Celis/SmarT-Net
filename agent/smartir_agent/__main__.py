import argparse
import json
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time
from . import __version__
from .config import Config, AgentError, credentials
from .store import Store
from .transport import Transport
from .runner import Agent


def emit(**fields):
    print(json.dumps({'at':time.time(), **fields}, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description='Independent polling EVE shipper; no traffic capture')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--file', type=Path, default=Path(os.getenv('SMARTIR_AGENT_FILE', 'eve.json')))
    parser.add_argument('--state-dir', type=Path, default=Path(os.getenv('SMARTIR_AGENT_STATE', '.smartir-agent')))
    parser.add_argument('--api-url', default=os.getenv('SMARTIR_AGENT_API_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--sensor', default=os.getenv('SMARTIR_AGENT_SENSOR', 'suricata-agent'))
    parser.add_argument('--poll', type=float, default=1)
    parser.add_argument('--batch-lines', type=int, default=100)
    parser.add_argument('--batch-bytes', type=int, default=512*1024)
    parser.add_argument('--rotate-wait', type=float, default=2)
    parser.add_argument('--max-state-mib', type=int, default=256)
    parser.add_argument('--allow-remote-https', action='store_true')
    parser.add_argument('--ca-file')
    parser.add_argument('--resume-blocked', action='store_true')
    parser.add_argument('--accept-source-reset', action='store_true')
    parser.add_argument('--once', action='store_true', help='One bounded poll/send, for scheduled/isolated validation')
    args = parser.parse_args()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, lambda *_:stop.set())
    store = transport = None
    try:
        config = Config(source=args.file.absolute(), state_dir=args.state_dir.absolute(), api_url=args.api_url,
            sensor_id=args.sensor, poll_seconds=args.poll, batch_lines=args.batch_lines, batch_bytes=args.batch_bytes,
            rotate_wait_seconds=args.rotate_wait, allow_remote_https=args.allow_remote_https,
            ca_file=args.ca_file, max_state_bytes=args.max_state_mib*1024*1024)
        credentials()  # Validate the secret source without logging it, even when no input exists yet.
        store = Store(config)
        if args.accept_source_reset and not args.resume_blocked: raise AgentError('resume_flag_required')
        if args.resume_blocked: store.resume(args.accept_source_reset)
        transport = Transport(config); agent = Agent(store, transport, emit)
        emit(code='started', version=__version__, poll_seconds=config.poll_seconds)
        while not stop.is_set():
            wait = agent.step()
            if args.once: break
            stop.wait(min(wait, 60))  # Recheck the durable deadline; never send early or overflow Windows waits.
        emit(code='stopped')
        return 0
    except AgentError as exc:
        emit(code=exc.code); return 2
    except (OSError, sqlite3.Error, ValueError):
        emit(code='local_state_or_configuration_failure'); return 2
    finally:
        if transport: transport.close()
        if store: store.close()


if __name__ == '__main__': raise SystemExit(main())
