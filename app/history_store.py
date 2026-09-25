"""Transactional local history; legacy JSON is imported once, without rewriting it."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3


class HistoryStore:
    def __init__(self, path: Path, legacy: Path | None = None):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS history (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, model TEXT,
                    verdict TEXT, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS history_date ON history(created_at DESC);
                CREATE INDEX IF NOT EXISTS history_model ON history(model);
                CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY);
            """)
            if legacy and legacy.exists():
                marker = "legacy:" + str(legacy.resolve())
                if db.execute("SELECT 1 FROM migrations WHERE name=?", (marker,)).fetchone() is None:
                    # Fail loudly on a corrupt legacy file instead of losing its history.
                    entries = json.loads(legacy.read_text(encoding="utf-8-sig"))
                    if not isinstance(entries, list):
                        raise ValueError("Historico legado invalido: esperado uma lista.")
                    for index, entry in enumerate(entries):
                        if isinstance(entry, dict):
                            self._insert(db, entry, fallback=f"legacy-{index}", ignore=True)
                    db.execute("INSERT INTO migrations VALUES (?)", (marker,))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _insert(db, entry: dict, fallback: str = "", ignore: bool = False):
        payload = json.dumps(entry, ensure_ascii=False, allow_nan=False)
        identifier = entry.get("id") or entry.get("analysis_id") or fallback or hashlib.sha256(payload.encode()).hexdigest()
        action = "IGNORE" if ignore else "REPLACE"
        db.execute(f"INSERT OR {action} INTO history VALUES (?, ?, ?, ?, ?)",
                   (identifier, entry.get("created_at", ""), entry.get("model"), entry.get("verdict"), payload))

    def append(self, entry: dict):
        with self.connection() as db:
            self._insert(db, entry)

    def upsert_all(self, entries: list[dict]):
        with self.connection() as db:
            for entry in entries:
                self._insert(db, entry)

    def all(self) -> list[dict]:
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM history ORDER BY created_at DESC, rowid DESC")]

    def backup(self, target: Path):
        target.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(target)
        try:
            with self.connection() as db:
                db.backup(destination)
        finally:
            destination.close()
