"""SQLite-lagring. En fil, WAL-läge, enkel att säkerhetskopiera.

Tabeller:
  samples   tidsserie från klockan (puls, hrv, spo2, steg, hudtemp ...), en rad per mätpunkt
  sleep     sömnpass med faser
  journal   journalanteckningar från 1177
  labs      provsvar från 1177
  events    allt som händer i systemet (vakt, konsilium, larm) - driver även live-vyn
  consults  konsiliemöten med hela samtalet och slutbedömningen
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts      REAL NOT NULL,          -- unix-sekunder, UTC
    metric  TEXT NOT NULL,          -- hr, hrv_rmssd, spo2, steps, skin_temp, resp_rate, ...
    value   REAL NOT NULL,
    source  TEXT NOT NULL DEFAULT 'watch',
    PRIMARY KEY (metric, ts, source)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sleep (
    id      TEXT PRIMARY KEY,
    start   REAL NOT NULL,
    end     REAL NOT NULL,
    stages  TEXT NOT NULL,          -- json: [{start, end, stage}]
    source  TEXT NOT NULL DEFAULT 'watch'
);

CREATE TABLE IF NOT EXISTS journal (
    id       TEXT PRIMARY KEY,      -- stabil hash av innehållet
    date     TEXT NOT NULL,         -- YYYY-MM-DD
    unit     TEXT,                  -- vårdenhet
    author   TEXT,                  -- yrkesroll
    kind     TEXT,                  -- anteckning, diagnos, vaccination, remiss ...
    title    TEXT,
    text     TEXT NOT NULL,
    fetched  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS labs (
    id        TEXT PRIMARY KEY,
    date      TEXT NOT NULL,
    analyte   TEXT NOT NULL,
    value     REAL,
    value_raw TEXT NOT NULL,
    unit      TEXT,
    ref_low   REAL,
    ref_high  REAL,
    flag      TEXT,                 -- H, L eller NULL
    fetched   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    kind    TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS consults (
    id       TEXT PRIMARY KEY,
    started  REAL NOT NULL,
    ended    REAL,
    trigger  TEXT NOT NULL,         -- json: vad som startade mötet
    transcript TEXT NOT NULL DEFAULT '[]',
    verdict  TEXT,                  -- json: slutbedömning efter granskning
    stats    TEXT                   -- json: tokens, tid, modeller
);
"""

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    path = Path(settings.db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def conn() -> sqlite3.Connection:
    global _initialized
    c = getattr(_local, "con", None)
    if c is None:
        c = _connect()
        _local.con = c
    if not _initialized:
        with _init_lock:
            if not _initialized:
                c.executescript(SCHEMA)
                _initialized = True
    return c


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    c = conn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise


def insert_samples(rows: Iterable[tuple[float, str, float, str]]) -> int:
    rows = list(rows)
    with tx() as c:
        c.executemany(
            "INSERT OR REPLACE INTO samples(ts, metric, value, source) VALUES (?,?,?,?)", rows
        )
    return len(rows)


def query_samples(metric: str, start: float, end: float | None = None) -> list[tuple[float, float]]:
    end = end or time.time()
    cur = conn().execute(
        "SELECT ts, value FROM samples WHERE metric=? AND ts BETWEEN ? AND ? ORDER BY ts",
        (metric, start, end),
    )
    return [(r[0], r[1]) for r in cur]


def metrics_available() -> list[dict[str, Any]]:
    cur = conn().execute(
        "SELECT metric, COUNT(*) n, MIN(ts) first, MAX(ts) last FROM samples GROUP BY metric"
    )
    return [dict(r) for r in cur]


def add_event(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    ts = time.time()
    with tx() as c:
        cur = c.execute(
            "INSERT INTO events(ts, kind, payload) VALUES (?,?,?)",
            (ts, kind, json.dumps(payload, ensure_ascii=False)),
        )
    return {"id": cur.lastrowid, "ts": ts, "kind": kind, "payload": payload}


def recent_events(limit: int = 200, kinds: list[str] | None = None) -> list[dict[str, Any]]:
    q = "SELECT id, ts, kind, payload FROM events"
    args: list[Any] = []
    if kinds:
        q += f" WHERE kind IN ({','.join('?' * len(kinds))})"
        args += kinds
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = conn().execute(q, args).fetchall()
    return [
        {"id": r["id"], "ts": r["ts"], "kind": r["kind"], "payload": json.loads(r["payload"])}
        for r in reversed(rows)
    ]
