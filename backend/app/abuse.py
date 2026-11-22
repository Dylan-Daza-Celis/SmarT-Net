"""Bounded process-local admission controls; no client-supplied forwarded IP trust."""
import asyncio
from collections import OrderedDict, deque
from contextlib import contextmanager
import math
import os
import threading
import time
from urllib.parse import urlsplit
from fastapi import Depends, HTTPException, Request
from starlette.responses import JSONResponse
from .security import current_user, writers, administrators


class AbuseController:
    def __init__(self, clock=time.monotonic, login_limit=20, capacity=4096):
        self.clock, self.login_limit, self.capacity = clock, login_limit, capacity
        self._lock = threading.Lock()
        self._buckets = OrderedDict()
        self.limits = {'import':30, 'compute':12, 'report':10, 'export':30, 'analytics':120, 'password':10}
        self._slots = {key:threading.BoundedSemaphore(value) for key,value in
            {'import':2, 'compute':1, 'report':2, 'export':2, 'analytics':4, 'password':2}.items()}

    def reset(self):
        """Internal test/isolated-benchmark hook; never exposed by HTTP."""
        with self._lock: self._buckets.clear()

    def check(self, key, limit, window=60):
        now = self.clock()
        with self._lock:
            expired = [k for k,v in self._buckets.items() if not v or v[-1] <= now-window]
            for k in expired: self._buckets.pop(k)
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self.capacity:
                    raise HTTPException(429, 'Capacidad temporal de admisión agotada', headers={'Retry-After':'60'})
                bucket = self._buckets[key] = deque()
            while bucket and bucket[0] <= now-window: bucket.popleft()
            if len(bucket) >= limit:
                retry = max(1, math.ceil(bucket[0]+window-now))
                raise HTTPException(429, 'Límite temporal de solicitudes', headers={'Retry-After':str(retry)})
            bucket.append(now)

    @contextmanager
    def work(self, category):
        slot = self._slots[category]
        if not slot.acquire(blocking=False):
            raise HTTPException(429, 'Operación costosa ya en curso; reintente después', headers={'Retry-After':'1'})
        try: yield
        finally: slot.release()


def admitted(role_dependency, category):
    async def dependency(request: Request, user=Depends(role_dependency)):
        control = request.app.state.abuse
        control.check(category+':user:'+user.id, control.limits[category])
        with control.work(category): yield user
    return dependency


importer = admitted(writers, 'import')
researcher = admitted(administrators, 'compute')
report_writer = admitted(writers, 'report')
export_reader = admitted(current_user, 'export')
analytics_reader = admitted(current_user, 'analytics')
password_admin = admitted(administrators, 'password')
research_exporter = admitted(administrators, 'export')


def publish_admin(db, user_id):
    """Short final authorization barrier after CPU/SQL work, before commit."""
    from . import lifecycle
    if db.bind.dialect.name=='postgresql' or (db.bind.dialect.name=='sqlite' and not db.connection().connection.driver_connection.in_transaction):
        lifecycle.mutation_lock(db)
    lifecycle.actor(db,user_id,admin=True)


class RequestGuard:
    """Pure ASGI: bounded JSON buffering before validation; EVE keeps partial-limit contract."""
    def __init__(self, app):
        self.app = app
        self.allowed_hosts=frozenset(h.strip().casefold() for h in os.environ.get(
            'SMARTIR_ALLOWED_HOSTS','localhost,127.0.0.1,::1,api').split(',') if h.strip())

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope,receive,send)
        path = scope.get('path',''); headers = dict(scope.get('headers',[]))
        async def response(status, detail, extra=None):
            await JSONResponse({'detail':detail},status_code=status,headers=extra)(scope,receive,secured_send)
        async def secured_send(message):
            if message['type'] == 'http.response.start':
                values = dict(message.get('headers',[]))
                values.update({b'x-content-type-options':b'nosniff', b'x-frame-options':b'DENY',
                    b'referrer-policy':b'no-referrer', b'permissions-policy':b'camera=(), microphone=(), geolocation=()'})
                if path.startswith('/api/'):
                    values[b'cache-control']=b'no-store'
                    values[b'content-security-policy']=b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
                message={**message,'headers':list(values.items())}
            await send(message)
        if len(path)>512: return await response(414,'Ruta demasiado larga')
        if sum(len(k)+len(v) for k,v in scope.get('headers',[]))>16384:
            return await response(431,'Cabeceras demasiado grandes')
        host_values=[v for k,v in scope.get('headers',[]) if k==b'host']
        try:
            if len(host_values)!=1: raise ValueError('Missing/duplicate Host')
            host=host_values[0].decode('ascii')
            if any(ord(c)<33 or c in '/\\?#@' for c in host): raise ValueError('Invalid Host syntax')
            parsed=urlsplit('http://'+host)
            if parsed.hostname is None or parsed.hostname.casefold() not in self.allowed_hosts: raise ValueError('Untrusted Host')
            parsed.port  # Validate numeric port/range, if present.
        except (ValueError, UnicodeError): return await response(400,'Host no permitido o inválido')
        login = path == '/api/auth/login' and scope['method']=='POST'
        control = scope['app'].state.abuse
        if login:
            peer = (scope.get('client') or ('unknown',0))[0]
            try: control.check('login:peer:'+peer, control.login_limit)
            except HTTPException as exc: return await response(exc.status_code,exc.detail,exc.headers)
        if path.startswith('/api/') and not login and b'authorization' not in headers:
            return await response(401,'Sesión inválida o expirada',{'WWW-Authenticate':'Bearer'})
        lengths = [v for k,v in scope.get('headers',[]) if k==b'content-length']
        if len(lengths)>1 or (lengths and (not lengths[0].isdigit() or b'transfer-encoding' in headers)):
            return await response(400,'Longitud de petición inválida')
        limit = 4096 if login else 16384 if path.startswith('/api/users') else 32768
        if path == '/api/events/import': limit = 5*1024*1024
        if path in ('/api/ml/datasets/import','/api/evaluation/datasets/import'): limit = 2*1024*1024
        # A timeout only covers waiting for the next network chunk, never ingestion/ML computation.
        async def timed_receive():
            try: return await asyncio.wait_for(receive(),timeout=10)
            except asyncio.TimeoutError: raise HTTPException(408,'Tiempo de lectura agotado; los lotes previos pueden haberse conservado')
        if scope['method'] in ('POST','PATCH','PUT') and path != '/api/events/import/eve':
            if lengths and int(lengths[0])>limit: return await response(413,'Petición demasiado grande')
            body = bytearray()
            while True:
                try: chunk = await timed_receive()
                except HTTPException as exc: return await response(exc.status_code,exc.detail)
                if chunk['type']=='http.disconnect': return
                if len(body)+len(chunk.get('body',b''))>limit: return await response(413,'Petición demasiado grande')
                body.extend(chunk.get('body',b''))
                if not chunk.get('more_body',False): break
            if lengths and len(body)!=int(lengths[0]): return await response(400,'Longitud de petición incoherente')
            delivered = False
            async def buffered_receive():
                nonlocal delivered
                if delivered: return await timed_receive()
                delivered=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            await self.app(scope,buffered_receive,secured_send)
        else:
            await self.app(scope,timed_receive,secured_send)
