"""HTTP- och WebSocket-API. Kontraktet som mobilappen och webben byggs mot.

POST /api/ingest            batch med mätpunkter från mobilen (som fått dem från klockan)
POST /api/ingest/sleep      sömnpass
GET  /api/series/{metric}   tidsserie, ?hours=24
GET  /api/metrics           vilka mätvärden som finns
GET  /api/events            senaste händelserna, ?limit=200
GET  /api/consults          konsiliemöten
GET  /api/consults/{id}     ett möte med hela samtalet
POST /api/consult           starta ett konsilium manuellt (fråga från användaren)
GET  /api/journal           journal och provsvar
POST /api/sync/1177         starta journalhämtning (kräver BankID i mobilen)
WS   /ws                    live-ström av alla händelser (se bus.py för typer)

Autentisering: Cloudflare Access framför allt som nås utifrån. Mobilappen skickar dessutom
X-Device-Token som jämförs med KONSILIET_DEVICE_TOKENS. Anrop från localhost släpps igenom.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .bus import bus
from .config import settings

app = FastAPI(title="Konsiliet", version="0.1.0")

WEB_DIR = Path(__file__).resolve().parents[3] / "web" / "dist"


def _is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    # Cloudflare Tunnel ansluter från localhost men sätter Cf-Connecting-Ip.
    return host in ("127.0.0.1", "::1") and "cf-connecting-ip" not in request.headers


def auth(request: Request, x_device_token: str | None = Header(default=None)) -> None:
    if _is_local(request):
        return
    if x_device_token and x_device_token in settings.device_tokens:
        return
    if request.headers.get("cf-access-authenticated-user-email"):
        return
    raise HTTPException(status_code=401, detail="Ej behörig")


class Sample(BaseModel):
    ts: float = Field(description="unix-sekunder UTC")
    metric: str
    value: float


class IngestBatch(BaseModel):
    source: str = "watch"
    samples: list[Sample]


class SleepStage(BaseModel):
    start: float
    end: float
    stage: str  # awake, light, deep, rem


class SleepSession(BaseModel):
    id: str
    start: float
    end: float
    stages: list[SleepStage]
    source: str = "watch"


class ConsultRequest(BaseModel):
    question: str
    hours: int = 72


@app.on_event("startup")
async def _startup() -> None:
    bus.bind(asyncio.get_running_loop())
    db.conn()
    from . import vakt  # noqa: F401  startar vaktens bakgrundsloop

    vakt.start()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "ts": time.time()}


@app.post("/api/ingest", dependencies=[Depends(auth)])
def ingest(batch: IngestBatch) -> dict[str, Any]:
    rows = [(s.ts, s.metric, s.value, batch.source) for s in batch.samples]
    n = db.insert_samples(rows)
    # Senaste värdet per mätvärde går ut live, utan att sparas som händelse.
    latest: dict[str, Sample] = {}
    for s in batch.samples:
        if s.metric not in latest or s.ts > latest[s.metric].ts:
            latest[s.metric] = s
    for s in latest.values():
        bus.publish("sample.live", s.model_dump(), persist=False)
    from . import vakt

    vakt.notify_new_data([s.metric for s in latest.values()])
    return {"stored": n}


@app.post("/api/ingest/sleep", dependencies=[Depends(auth)])
def ingest_sleep(sess: SleepSession) -> dict[str, Any]:
    with db.tx() as c:
        c.execute(
            "INSERT OR REPLACE INTO sleep(id, start, end, stages, source) VALUES (?,?,?,?,?)",
            (sess.id, sess.start, sess.end, json.dumps([s.model_dump() for s in sess.stages]), sess.source),
        )
    return {"stored": 1}


@app.get("/api/metrics", dependencies=[Depends(auth)])
def metrics() -> list[dict[str, Any]]:
    return db.metrics_available()


@app.get("/api/series/{metric}", dependencies=[Depends(auth)])
def series(metric: str, hours: float = 24) -> dict[str, Any]:
    start = time.time() - hours * 3600
    pts = db.query_samples(metric, start)
    return {"metric": metric, "points": pts}


@app.get("/api/sleep", dependencies=[Depends(auth)])
def sleep(days: int = 14) -> list[dict[str, Any]]:
    since = time.time() - days * 86400
    rows = db.conn().execute("SELECT * FROM sleep WHERE end > ? ORDER BY start", (since,)).fetchall()
    return [{**dict(r), "stages": json.loads(r["stages"])} for r in rows]


@app.get("/api/events", dependencies=[Depends(auth)])
def events(limit: int = 200) -> list[dict[str, Any]]:
    return db.recent_events(limit)


@app.get("/api/consults", dependencies=[Depends(auth)])
def consults(limit: int = 50) -> list[dict[str, Any]]:
    rows = db.conn().execute(
        "SELECT id, started, ended, trigger, verdict, stats FROM consults ORDER BY started DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("trigger", "verdict", "stats"):
            d[k] = json.loads(d[k]) if d[k] else None
        out.append(d)
    return out


@app.get("/api/consults/{cid}", dependencies=[Depends(auth)])
def consult(cid: str) -> dict[str, Any]:
    r = db.conn().execute("SELECT * FROM consults WHERE id=?", (cid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = dict(r)
    for k in ("trigger", "transcript", "verdict", "stats"):
        d[k] = json.loads(d[k]) if d[k] else None
    return d


@app.post("/api/consult", dependencies=[Depends(auth)])
def start_consult(req: ConsultRequest) -> dict[str, Any]:
    from . import konsiliet

    cid = konsiliet.start_async({"kind": "question", "question": req.question, "hours": req.hours})
    return {"consult_id": cid}


@app.get("/api/journal", dependencies=[Depends(auth)])
def journal() -> dict[str, Any]:
    c = db.conn()
    j = [dict(r) for r in c.execute("SELECT * FROM journal ORDER BY date DESC")]
    l = [dict(r) for r in c.execute("SELECT * FROM labs ORDER BY date DESC, analyte")]
    return {"journal": j, "labs": l}


@app.post("/api/sync/1177", dependencies=[Depends(auth)])
def sync_1177() -> dict[str, Any]:
    from . import hamtare1177

    hamtare1177.start_async()
    return {"started": True}


def _mac_minne() -> dict[str, Any]:
    """Unified memory på Mac minin, för nördpanelen."""
    import subprocess

    try:
        total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
        vm = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
        page = int(re.search(r"page size of (\d+)", vm).group(1))
        pages = {k.strip(): int(v.strip(" .")) for k, v in re.findall(r"^(.+?):\s+(\d+)\.?$", vm, re.M)}
        used = (pages.get("Pages active", 0) + pages.get("Pages wired down", 0)
                + pages.get("Pages occupied by compressor", 0)) * page
        tryck = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True).stdout
        fri = re.search(r"(\d+)%", tryck)
        return {"total_gb": round(total / 2**30, 1), "anvant_gb": round(used / 2**30, 1),
                "fritt_procent": int(fri.group(1)) if fri else None}
    except Exception as e:
        return {"fel": str(e)}


@app.get("/api/system", dependencies=[Depends(auth)])
def system() -> dict[str, Any]:
    from . import llm

    since = time.time() - 60
    epm = db.conn().execute("SELECT COUNT(*) FROM events WHERE ts > ?", (since,)).fetchone()[0]
    return {
        "modeller_laddade": [{"namn": m.get("name"), "storlek_gb": round(m.get("size", 0) / 2**30, 2),
                              "vram_gb": round(m.get("size_vram", 0) / 2**30, 2)} for m in llm.loaded_models()],
        "modeller_konfig": {"orkestrerare": settings.model_orchestrator, "specialist": settings.model_specialist},
        "tokens_sedan_start": llm.total_usage.as_dict(),
        "minne": _mac_minne(),
        "handelser_per_minut": epm,
        "matvarden": db.metrics_available(),
    }


@app.websocket("/ws")
async def ws(sock: WebSocket) -> None:
    await sock.accept()
    q = bus.subscribe()
    try:
        # Skicka historik först så att en ny klient ser vad som pågår.
        for ev in db.recent_events(300):
            await sock.send_json(ev)
        while True:
            ev = await q.get()
            await sock.send_json(ev)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
