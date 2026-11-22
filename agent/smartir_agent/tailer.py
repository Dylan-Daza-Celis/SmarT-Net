import hashlib
import os
import stat
import time
from .config import AgentError, MAX_LINE_BYTES


def identity(st): return str(st.st_dev), str(st.st_ino)
def source_identity(row): return row['device'], row['inode']


def anchor_at(stream, position):
    stream.seek(max(0, position-128))
    return hashlib.sha256(stream.read(min(128, position))).hexdigest() if position else ''


class Tailer:
    def __init__(self, store):
        self.store, self.config = store, store.config
        self.eof = None
        self.observation = None

    def observe(self, code):
        if code != self.observation:
            with self.store.db: self.store.note(code)
            self.observation = code

    def candidates(self):
        path = self.config.source
        result = []
        try:
            with os.scandir(path.parent) as entries:
                for n, entry in enumerate(entries):
                    if n >= 1000: self.store.block('source_directory_capacity')
                    if entry.name != path.name and not entry.name.startswith(path.name+'.'): continue
                    if entry.is_symlink(): self.store.block('source_symlink_detected')
                    # Windows DirEntry.stat can cache st_ino=0; os.stat obtains the actual file identity.
                    st = os.stat(entry.path, follow_symlinks=False)
                    if not stat.S_ISREG(st.st_mode): self.store.block('source_not_regular')
                    result.append((path.parent/entry.name, st))
                    if len(result) > 128: self.store.block('source_directory_capacity')
        except FileNotFoundError: return []
        return result

    def next_rotation(self, current_path, files, source):
        base = self.config.source
        retired = {source_identity(r) for r in self.store.db.execute('SELECT * FROM sources WHERE current=0')}
        other = [(p, st) for p, st in files if identity(st) != source_identity(source) and identity(st) not in retired]
        if not other: return None
        suffix = current_path.name.removeprefix(base.name+'.')
        if current_path != base and suffix.isdigit() and int(suffix) > 0:
            # Standard rename/create: .3 -> .2 -> .1 -> current, even after multiple offline rotations.
            number = int(suffix)-1
            expected = base.with_name(base.name+'.'+str(number)) if number else base
            chosen = next(((p, st) for p, st in other if p == expected), None)
            if chosen is None: self.store.block('rotation_gap')
            return chosen
        if len(other) != 1 or other[0][0] != base: self.store.block('ambiguous_rotation')
        return other[0]

    def poll(self):
        pending = self.store.pending()
        if pending: return pending
        self.store.budget()
        files = self.candidates()
        by_id = {identity(st):(p, st) for p, st in files}
        source = self.store.source()
        # Detect observable late writes to already retired generations, never silently skip them.
        seen = {source_identity(source)} if source else set()
        for row in self.store.db.execute('SELECT * FROM sources WHERE current=0 ORDER BY rowid DESC'):
            key = source_identity(row)
            if key in seen: continue  # Explicit copytruncate reset creates a new generation on the same inode.
            seen.add(key)
            item = by_id.get(key)
            if item and item[1].st_size > row['offset']: self.store.block('late_retired_growth')
        if source is None:
            current = next(((p, st) for p, st in files if p == self.config.source), None)
            if not current:
                self.observe('waiting_for_file'); return None
            # Initial old archives cannot be ordered reliably: initial run starts current at byte zero.
            source = self.store.begin_source(current[1])
            if len(files)>1:
                with self.store.db: self.store.note('initial_archives_not_replayed', count=len(files)-1)
        located = by_id.get(source_identity(source))
        if located is None: self.store.block('rotation_gap')
        path, st = located
        try:
            with path.open('rb') as stream:
                if identity(os.fstat(stream.fileno())) != source_identity(source): return None  # Rename race: rescan.
                if st.st_size < source['offset'] or anchor_at(stream, source['offset']) != source['anchor']:
                    self.store.block('source_truncated_or_rewritten')
                stream.seek(max(0, source['offset']-128))
                previous_tail = stream.read(min(128, source['offset']))
                stream.seek(source['offset'])
                body = bytearray(); count = 0; end = source['offset']; incomplete = False
                while count < self.config.batch_lines:
                    start = stream.tell(); line = stream.readline(MAX_LINE_BYTES+2)
                    if not line: break
                    if len(line.rstrip(b'\n')) > MAX_LINE_BYTES: self.store.block('line_too_large')
                    if not line.endswith(b'\n'):
                        incomplete = True; break
                    if len(body)+len(line) > self.config.batch_bytes:
                        stream.seek(start); break
                    body.extend(line); count += 1; end = stream.tell()
                if body:
                    fingerprint = anchor_at(stream, end)
                    captured = hashlib.sha256((previous_tail+body)[-128:]).hexdigest()
                    if os.fstat(stream.fileno()).st_size < end or fingerprint != captured:
                        self.store.block('source_changed_during_read')
                    self.eof = None
                    self.observation = 'batch_ready'
                    return self.store.spool(source, bytes(body), end, count, fingerprint)
        except FileNotFoundError: return None  # Retain offset; next scan resolves or blocks the gap.
        if path != self.config.source:
            if incomplete: self.store.block('rotated_incomplete_line')
            key = source['id'], st.st_size
            if self.eof is None or self.eof[0] != key: self.eof = key, time.monotonic()
            if time.monotonic()-self.eof[1] >= self.config.rotate_wait_seconds:
                next_file = self.next_rotation(path, files, source)
                if next_file:
                    self.store.begin_source(next_file[1], source, 'rotation'); self.eof = None
        else: self.observe('waiting_for_newline' if incomplete else 'waiting_for_append')
        return None
