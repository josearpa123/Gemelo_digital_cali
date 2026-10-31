"""Tracing of the whole digital twin: simulation, RL agents, injected events, LLM assistant
and training.

Cost matters: the simulation must not lose more than 5 % of its speed to tracing
(eval/bench_tracing.py). So `emit` only builds a dict and appends it to a list; a thread
hands the accumulated batch every `flush_every` seconds to a separate *process* that
writes SQLite and the JSON-lines log. Waking a thread per event, or serialising and
writing in this process, competes with the simulation thread for the GIL."""

import itertools
import json
import logging
import multiprocessing
import os
import sqlite3
import threading
import time
import uuid
from collections import deque
from pathlib import Path

COMPONENTS = ("sim", "rl", "event", "llm", "training")
STATUSES = ("ok", "warn", "error", "fallback")
# environment variables whose values must never reach a trace, log or API response
SECRET_ENV = ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY")
SECRET_KEYS = {"api_key", "authorization", "apikey", "key", "token", "password"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY,
    trace_id TEXT NOT NULL,
    ts REAL NOT NULL,
    sim_t REAL,
    component TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    tls_id TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_component ON events (component, seq);
CREATE INDEX IF NOT EXISTS events_tls ON events (tls_id, seq);
CREATE INDEX IF NOT EXISTS events_trace ON events (trace_id);
CREATE TABLE IF NOT EXISTS ingest (file TEXT PRIMARY KEY, offset INTEGER NOT NULL);
"""

log = logging.getLogger("traces")


# random per process + counter: unique and much cheaper than a uuid4 per event
_ID_PREFIX = uuid.uuid4().hex[:6]
_ID_COUNTER = itertools.count(1)


def new_trace_id() -> str:
    return f"{_ID_PREFIX}{next(_ID_COUNTER):010x}"


def secrets_from_env() -> list[str]:
    return [v for name in SECRET_ENV if len(v := os.environ.get(name, "")) >= 8]


def scrub(data: dict, secrets: list[str] | None = None) -> dict:
    """Drop secret-looking keys and mask any configured secret value inside strings."""
    secrets = secrets_from_env() if secrets is None else secrets
    if SECRET_KEYS.isdisjoint(k.lower() for k in data):
        clean = data
    else:
        clean = {k: v for k, v in data.items() if k.lower() not in SECRET_KEYS}
    if not secrets:
        return clean
    text = json.dumps(clean, default=str)
    if not any(s in text for s in secrets):
        return clean
    for s in secrets:
        text = text.replace(s, "***")
    return json.loads(text)


def connect(db_path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


def _log_line(e: dict, data: str) -> str:
    head = json.dumps({k: v for k, v in e.items() if k != "data"}, ensure_ascii=False)
    return f'{head[:-1]}, "data": {data}}}'


def store_batch(db, log_path: Path | None, log_max_bytes: int, batch: list[dict]) -> None:
    """Write events to SQLite and append them to the JSON-lines log (rotated to .1)."""
    rows, lines = [], []
    for e in batch:
        data = json.dumps(e["data"], default=str, ensure_ascii=False)
        rows.append(
            (
                e["seq"],
                e["trace_id"],
                e["ts"],
                e["sim_t"],
                e["component"],
                e["type"],
                e["status"],
                e["tls_id"],
                data,
            )
        )
        if log_path or e["status"] in ("error", "fallback"):
            line = _log_line(e, data)
            lines.append(line)
            if e["status"] in ("error", "fallback"):
                log.warning(line)
    if db is not None:
        try:
            db.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?)", rows)
            db.commit()
        except sqlite3.Error as exc:  # tracing must never take the simulation down
            log.warning("traces: sqlite write failed: %s", exc)
    if log_path and lines:
        try:
            if log_path.exists() and log_path.stat().st_size > log_max_bytes:
                log_path.replace(log_path.with_suffix(log_path.suffix + ".1"))
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError as exc:
            log.warning("traces: log write failed: %s", exc)


def _writer_process(db_path, log_path, log_max_bytes, inbox, written, ready) -> None:
    """Child process: stores every batch it receives; `None` ends it."""
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    db = connect(db_path) if db_path else None
    ready.set()
    while True:
        batch = inbox.get()
        if batch is None:
            break
        store_batch(db, log_path, log_max_bytes, batch)
        written.value = batch[-1]["seq"]
    if db is not None:
        db.close()


class Tracer:
    """Collects events. `db_path=None` and `log_path=None` keep them only in memory."""

    enabled = True

    def __init__(
        self,
        db_path: Path | None = None,
        log_path: Path | None = None,
        recent: int = 5000,
        flush_every: float = 0.5,
        log_max_bytes: int = 20_000_000,
    ):
        self.db_path = Path(db_path) if db_path else None
        self.log_path = Path(log_path) if log_path else None
        self._secrets = secrets_from_env()
        self._pending: list[dict] = []
        self._recent: deque[dict] = deque(maxlen=recent)
        self._lock = threading.Lock()
        self._flush_every = flush_every
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._seq = 0
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with connect(self.db_path) as db:
                db.executescript(SCHEMA)
                self._seq = db.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._proc = None
        if self.db_path or self.log_path:
            ctx = multiprocessing.get_context("spawn")  # never fork a process running libsumo
            self._inbox = ctx.Queue()
            self._written = ctx.Value("q", self._seq)
            ready = ctx.Event()
            self._proc = ctx.Process(
                target=_writer_process,
                args=(
                    self.db_path,
                    self.log_path,
                    log_max_bytes,
                    self._inbox,
                    self._written,
                    ready,
                ),
                name="trace-writer",
                daemon=True,
            )
            self._proc.start()
            ready.wait(30)
        self._sent = self._seq
        self._mem_written = self._seq
        self._writer = threading.Thread(target=self._hand_off, name="trace-handoff", daemon=True)
        self._writer.start()

    def add_secret(self, value: str) -> None:
        """Mask a secret that appeared after start-up (a key entered in the panel)."""
        if len(value) >= 8 and value not in self._secrets:
            self._secrets = [*self._secrets, value]

    # ---- producing ----------------------------------------------------------------------
    def emit(
        self,
        component: str,
        type: str,
        status: str = "ok",
        data: dict | None = None,
        sim_t: float | None = None,
        tls_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        if component not in COMPONENTS:
            raise ValueError(f"unknown component: {component}")
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        event = {
            "seq": 0,
            "trace_id": trace_id or new_trace_id(),
            "ts": time.time(),
            "sim_t": sim_t,
            "component": component,
            "type": type,
            "status": status,
            "tls_id": tls_id,
            # simulation and RL data come from SUMO and cannot hold a key: only text that
            # crossed a process boundary (LLM, trainer files) is scanned for secret values
            "data": scrub(data, self._secrets if component in ("llm", "training") else [])
            if data
            else {},
        }
        with self._lock:
            self._seq += 1
            event["seq"] = self._seq
            self._recent.append(event)
            self._pending.append(event)
        return event

    def since(self, seq: int, limit: int = 500) -> list[dict]:
        """Events newer than `seq` still held in memory (for the WebSocket)."""
        with self._lock:
            if not self._recent or self._recent[-1]["seq"] <= seq:
                return []
            out = [e for e in self._recent if e["seq"] > seq]
        return out[-limit:]

    @property
    def last_seq(self) -> int:
        return self._seq

    # ---- storing ------------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def _hand_off(self) -> None:
        while True:
            self._wake.wait(self._flush_every)
            self._wake.clear()
            with self._lock:
                batch, self._pending = self._pending, []
            if batch:
                if self._proc is not None:
                    self._inbox.put(batch)
                self._sent = batch[-1]["seq"]
            if self._stop.is_set() and not self._pending:
                break

    @property
    def written(self) -> int:
        return self._written.value if self._proc is not None else self._sent

    def flush(self, timeout: float = 15.0) -> None:
        """Block until every event emitted so far has been written."""
        target = self._seq
        deadline = time.monotonic() + timeout
        while self.written < target and time.monotonic() < deadline:
            self._wake.set()
            time.sleep(0.01)

    def close(self) -> None:
        self.flush()
        self._stop.set()
        self._wake.set()
        self._writer.join(timeout=5)
        if self._proc is not None:
            self._inbox.put(None)
            self._proc.join(timeout=10)

    # ---- reading ------------------------------------------------------------------------
    def query(
        self,
        component: str | None = None,
        tls_id: str | None = None,
        type: str | None = None,
        since: float | None = None,
        until: float | None = None,
        trace_id: str | None = None,
        after_seq: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Newest-first events from SQLite (or from memory without a database)."""
        if not self.db_path:
            events = [
                e
                for e in reversed(self._recent)
                if (component is None or e["component"] == component)
                and (tls_id is None or e["tls_id"] == tls_id)
                and (type is None or e["type"] == type)
                and (since is None or e["ts"] >= since)
                and (until is None or e["ts"] <= until)
                and (trace_id is None or e["trace_id"] == trace_id)
                and (after_seq is None or e["seq"] > after_seq)
            ]
            return events[:limit]
        where, args = [], []
        for column, op, value in (
            ("component", "=", component),
            ("tls_id", "=", tls_id),
            ("type", "=", type),
            ("ts", ">=", since),
            ("ts", "<=", until),
            ("trace_id", "=", trace_id),
            ("seq", ">", after_seq),
        ):
            if value is not None:
                where.append(f"{column} {op} ?")
                args.append(value)
        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY seq DESC LIMIT ?"
        args.append(limit)
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(sql, args).fetchall()
        return [dict(r) | {"data": json.loads(r["data"])} for r in rows]

    def counts(self) -> list[tuple[str, str, str, int]]:
        """(component, type, status, n) over every stored event."""
        if not self.db_path:
            from collections import Counter

            c = Counter((e["component"], e["type"], e["status"]) for e in self._recent)
            return [(*k, n) for k, n in c.items()]
        with self._connect() as db:
            return db.execute(
                "SELECT component, type, status, COUNT(*) FROM events "
                "GROUP BY component, type, status"
            ).fetchall()

    def all_events(self) -> list[dict]:
        return list(reversed(self.query(limit=10**9)))

    # ---- external files (training) ------------------------------------------------------
    def ingest_jsonl(self, folder: Path) -> int:
        """Emit events written by other processes (the trainer) as JSON lines, once each."""
        folder = Path(folder)
        if not folder.is_dir():
            return 0
        offsets = {}
        if self.db_path:
            with self._connect() as db:
                offsets = dict(db.execute("SELECT file, offset FROM ingest").fetchall())
        else:
            offsets = getattr(self, "_offsets", {})
        count = 0
        for path in sorted(folder.glob("*.jsonl")):
            start = offsets.get(path.name, 0)
            if path.stat().st_size <= start:
                continue
            with path.open("rb") as fh:
                fh.seek(start)
                for raw in fh:
                    if not raw.endswith(b"\n"):
                        break  # line still being written
                    start += len(raw)
                    try:
                        item = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    status = item.pop("status", "ok")
                    self.emit(
                        "training",
                        str(item.pop("type", "episodio")),
                        status if status in STATUSES else "warn",
                        data=item,
                        trace_id=item.get("run_id"),
                    )
                    count += 1
            offsets[path.name] = start
        if self.db_path:
            with self._connect() as db:
                db.executemany("INSERT OR REPLACE INTO ingest VALUES (?, ?)", offsets.items())
        else:
            self._offsets = offsets
        return count


class NullTracer:
    """Tracing switched off (benchmarks, tools that do not need it)."""

    enabled = False
    last_seq = 0

    def emit(self, *args, **kwargs) -> dict:
        return {}

    def since(self, seq: int, limit: int = 500) -> list[dict]:
        return []

    def flush(self, timeout: float = 0) -> None:
        pass

    def close(self) -> None:
        pass
