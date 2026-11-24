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
import ipaddress
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .bus import bus
from .config import settings

app = FastAPI(title="Konsiliet", version="0.1.0")

WEB_DIR = Path(__file__).resolve().parents[3] / "web" / "dist"


TAILNET = ipaddress.ip_network("100.64.0.0/10")  # Tailscale: bara mina egna enheter
COOKIE = "konsiliet_token"


def _betrodd(host: str, headers: Any, token: str | None) -> bool:
    via_tunnel = "cf-connecting-ip" in headers  # Cloudflare Tunnel ansluter från localhost men sätter headern
    if not via_tunnel:
        if host in ("127.0.0.1", "::1"):
            return True
        try:
            if ipaddress.ip_address(host) in TAILNET:
                return True
        except ValueError:
            pass
    if token and token in settings.device_tokens:
        return True
    return bool(headers.get("cf-access-authenticated-user-email"))


def auth(request: Request, x_device_token: str | None = Header(default=None)) -> None:
    host = request.client.host if request.client else ""
    token = x_device_token or request.cookies.get(COOKIE)
    if not _betrodd(host, request.headers, token):
        raise HTTPException(status_code=401, detail="Ej behörig")


@app.middleware("http")
async def _token_cookie(request: Request, call_next: Any) -> Any:
    """WebView i mobilappen: /?token=... sätter en httpOnly-cookie så att webbappens egna anrop går igenom."""
    resp = await call_next(request)
    tok = request.query_params.get("token")
    if tok and tok in settings.device_tokens:
        resp.set_cookie(COOKIE, tok, httponly=True, secure=request.url.scheme == "https",
                        samesite="lax", max_age=365 * 86400)
    return resp


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
    from . import datorn, rutiner, vakt

    vakt.start()
    rutiner.start()
    if os.environ.get("KONSILIET_DATORN", "1") == "1":
        datorn.start()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "ts": time.time()}


@app.post("/api/ingest", dependencies=[Depends(auth)])
def ingest(batch: IngestBatch) -> dict[str, Any]:
    from . import matning

    t0 = time.perf_counter()
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
    matning.record("Mottagning (ingest)", (time.perf_counter() - t0) * 1000)
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
def series(metric: str, hours: float = 24, step: float = 0) -> dict[str, Any]:
    """Utan step: [ts, värde]. Med step (sekunder): en punkt per hink, [ts, min, max, median]."""
    start = time.time() - hours * 3600
    pts = db.query_samples(metric, start)
    if step > 0:
        return {"metric": metric, "step": step, "points": db.downsample(pts, step)}
    return {"metric": metric, "points": pts}


@app.get("/api/ref/{ref:path}", dependencies=[Depends(auth)])
def ref(ref: str) -> dict[str, Any]:
    """Slår upp en källreferens (S:, B:, N:, J:, L:) till något läsbart."""
    from . import verktyg

    return verktyg.las_ref(ref)


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


@app.get("/api/aterhamtning", dependencies=[Depends(auth)])
def aterhamtning() -> dict[str, Any]:
    from . import rutiner

    return rutiner.aterhamtning()


@app.post("/api/brief", dependencies=[Depends(auth)])
def brief() -> dict[str, Any]:
    from . import rutiner

    return rutiner.morgonbrief()


@app.get("/api/datorn", dependencies=[Depends(auth)])
def datortid(hours: float = 24) -> dict[str, Any]:
    """Minuter vid datorn per kategori, och puls under respektive kategori."""
    start = time.time() - hours * 3600
    hr = dict(db.query_samples("hr", start))
    hr_min: dict[int, list[float]] = {}
    for ts, v in hr.items():
        hr_min.setdefault(int(ts // 60), []).append(v)
    out = {}
    for kat in ("kod", "spel", "chatt", "webb", "annat"):
        minuter = [int(ts // 60) for ts, _ in db.query_samples(f"dator_{kat}", start)]
        pulser = [v for m in minuter for v in hr_min.get(m, [])]
        out[kat] = {"minuter": len(minuter),
                    "puls_median": round(sorted(pulser)[len(pulser) // 2], 1) if pulser else None}
    return {"timmar": hours, "kategorier": out}


@app.get("/api/besoksunderlag.pdf", dependencies=[Depends(auth)])
def besoksunderlag() -> Response:
    from . import underlag

    return Response(underlag.pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="besoksunderlag.pdf"'})


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
    from . import llm, matning

    since = time.time() - 60
    epm = db.conn().execute("SELECT COUNT(*) FROM events WHERE ts > ?", (since,)).fetchone()[0]
    return {
        "modeller_laddade": [{"namn": m.get("name"), "storlek_gb": round(m.get("size", 0) / 2**30, 2),
                              "vram_gb": round(m.get("size_vram", 0) / 2**30, 2)} for m in llm.loaded_models()],
        "modeller_konfig": {"orkestrerare": settings.model_orchestrator, "specialist": settings.model_specialist},
        "tokens_sedan_start": llm.total_usage.as_dict(),
        "minne": _mac_minne(),
        "handelser_per_minut": epm,
        "pipeline": matning.sammanstall(),
        "matvarden": db.metrics_available(),
    }


@app.websocket("/ws")
async def ws(sock: WebSocket) -> None:
    host = sock.client.host if sock.client else ""
    token = sock.query_params.get("token") or sock.headers.get("x-device-token") or sock.cookies.get(COOKIE)
    if not _betrodd(host, sock.headers, token):
        await sock.close(code=4401)
        return
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
