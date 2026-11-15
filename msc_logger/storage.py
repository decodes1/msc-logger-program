"""Transactional local storage and verified, rotating database backups."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, last_day INTEGER NOT NULL, checks TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS completions (
    id INTEGER PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
    day INTEGER NOT NULL, operator TEXT NOT NULL, note TEXT NOT NULL,
    created REAL NOT NULL, UNIQUE(task_id, day)
);
CREATE TABLE IF NOT EXISTS inventory (
    id TEXT PRIMARY KEY, quantity INTEGER NOT NULL CHECK(quantity >= 0),
    revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY, category TEXT NOT NULL, description TEXT NOT NULL,
    priority TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
    ack_at REAL, receipt TEXT, context TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY, tree TEXT NOT NULL, choice INTEGER NOT NULL,
    outcome TEXT NOT NULL, note TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY, sensor TEXT NOT NULL, value REAL NOT NULL,
    observed REAL NOT NULL, received REAL NOT NULL, source TEXT NOT NULL,
    UNIQUE(sensor, observed)
);
CREATE INDEX IF NOT EXISTS samples_sensor_time ON samples(sensor, observed DESC);
CREATE INDEX IF NOT EXISTS reports_queue ON reports(status, next_at);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, created REAL NOT NULL, level TEXT NOT NULL,
    kind TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL,
    created REAL NOT NULL
);
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        try:
            if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("Database integrity check failed")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise sqlite3.DatabaseError("This database needs a newer MSC Logger")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript(SCHEMA)
            self.db.execute("PRAGMA user_version=1")
        except Exception:
            self.db.close()
            raise

    @contextmanager
    def transaction(self):
        with self.lock:
            with self.db:
                yield self.db

    def backup(self, destination):
        destination = Path(destination)
        temporary = destination.with_suffix(".pending")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            target = sqlite3.connect(temporary)
            try:
                self.db.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("Backup verification failed")
            finally:
                target.close()
        temporary.replace(destination)
        return destination

    def close(self):
        with self.lock:
            self.db.close()


def setting(db, key):
    return json.loads(db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()[0])


def set_setting(db, key, value):
    db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
