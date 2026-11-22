"""Offline integrity verification. Uses only the Python standard library."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(path):
    path = Path(path)
    if path.stat().st_size > 6*1024*1024:
        raise ValueError('Report exceeds verification limit')
    document = json.loads(path.read_text(encoding='utf-8-sig'))
    encoded = json.dumps(document['payload'], ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    actual = hashlib.sha256(encoded).hexdigest()
    if actual != document['content_sha256']:
        raise ValueError('SHA-256 mismatch')
    return actual


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Verify SmartIR-Net analytical JSON snapshot integrity')
    parser.add_argument('report')
    arguments = parser.parse_args()
    try:
        print('Verified SHA-256: '+verify(arguments.report))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, 'Invalid analytical report: '+type(exc).__name__+'\n')
