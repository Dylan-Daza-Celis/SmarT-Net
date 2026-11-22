import email.utils
import json
import math
import re
import ssl
import time
from uuid import UUID
import httpx
from .config import AgentError, credentials


class Retry(Exception):
    def __init__(self, code, delay=None): self.code, self.delay = code, delay


def retry_after(value, now=None):
    if value is None: return None
    try:
        if value.isdigit(): delay = max(1, int(value))
        else:
            date = email.utils.parsedate_to_datetime(value)
            if date.tzinfo is None: return None
            delay = max(1, math.ceil(date.timestamp()-(time.time() if now is None else now)))
        if delay > 365*86400: raise AgentError('retry_after_excessive')
        return delay
    except (ValueError, TypeError, OverflowError): return None


class Transport:
    def __init__(self, config, client=None, credential_provider=credentials):
        self.config, self.credentials = config, credential_provider
        self.token = None; self.expiry = 0; self.actor_id = None
        self.on_event = lambda code: None
        self.client = client or httpx.Client(base_url=config.api_url.rstrip('/'),
            trust_env=False, follow_redirects=False, verify=ssl.create_default_context(cafile=config.ca_file),
            headers={'Accept-Encoding':'identity'},
            timeout=httpx.Timeout(30, connect=5, pool=5), limits=httpx.Limits(max_connections=1, max_keepalive_connections=1))

    def close(self): self.client.close()

    def request(self, method, path, **kwargs):
        try:
            with self.client.stream(method, path, **kwargs) as response:
                status = response.status_code
                if status in (408, 425, 429, 500, 502, 503, 504):
                    raise Retry('http_'+str(status), retry_after(response.headers.get('Retry-After')))
                if status != 200: raise AgentError('http_'+str(status))
                if response.headers.get('Content-Encoding','identity').lower() != 'identity':
                    raise AgentError('unexpected_response_encoding')
                body = bytearray()
                chunks = (response.content,) if response.is_stream_consumed else response.iter_raw(chunk_size=8192)
                for chunk in chunks:
                    if len(body)+len(chunk) > 128*1024: raise AgentError('response_too_large')
                    body.extend(chunk)
                try: return json.loads(body)
                except (ValueError, UnicodeError, RecursionError): raise AgentError('invalid_response') from None
        except httpx.HTTPError:
            raise Retry('network_error') from None

    def authenticate(self):
        username, password = self.credentials()
        data = self.request('POST', '/api/auth/login', json={'username': username, 'password': password})
        if (not isinstance(data, dict) or not isinstance(data.get('access_token'), str) or
                not re.fullmatch(r'[a-zA-Z0-9_.~-]{1,4096}', data['access_token']) or data.get('token_type') != 'bearer' or
                type(data.get('expires_in')) is not int or not 60 <= data['expires_in'] <= 900):
            raise AgentError('invalid_login_response')
        token = data['access_token']
        me = self.request('GET', '/api/auth/me', headers={'Authorization':'Bearer '+token})
        if (not isinstance(me, dict) or me.get('eve_only') is not True or me.get('active') is not True or
                me.get('role') != 'analista' or not isinstance(me.get('id'), str)):
            raise AgentError('least_privilege_account_required')
        self.token, self.actor_id = token, me['id']
        self.expiry = time.monotonic()+data['expires_in']-30

    def send(self, batch):
        if self.token is None or time.monotonic() >= self.expiry:
            self.on_event('jwt_obtain' if self.token is None else 'jwt_renewal_due')
            self.authenticate()
        for renewal in range(2):
            try:
                self.on_event('eve_request_started')
                report = self.request('POST', '/api/events/import/eve', content=batch['body'],
                    params={'sensor_id':self.config.sensor_id,
                            'filename':f"agent-{batch['source_id']}-L{batch['start_line']}-B{batch['id']}.jsonl"},
                    headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/x-ndjson'})
                return validate_report(report, batch)
            except AgentError as exc:
                if exc.code != 'http_401' or renewal: raise
                self.token = None
                self.on_event('http_401_reauthenticate')
                self.authenticate()  # One renewal only; bad credentials become a permanent block.
        raise AgentError('http_401')


def validate_report(report, batch):
    if not isinstance(report, dict): raise AgentError('unverifiable_acceptance')
    counts = ('imported', 'duplicates', 'discarded', 'processed', 'batches', 'bytes_received', 'unknown', 'errors_omitted')
    if any(type(report.get(k)) is not int or report[k] < 0 for k in counts): raise AgentError('unverifiable_acceptance')
    try: UUID(report.get('import_id', ''))
    except (ValueError, TypeError, AttributeError): raise AgentError('unverifiable_acceptance') from None
    if (report.get('complete') is not True or report['errors_omitted'] != 0 or
            report['bytes_received'] != len(batch['body']) or report['processed'] != batch['records'] or
            report['imported']+report['duplicates']+report['discarded'] != batch['records'] or
            not isinstance(report.get('errors'), list) or not isinstance(report.get('discard_reasons'), dict)):
        raise AgentError('unverifiable_acceptance')
    reasons = report['discard_reasons']
    if any(not isinstance(k, str) or type(v) is not int or v < 0 for k,v in reasons.items()) or sum(reasons.values()) != report['discarded']:
        raise AgentError('unverifiable_acceptance')
    for error in report['errors']:
        if (not isinstance(error, dict) or type(error.get('line')) is not int or
                not 1 <= error['line'] <= batch['end_line']-batch['start_line']+1 or
                not isinstance(error.get('code'), str) or not isinstance(error.get('fields'), list)):
            raise AgentError('unverifiable_acceptance')
    # Store only the known report schema, never arbitrary response keys or authentication values.
    return {k:report[k] for k in (*counts, 'import_id', 'complete', 'errors', 'discard_reasons')}
