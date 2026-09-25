"""Bounded worker queue with durable state and cooperative cancellation."""

from datetime import datetime, timezone
from contextlib import contextmanager
import json
import logging
from pathlib import Path
from queue import Queue
import sqlite3
from threading import Event, Lock, Thread
import uuid


class QueueFull(RuntimeError):
    pass


class JobQueue:
    def __init__(self, path: Path, capacity: int = 8):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.capacity = capacity
        self.active: dict[str, Event] = {}
        self.pending = Queue()
        self.closed = False
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, state TEXT, updated_at TEXT, payload TEXT)")
            db.execute("UPDATE jobs SET state='falhou', payload=? WHERE state IN ('aguardando','executando','cancelando')",
                       (json.dumps({"error": "Servidor reiniciado; analise nao foi retomada automaticamente."}),))
        self.worker = Thread(target=self._work, daemon=True, name="integrity-worker")
        self.worker.start()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _save(self, identifier, state, payload=None):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?)",
                       (identifier, state, datetime.now(timezone.utc).isoformat(), json.dumps(payload or {}, ensure_ascii=False, allow_nan=False)))

    def submit(self, operation) -> str:
        with self.lock:
            if self.closed or len(self.active) >= self.capacity:
                raise QueueFull("Fila cheia. Aguarde uma analise terminar.")
            identifier = uuid.uuid4().hex
            event = Event()
            self._save(identifier, "aguardando")
            self.active[identifier] = event
            self.pending.put((identifier, event, operation))
            return identifier

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT state, updated_at, payload FROM jobs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            return None
        return {"id": identifier, "state": row[0], "updated_at": row[1], **json.loads(row[2])}

    def cancel(self, identifier):
        with self.lock:
            event = self.active.get(identifier)
            if event:
                current = self.get(identifier)
                if current and current['state'] in {'aguardando', 'executando', 'cancelando'}:
                    event.set()
                    self._save(identifier, "cancelada" if current["state"] == "aguardando" else "cancelando")
        return self.get(identifier)

    def _work(self):
        while True:
            item = self.pending.get()
            if item is None:
                self.pending.task_done()
                break
            identifier, event, operation = item
            try:
                with self.lock:
                    if event.is_set():
                        self._save(identifier, "cancelada")
                    else:
                        self._save(identifier, "executando")
                if not event.is_set():
                    result = operation(event.is_set)
                    with self.lock:
                        if event.is_set():
                            self._save(identifier, "cancelada")
                        else:
                            state = "falhou" if result.get("status") == "nao_concluida" else "concluida"
                            self._save(identifier, state, {"result": result})
            except Exception as exc:
                # Exception text may contain provider credentials or image data.
                logging.getLogger(__name__).error('Job %s failed (%s)', identifier, type(exc).__name__)
                try:
                    with self.lock:
                        self._save(identifier, "cancelada" if event.is_set() else "falhou",
                                   {"error": "Falha interna na analise. Consulte os registros locais."})
                except Exception:
                    logging.getLogger(__name__).error('Could not persist failure for job %s', identifier)
            finally:
                with self.lock:
                    self.active.pop(identifier, None)
                self.pending.task_done()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for event in self.active.values():
                event.set()
        self.pending.put(None)
        self.worker.join()
