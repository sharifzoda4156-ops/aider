"""Optional trusted, content-addressed symbol cache; JSON only, never pickle."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path

SCHEMA = 1
MAX_ENTRY_BYTES = 2 * 1024 * 1024
MAX_CACHE_BYTES = 64 * 1024 * 1024


def parser_identity():
    packages = ('grep-ast', 'tree-sitter', 'tree-sitter-language-pack',
                'tree-sitter-languages', 'Pygments')
    versions = {}
    for name in packages:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def cache_key(code, language, query, basename, parser_versions, implementation):
    identity = json.dumps([SCHEMA, language, query, basename, parser_versions,
                           implementation], sort_keys=True).encode()
    return hashlib.sha256(identity + b'\0' + code.encode('utf-8')).hexdigest()


class SymbolCache:
    def __init__(self, directory, max_bytes=MAX_CACHE_BYTES):
        directory = Path(directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / 'symbols-v1.sqlite3'
        self.max_bytes = max_bytes
        self.stats = dict(hits=0, misses=0, writes=0, errors=0)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tags (key TEXT PRIMARY KEY, '
                       'payload TEXT NOT NULL, bytes INTEGER NOT NULL, used INTEGER NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=1)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key):
        try:
            with self.connect() as db:
                row = db.execute('SELECT payload FROM tags WHERE key=?', (key,)).fetchone()
                if not row:
                    self.stats['misses'] += 1
                    return None
                if not isinstance(row[0], str) or len(row[0].encode()) > MAX_ENTRY_BYTES:
                    raise ValueError('oversized cached symbols')
                data = json.loads(row[0])
                if not isinstance(data, list) or any(
                    not isinstance(t, list) or len(t) != 3 or
                    not isinstance(t[0], int) or not isinstance(t[1], str) or
                    t[2] not in ('def', 'ref') for t in data
                ):
                    raise ValueError('invalid cached symbols')
                db.execute('UPDATE tags SET used=? WHERE key=?', (time.time_ns(), key))
            self.stats['hits'] += 1
            return data
        except (sqlite3.Error, OSError, ValueError, TypeError, UnicodeError):
            self.stats['errors'] += 1
            return None

    def put(self, key, tags):
        payload = json.dumps(tags, ensure_ascii=False)
        size = len(payload.encode())
        if size > min(MAX_ENTRY_BYTES, self.max_bytes):
            return
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT OR REPLACE INTO tags VALUES (?, ?, ?, ?)',
                           (key, payload, size, time.time_ns()))
                total = db.execute('SELECT COALESCE(SUM(bytes),0) FROM tags').fetchone()[0]
                for old_key, old_size in db.execute(
                    'SELECT key, bytes FROM tags ORDER BY used, key'
                ).fetchall():
                    if total <= self.max_bytes:
                        break
                    db.execute('DELETE FROM tags WHERE key=?', (old_key,))
                    total -= old_size
            self.stats['writes'] += 1
        except (sqlite3.Error, OSError):
            self.stats['errors'] += 1
