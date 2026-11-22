"""Only fresh UUID databases/schemas; never accepts an arbitrary database or target URL."""
import contextlib
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4
import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Isolated:
    def __init__(self, database='sqlite'):
        self.directory = ROOT/'.test-runs'/('iter10-'+uuid4().hex)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.schema = 'iter10_'+uuid4().hex
        if database == 'postgresql':
            # Deliberately a dedicated loopback-only temporary PostgreSQL instance.
            base = 'postgresql+psycopg://postgres@127.0.0.1:55440/smartir_validation'
            engine = create_engine(base)
            with engine.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            engine.dispose()
            self.url = base+'?options=-csearch_path%3D'+self.schema
        elif database == 'sqlite':
            self.url = 'sqlite:///'+str(self.directory/'validation.db')
        else: raise ValueError('Only sqlite or postgresql validation databases')
        self.environment = {**os.environ, 'DATABASE_URL': self.url, 'JWT_SECRET': secrets.token_urlsafe(48),
                            'CORRELATION_WINDOW_SECONDS': '900', 'SMARTIR_ALLOWED_HOSTS': 'localhost,127.0.0.1',
                            'PYTHONPATH': str(ROOT/'backend')}
        self.credentials = {role: ('validation_'+role, secrets.token_urlsafe(24))
                            for role in ('administrador', 'analista', 'observador')}
        self.api_port = port()
        self.base_url = f'http://127.0.0.1:{self.api_port}'
        self.process = None

    def prepare(self):
        self.command([sys.executable, '-m', 'alembic', 'upgrade', 'head'])
        # Separate child avoids app/database imports with an ambient user's DATABASE_URL.
        script = """import json,sys
from app.database import Session
from app.models import User
from app.security import password_hasher
with Session.begin() as db:
 for role,(username,password) in json.load(sys.stdin).items():
  db.add(User(username=username,role=role,password_hash=password_hasher.hash(password)))
"""
        import json
        self.command([sys.executable, '-c', script], input=json.dumps(self.credentials))

    def command(self, args, **kwargs):
        return subprocess.run(args, cwd=ROOT/'backend', env=self.environment, check=True,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), **kwargs)

    def start(self):
        self.process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
            '--port', str(self.api_port), '--no-proxy-headers', '--no-server-header', '--limit-concurrency', '32',
            '--no-access-log'], cwd=ROOT/'backend', env=self.environment, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with httpx.Client(trust_env=False, timeout=1) as client:
            for _ in range(200):
                if self.process.poll() is not None: raise RuntimeError('Isolated API failed to start; no secrets logged')
                try:
                    if client.get(self.base_url+'/health').status_code == 200: return
                except httpx.HTTPError: pass
                time.sleep(.1)
        self.stop()
        raise RuntimeError('Isolated API health timeout')

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try: self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=5)
            self.process = None

    def snapshot(self):
        import hashlib
        import json
        from sqlalchemy import inspect
        engine = create_engine(self.url)
        try:
            with engine.connect() as db:
                tables = inspect(db).get_table_names()
                result = {}
                for table in sorted(tables):
                    rows = sorted([list(row) for row in db.execute(text(f'SELECT * FROM {table}'))], key=repr)
                    result[table] = {'rows': len(rows), 'sha256': hashlib.sha256(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()}
                return result
        finally: engine.dispose()

    @contextlib.contextmanager
    def running(self):
        try:
            self.prepare(); self.start(); yield self
        finally: self.stop()
