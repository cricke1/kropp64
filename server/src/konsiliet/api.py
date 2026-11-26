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
GET  /api/rost/{event_id}   en agent.say-replik uppläst (Ogg Opus), aldrig fri text
GET  /api/idag              dagens svar: träna, ta det lugnt eller vila, varför och planen (vardag.py)
GET  /api/somn              sömnskuld, läggdags och sena kvällar
GET  /api/pass              träningspass med tid i zoner och råd efteråt
GET  /api/vecka             veckosammanfattningen
GET  /api/notiser           knuffar per dag, budget, tysta timmar, fokusläge
POST /api/knuff/svar        svar på en knuff: snooze, inte_nu, fokus, klar
GET/POST /api/installningar plan, passdagar, väckning, tysta timmar, notisbudget
POST /api/sync/1177         starta journalhämtning (kräver BankID i mobilen)
WS   /ws                    live-ström av alla händelser (se bus.py för typer)

Autentisering: Cloudflare Access framför allt som nås utifrån. Mobilappen skickar dessutom
X-Device-Token som jämförs med KONSILIET_DEVICE_TOKENS. Anrop från localhost släpps igenom.
"""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import math
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


def _token_ok(token: str | None) -> bool:
    """Jämförelse i konstant tid, så att token inte kan gissas tecken för tecken via svarstider."""
    if not token:
        return False
    return any(hmac.compare_digest(token.encode(), t.encode()) for t in settings.device_tokens)


def _betrodd(host: str, headers: Any, token: str | None) -> bool:
    """Säkerhetsmodell:
    - Servern lyssnar bara på 127.0.0.1 och Mac minins Tailscale-adress (se drift/), aldrig på LAN.
    - Anrop direkt från localhost eller Tailscale-nätet (bara mina egna enheter) är betrodda.
    - Allt som kommer via en tunnel (Cf-Connecting-Ip satt) kräver giltig enhetstoken. Inga headers
      från klienten litas på i sig: en påhittad Cf-Access-header ger ingenting (hål hittat i granskning).
    """
    via_tunnel = "cf-connecting-ip" in headers
    if not via_tunnel:
        if host in ("127.0.0.1", "::1"):
            return True
        try:
            if ipaddress.ip_address(host) in TAILNET:
                return True
        except ValueError:
            pass
    return _token_ok(token)


TILLATNA_HOSTAR = {"127.0.0.1", "localhost", "[::1]"} | {
    h.strip() for h in os.environ.get("KONSILIET_HOSTAR", "").split(",") if h.strip()}


def _host_ok(host_header: str | None) -> bool:
    """Skydd mot DNS rebinding: Host-headern måste vara en adress vi faktiskt svarar på."""
    if not host_header:
        return False
    h = host_header.rsplit(":", 1)[0] if not host_header.startswith("[") else host_header.split("]")[0] + "]"
    if h in TILLATNA_HOSTAR:
        return True
    try:
        return ipaddress.ip_address(h) in TAILNET
    except ValueError:
        return False


def auth(request: Request, x_device_token: str | None = Header(default=None)) -> None:
    host = request.client.host if request.client else ""
    token = x_device_token or request.cookies.get(COOKIE)
    if not _host_ok(request.headers.get("host")) or not _betrodd(host, request.headers, token):
        raise HTTPException(status_code=401, detail="Ej behörig")


@app.middleware("http")
async def _bara_egna_natet(request: Request, call_next: Any) -> Any:
    """Servern lyssnar på alla gränssnitt för att Tailscale ska nå den, men svarar bara localhost,
    Tailscale-nätet och tunneln (med token). Allt från LAN eller annat får 403, även webbsidan."""
    host = request.client.host if request.client else ""
    lokal = host in ("127.0.0.1", "::1")
    try:
        tailnet = ipaddress.ip_address(host) in TAILNET
    except ValueError:
        tailnet = False
    if not (lokal or tailnet):
        return Response("Ej tillgänglig", status_code=403)
    if not _host_ok(request.headers.get("host")):
        return Response("Fel värd", status_code=421)
    return await call_next(request)


@app.middleware("http")
async def _token_cookie(request: Request, call_next: Any) -> Any:
    """WebView i mobilappen: /?token=... sätter en httpOnly-cookie så att webbappens egna anrop går igenom."""
    resp = await call_next(request)
    tok = request.query_params.get("token")
    if tok and _token_ok(tok):
        resp.set_cookie(COOKIE, tok, httponly=True, secure=request.url.scheme == "https",
                        samesite="strict", max_age=365 * 86400)
    return resp


METRIC_NAMN = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
# Rimliga gränser per mätvärde. Värden utanför är mätfel eller fusk och tas inte emot.
GRANSER = {"hr": (20, 250), "hr_resting": (20, 150), "resting_hr": (20, 150), "hrv_rmssd": (1, 400),
           "spo2": (50, 100), "resp_rate": (2, 80), "skin_temp": (20, 45), "skin_temp_delta": (-10, 10),
           "steps": (0, 50000)}
# Appen skickar några namn som servern internt kallar annat.
ALIAS = {"hr_resting": "resting_hr"}


class Sample(BaseModel):
    ts: float = Field(description="unix-sekunder UTC")
    metric: str
    value: float


class IngestBatch(BaseModel):
    source: str = Field(default="watch", max_length=40, pattern=r"^[a-z0-9_.-]+$")
    samples: list[Sample] = Field(max_length=20000)


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
    nu = time.time()
    rows, avvisade = [], 0
    for smp in batch.samples:
        metric = ALIAS.get(smp.metric, smp.metric)
        lo, hi = GRANSER.get(metric, (-1e9, 1e9))
        ok = (METRIC_NAMN.match(metric) and math.isfinite(smp.value) and math.isfinite(smp.ts)
              and nu - 400 * 86400 < smp.ts < nu + 300 and lo <= smp.value <= hi)
        if ok:
            rows.append((smp.ts, metric, smp.value, batch.source))
        else:
            avvisade += 1
    n = db.insert_samples(rows)
    # Senaste värdet per mätvärde går ut live, utan att sparas som händelse.
    latest: dict[str, Sample] = {}
    for s in batch.samples:
        if s.metric not in latest or s.ts > latest[s.metric].ts:
            latest[s.metric] = s
    for s in latest.values():
        bus.publish("sample.live", s.model_dump(), persist=False)
    from . import vakt

    # Vakten får veta vilken period som fått ny data, så att sent inkommande data (Health Connect,
    # offlinekö) också utvärderas på mätpunkternas egen tid.
    if rows:
        vakt.notify_new_data([r[1] for r in rows], min(r[0] for r in rows), max(r[0] for r in rows))
    matning.record("Mottagning (ingest)", (time.perf_counter() - t0) * 1000)
    return {"stored": n, "avvisade": avvisade}


@app.post("/api/ingest/sleep", dependencies=[Depends(auth)])
def ingest_sleep(sess: SleepSession) -> dict[str, Any]:
    with db.tx() as c:
        c.execute(
            "INSERT OR REPLACE INTO sleep(id, start, end, stages, source) VALUES (?,?,?,?,?)",
            (sess.id, sess.start, sess.end, json.dumps([s.model_dump() for s in sess.stages]), sess.source),
        )
    if time.time() - sess.end < 3 * 3600:
        # Natten är slut: POST-skärmen kan skrivas nu i stället för på ett fast klockslag.
        _i_bakgrunden(lambda: __import__("konsiliet.vardag", fromlist=["morgon"]).morgon(time.time()))
    return {"stored": 1}


def _i_bakgrunden(f: Any) -> None:
    import threading

    def kor() -> None:
        try:
            f()
        except Exception:
            import logging
            logging.getLogger("api").exception("bakgrundsjobb")

    threading.Thread(target=kor, daemon=True).start()


class Exercise(BaseModel):
    id: str
    start: float
    end: float | None = None
    typ: str
    source: str = "watch"


@app.post("/api/ingest/exercise", dependencies=[Depends(auth)])
def ingest_exercise(ex: Exercise) -> dict[str, Any]:
    """Träningspass. Skicka vid start (end=null) och igen vid slut. Vakten bortser från hög puls under pass."""
    with db.tx() as c:
        c.execute("INSERT OR REPLACE INTO exercise(id, start, end, typ, source) VALUES (?,?,?,?,?)",
                  (ex.id, ex.start, ex.end, ex.typ, ex.source))
    if ex.end is not None:
        from . import vardag

        # Sammanfattningen efter passet (zoner, råd) går ut som notis.
        _i_bakgrunden(lambda: vardag.efter_pass(ex.id))
    return {"stored": 1}


@app.get("/api/metrics", dependencies=[Depends(auth)])
def metrics() -> list[dict[str, Any]]:
    return db.metrics_available()


@app.get("/api/kallor", dependencies=[Depends(auth)])
def kallor() -> list[dict[str, Any]]:
    """Vilka källor datan kommer från, så att webben kan märka syntetisk testdata tydligt."""
    rows = db.conn().execute("SELECT source, COUNT(*) n, MIN(ts) first, MAX(ts) last FROM samples GROUP BY source").fetchall()
    return [{**dict(r), "test": db.ar_testkalla(r["source"])} for r in rows]


@app.get("/api/series/{metric}", dependencies=[Depends(auth)])
def series(metric: str, hours: float = 24, step: float = 0) -> dict[str, Any]:
    """Utan step: [ts, värde]. Med step (sekunder): en punkt per hink, [ts, min, max, median]."""
    hours = min(max(hours, 0.1), 24 * 90)
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
    for k in ("trigger", "transcript", "verdict", "stats", "evidence"):
        d[k] = json.loads(d[k]) if d[k] else None
    return d


@app.post("/api/consult", dependencies=[Depends(auth)])
def start_consult(req: ConsultRequest) -> dict[str, Any]:
    from . import vardag

    # Snabbsvaret ur datan (consult.kort) kommer inom sekunder, teamets svar efter några minuter.
    cid = vardag.starta_trad({"kind": "question", "question": req.question, "hours": req.hours})
    return {"consult_id": cid}


@app.get("/api/journal", dependencies=[Depends(auth)])
def journal() -> dict[str, Any]:
    c = db.conn()
    j = [dict(r) for r in c.execute("SELECT * FROM journal ORDER BY date DESC")]
    l = [dict(r) for r in c.execute("SELECT * FROM labs ORDER BY date DESC, analyte")]
    return {"journal": j, "labs": l}


@app.get("/api/1177/status", dependencies=[Depends(auth)])
def status_1177() -> dict[str, Any]:
    from . import hamtare1177

    return hamtare1177.status()


@app.post("/api/sync/1177", dependencies=[Depends(auth)])
def sync_1177() -> dict[str, Any]:
    from . import hamtare1177

    startad = hamtare1177.start_async()
    return {"started": startad, "pagar": not startad}


@app.get("/api/aterhamtning", dependencies=[Depends(auth)])
def aterhamtning() -> dict[str, Any]:
    from . import rutiner

    return rutiner.aterhamtning()


@app.post("/api/brief", dependencies=[Depends(auth)])
def brief() -> dict[str, Any]:
    from . import rutiner

    return rutiner.morgonbrief()


@app.get("/api/idag", dependencies=[Depends(auth)])
def idag() -> dict[str, Any]:
    from . import vardag

    return vardag.idag()


@app.get("/api/somn", dependencies=[Depends(auth)])
def somn_status() -> dict[str, Any]:
    from . import vardag

    return vardag.somn(time.time())


@app.get("/api/pass", dependencies=[Depends(auth)])
def pass_lista(dagar: int = 14) -> list[dict[str, Any]]:
    from . import vardag

    nu = time.time()
    return [s for p in vardag.pass_lista(nu - min(dagar, 90) * 86400, nu) if (s := vardag.pass_summering(p["id"], nu))]


@app.get("/api/vecka", dependencies=[Depends(auth)])
def vecka() -> dict[str, Any]:
    from . import vardag

    return vardag.vecka()


@app.get("/api/notiser", dependencies=[Depends(auth)])
def notiser(dagar: int = 7) -> dict[str, Any]:
    from . import vardag

    return vardag.notis_statistik(time.time(), min(dagar, 60))


class KnuffSvar(BaseModel):
    typ: str = Field(max_length=20)
    svar: str = Field(max_length=20)
    minuter: int | None = Field(default=None, ge=0, le=24 * 60)


@app.post("/api/knuff/svar", dependencies=[Depends(auth)])
def knuff_svar(s: KnuffSvar) -> dict[str, Any]:
    from . import vardag

    try:
        return vardag.svara(s.typ, s.svar, s.minuter)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/installningar", dependencies=[Depends(auth)])
def installningar() -> dict[str, Any]:
    from . import vardag

    return vardag.installningar()


@app.post("/api/installningar", dependencies=[Depends(auth)])
def spara_installningar(andringar: dict[str, Any]) -> dict[str, Any]:
    from . import vardag

    try:
        return vardag.spara_installningar(andringar)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))


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
    # Mobilens skärmtid, samma modell (mobil_<kategori>, en punkt per minut), från mobilappen.
    mobil = {}
    for kat in ("spel", "sociala", "video", "chatt", "webb", "annat"):
        minuter = [int(ts // 60) for ts, _ in db.query_samples(f"mobil_{kat}", start)]
        pulser = [v for m in minuter for v in hr_min.get(m, [])]
        mobil[kat] = {"minuter": len(minuter),
                      "puls_median": round(sorted(pulser)[len(pulser) // 2], 1) if pulser else None}
    return {"timmar": hours, "kategorier": out, "mobil": mobil}


@app.get("/api/besoksunderlag.pdf", dependencies=[Depends(auth)])
def besoksunderlag() -> Response:
    from . import underlag

    return Response(underlag.pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="besoksunderlag.pdf"'})


@app.get("/api/rost/{event_id}", dependencies=[Depends(auth)])
def rost_ljud(event_id: int, request: Request) -> Response:
    """En replik ur händelseloggen uppläst med läkarens röst (Ogg Opus). Tar aldrig emot text: bara
    agent.say-händelser som redan finns kan läsas upp, så att ingen kan få en klonad röst att säga något annat."""
    from . import rost

    if not rost.hastighet_ok(request.client.host if request.client else ""):
        raise HTTPException(429, "För många anrop")
    rep = rost.replik(event_id)
    if rep is None:
        raise HTTPException(404)
    rost.forvarm(event_id)
    try:
        fil = rost.ljud(*rep)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    if fil is None:
        return Response(status_code=204)
    return FileResponse(fil, media_type="audio/ogg", headers={"Cache-Control": "private, max-age=300"})


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
    origin = sock.headers.get("origin")
    # Origin-kontroll mot Cross-Site WebSocket Hijacking: bara samma värd (eller appens WebView utan Origin).
    origin_ok = origin is None or origin.split("://", 1)[-1] == sock.headers.get("host", "")
    if not origin_ok or not _host_ok(sock.headers.get("host")) or not _betrodd(host, sock.headers, token):
        await sock.close(code=4401)
        return
    await sock.accept()
    q = bus.subscribe()
    try:
        # Skicka historik först så att en ny klient ser vad som pågår.
        for ev in db.recent_events(300):
            # Märkt så att ingen klient agerar på gamla händelser (t.ex. startar sms för ett gammalt larm).
            await sock.send_json({**ev, "replay": True})
        while True:
            ev = await q.get()
            await sock.send_json(ev)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
