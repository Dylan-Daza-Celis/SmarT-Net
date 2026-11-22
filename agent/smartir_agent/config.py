from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

MAX_LINE_BYTES = 64 * 1024  # Existing EVE contract, excluding LF (including optional CR).


class AgentError(Exception):
    """Only a constant safe code may reach logs; never exception messages/bodies."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Config:
    source: Path
    state_dir: Path
    api_url: str = 'http://127.0.0.1:8000'
    sensor_id: str = 'suricata-agent'
    batch_lines: int = 100
    batch_bytes: int = 512 * 1024
    poll_seconds: float = 1
    rotate_wait_seconds: float = 2
    allow_remote_https: bool = False
    ca_file: str | None = None
    max_state_bytes: int = 256 * 1024 * 1024
    min_free_bytes: int = 64 * 1024 * 1024

    def __post_init__(self):
        try:
            url = urlsplit(self.api_url)
            port = url.port
            local = url.hostname == 'localhost'
            try: local = local or ipaddress.ip_address(url.hostname or '').is_loopback
            except ValueError: pass
            if (url.scheme not in ('http', 'https') or not url.hostname or url.username is not None or
                url.password is not None or url.query or url.fragment or url.path not in ('', '/') or
                (not local and not (url.scheme == 'https' and self.allow_remote_https)) or
                (port is not None and not 1 <= port <= 65535)):
                raise ValueError()
        except ValueError: raise AgentError('unsafe_api_origin') from None
        if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}', self.sensor_id): raise AgentError('invalid_sensor')
        if not (1 <= self.batch_lines <= 100 and MAX_LINE_BYTES+1 <= self.batch_bytes <= 1024*1024 and
                .05 <= self.poll_seconds <= 300 and 0 <= self.rotate_wait_seconds <= 300 and
                2*1024*1024 <= self.max_state_bytes <= 16*1024**3 and self.min_free_bytes >= 0):
            raise AgentError('invalid_limits')
        if self.source.is_symlink(): raise AgentError('symlink_source_not_supported')
        if self.source.resolve() == (self.state_dir/'state.db').resolve(): raise AgentError('state_is_source')


def credentials():
    username = os.environ.get('SMARTIR_AGENT_USERNAME', '')
    filename = os.environ.get('SMARTIR_AGENT_PASSWORD_FILE', '')
    password = os.environ.get('SMARTIR_AGENT_PASSWORD', '')
    if filename and password: raise AgentError('ambiguous_credentials')
    if filename:
        path = Path(filename)
        if path.is_symlink() or not path.is_file(): raise AgentError('invalid_password_file')
        if os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise AgentError('password_file_permissions')
        with path.open('rb') as stream: value = stream.read(1025)
        if len(value) > 1024: raise AgentError('invalid_credentials')
        try: password = value.decode('utf-8').rstrip('\r\n')
        except UnicodeError: raise AgentError('invalid_credentials') from None
    if not re.fullmatch(r'[a-zA-Z0-9_.@-]{1,100}', username) or not 12 <= len(password) <= 128:
        raise AgentError('invalid_credentials')
    return username, password
