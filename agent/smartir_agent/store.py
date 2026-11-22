"""Private, FULL-synchronous SQLite outbox/checkpoint and append-only metadata audit."""
import hashlib
import json
import os
import shutil
import sqlite3
import time
from uuid import uuid4
from .config import AgentError

APPLICATION_ID = 0x53495241


class Store:
    def __init__(self, config):
        self.config = config
        directory = config.state_dir
        if directory.is_symlink(): raise AgentError('symlink_state_not_supported')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != 'nt' and directory.stat().st_mode & 0o077: raise AgentError('state_directory_permissions')
        if (directory/'reader.lock').is_symlink(): raise AgentError('symlink_state_not_supported')
        self.lock = (directory/'reader.lock').open('a+b')
        if os.name != 'nt': os.chmod(directory/'reader.lock', 0o600)
        self.lock.seek(0, 2)
        if self.lock.tell() == 0: self.lock.write(b'0'); self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close(); raise AgentError('checkpoint_already_locked') from None
        try:
            db_path = directory/'state.db'
            if db_path.is_symlink(): raise AgentError('symlink_state_not_supported')
            if not db_path.exists():
                fd = os.open(db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
            elif db_path.stat().st_size:
                with db_path.open('rb') as existing: header = existing.read(100)
                if header[:16] != b'SQLite format 3\x00' or int.from_bytes(header[68:72], 'big') != APPLICATION_ID:
                    raise AgentError('foreign_or_invalid_state_database')
            self.db = sqlite3.connect(db_path)
            self.db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2*1024*1024)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA application_id='+str(APPLICATION_ID))
            self.db.execute('PRAGMA max_page_count='+str(config.max_state_bytes//4096))
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY,device TEXT,inode TEXT,offset INTEGER NOT NULL,
                    line INTEGER NOT NULL,anchor TEXT NOT NULL,current INTEGER NOT NULL,created REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_current_source ON sources(current) WHERE current=1;
                CREATE TABLE IF NOT EXISTS batches (seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,
                    source_id TEXT REFERENCES sources(id),start INTEGER,end INTEGER,start_line INTEGER,end_line INTEGER,
                    body BLOB,sha256 TEXT,anchor TEXT,records INTEGER,status TEXT,attempts INTEGER DEFAULT 0,
                    next_attempt REAL DEFAULT 0,created REAL,accepted REAL,report TEXT);
                CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT,at REAL,code TEXT,batch_id TEXT,details TEXT);
            ''')
            binding = json.dumps({'version': 1, 'source': str(config.source.resolve()),
                                  'api': config.api_url.rstrip('/'), 'sensor': config.sensor_id}, sort_keys=True)
            with self.db:
                previous = self.get('binding')
                if previous is not None and previous != binding: raise AgentError('checkpoint_binding_mismatch')
                if previous is None:
                    self.set('binding', binding); self.set('origin_id', str(uuid4())); self.note('initialized')
        except BaseException:
            if hasattr(self, 'db'): self.db.close()
            self.lock.close(); raise

    def close(self):
        self.db.close(); self.lock.close()  # Kernel releases both Windows and POSIX locks, including after a crash.

    def get(self, key):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    def set(self, key, value):
        self.db.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))

    def note(self, code, batch_id=None, **details):
        self.db.execute('INSERT INTO audit(at,code,batch_id,details) VALUES(?,?,?,?)',
                        (time.time(), code, batch_id, json.dumps(details, sort_keys=True)))

    def block(self, code, batch_id=None):
        with self.db:
            self.set('blocked', code); self.note(code, batch_id)
            if batch_id: self.db.execute("UPDATE batches SET status='blocked' WHERE id=?", (batch_id,))
        raise AgentError(code)

    def budget(self, extra=0):
        size = self.db.execute('PRAGMA page_count').fetchone()[0]*self.db.execute('PRAGMA page_size').fetchone()[0]
        if size+extra*2+65536 >= self.config.max_state_bytes or shutil.disk_usage(self.config.state_dir).free < self.config.min_free_bytes+extra*2:
            raise AgentError('state_capacity_exhausted')

    def source(self):
        return self.db.execute('SELECT * FROM sources WHERE current=1').fetchone()

    def begin_source(self, st, previous=None, reason='source_opened'):
        if not st.st_ino: self.block('unsupported_file_identity')
        if self.db.execute('SELECT count(*) FROM sources').fetchone()[0] >= 128: self.block('source_history_capacity')
        with self.db:
            if previous: self.db.execute('UPDATE sources SET current=0 WHERE id=?', (previous['id'],))
            sid = str(uuid4())
            self.db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',
                            (sid, str(st.st_dev), str(st.st_ino), 0, 0, '', 1, time.time()))
            self.note(reason, source_id=sid, previous=previous['id'] if previous else None)
        return self.source()

    def pending(self):
        row = self.db.execute("SELECT * FROM batches WHERE status IN ('pending','blocked') ORDER BY seq LIMIT 1").fetchone()
        if row:
            body = row['body']
            if (not isinstance(body, bytes) or not 1 <= len(body) <= 1024*1024 or not body.endswith(b'\n') or
                hashlib.sha256(body).hexdigest() != row['sha256'] or row['end']-row['start'] != len(body) or
                body.count(b'\n') != row['end_line']-row['start_line']+1 or
                sum(bool(line.strip()) for line in body.split(b'\n')[:-1]) != row['records']):
                self.block('spool_integrity_failure', row['id'])
        return row

    def spool(self, source, body, end, lines, anchor):
        self.budget(len(body))
        bid = str(uuid4()); records = sum(bool(line.strip()) for line in body.split(b'\n')[:-1])
        with self.db:
            self.db.execute('''INSERT INTO batches(id,source_id,start,end,start_line,end_line,body,sha256,anchor,records,status,created)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (bid, source['id'], source['offset'], end, source['line']+1,
                source['line']+lines, body, hashlib.sha256(body).hexdigest(), anchor, records, 'pending', time.time()))
            self.note('spooled', bid, source_id=source['id'], start=source['offset'], end=end, lines=lines)
        return self.pending()

    def attempt(self, batch):
        with self.db:
            self.db.execute('UPDATE batches SET attempts=attempts+1 WHERE id=?', (batch['id'],)); self.note('attempt', batch['id'])

    def retry(self, batch, code, delay):
        with self.db:
            self.db.execute('UPDATE batches SET next_attempt=? WHERE id=?', (time.time()+delay, batch['id']))
            self.note(code, batch['id'], retry_seconds=delay)

    def accept(self, batch, report, actor_id):
        with self.db:
            current = self.source()
            if current['id'] != batch['source_id'] or current['offset'] != batch['start']: raise AgentError('checkpoint_conflict')
            self.db.execute('UPDATE sources SET offset=?,line=?,anchor=? WHERE id=?',
                (batch['end'], batch['end_line'], batch['anchor'], batch['source_id']))
            # Rejected/unsupported lines keep their exact bounded original batch for audit; never silently discarded.
            self.db.execute("UPDATE batches SET status='accepted',accepted=?,report=?,body=? WHERE id=?",
                (time.time(), json.dumps(report, sort_keys=True), batch['body'] if report['discarded'] else None, batch['id']))
            self.note('accepted_with_quarantine' if report['discarded'] else 'accepted', batch['id'],
                      actor_id=actor_id, imported=report['imported'], duplicates=report['duplicates'], discarded=report['discarded'])

    def resume(self, accept_reset=False):
        blocked = self.get('blocked')
        if not blocked: return
        if blocked.startswith('source_') or blocked in ('rotation_gap', 'ambiguous_rotation', 'rotated_incomplete_line', 'late_retired_growth', 'line_too_large'):
            if not accept_reset: raise AgentError('explicit_source_reset_required')
            if self.pending(): raise AgentError('pending_batch_prevents_source_reset')
            st = self.config.source.stat()
            self.begin_source(st, self.source(), 'operator_source_reset_gap_possible')
        elif accept_reset: raise AgentError('pending_batch_prevents_source_reset')
        with self.db:
            self.set('blocked', ''); self.db.execute("UPDATE batches SET status='pending' WHERE status='blocked'")
            self.note('operator_resumed', accepted_source_gap=accept_reset)
