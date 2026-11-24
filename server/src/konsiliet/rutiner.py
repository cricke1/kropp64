"""Återkommande rutiner: stillasittandevakt, morgonbrief med återhämtningspoäng, veckorapport.

Återhämtningspoängen är en öppen formel, inte en svart låda (alla siffror visas i appen):

    poäng = 50 + 12 * z_hrv - 10 * z_vilopuls + 8 * (sömntimmar - 7.5)   (klämd till 0-100)

  z_hrv        nattens median-HRV mot 28 dagars nattbaslinje, i robusta standardavvikelser
  z_vilopuls   nattens lägsta 10-minutersmedian mot baslinjen, i robusta standardavvikelser
  sömntimmar   senaste sömnpassets längd minus vakna perioder
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from . import db, llm
from .bus import bus
from .config import settings

log = logging.getLogger("rutiner")
MAD_TO_SD = 1.4826

STILLA_MINUTER = 90
STILLA_STEG = 150
_senast: dict[str, float] = {}


def _robust(vals: list[float]) -> tuple[float, float] | None:
    if len(vals) < 20:
        return None
    a = np.array(vals)
    med = float(np.median(a))
    return med, max(float(np.median(np.abs(a - med))) * MAD_TO_SD, 1e-6)


def _natt(metric: str, natt_slut: datetime) -> list[float]:
    """Värden mellan 00 och 06 natten som slutar natt_slut."""
    start = natt_slut.replace(hour=0, minute=0, second=0, microsecond=0)
    return [v for _, v in db.query_samples(metric, start.timestamp(), (start + timedelta(hours=6)).timestamp())]


def aterhamtning(dag: datetime | None = None) -> dict[str, Any]:
    dag = dag or datetime.now()
    hrv_n, hr_n = _natt("hrv_rmssd", dag), _natt("hr", dag)
    hist_hrv, hist_hr = [], []
    for d in range(1, 29):
        hist_hrv += _natt("hrv_rmssd", dag - timedelta(days=d))
        hr_d = _natt("hr", dag - timedelta(days=d))
        if len(hr_d) >= 10:
            hist_hr.append(float(min(np.convolve(hr_d, np.ones(10) / 10, mode="valid"))))
    delar: dict[str, Any] = {}
    poang = 50.0
    b = _robust(hist_hrv)
    if hrv_n and b:
        z = (float(np.median(hrv_n)) - b[0]) / b[1]
        delar["hrv"] = {"natt_ms": round(float(np.median(hrv_n)), 1), "baslinje_ms": round(b[0], 1), "z": round(z, 2)}
        poang += 12 * z
    b = _robust(hist_hr) if len(hist_hr) >= 7 else None
    if len(hr_n) >= 10 and b:
        vila = float(min(np.convolve(hr_n, np.ones(10) / 10, mode="valid")))
        z = (vila - b[0]) / b[1]
        delar["vilopuls"] = {"natt": round(vila, 1), "baslinje": round(b[0], 1), "z": round(z, 2)}
        poang -= 10 * z
    row = db.conn().execute("SELECT start, end, stages FROM sleep WHERE end > ? ORDER BY end DESC LIMIT 1",
                            ((dag - timedelta(hours=18)).timestamp(),)).fetchone()
    if row:
        vaken = sum(s["end"] - s["start"] for s in json.loads(row["stages"]) if s["stage"] == "awake")
        h = (row["end"] - row["start"] - vaken) / 3600
        delar["somn"] = {"timmar": round(h, 2)}
        poang += 8 * (h - 7.5)
    if not delar:
        return {"poang": None, "delar": {}, "kommentar": "för lite data"}
    return {"poang": int(max(0, min(100, round(poang)))), "delar": delar,
            "formel": "50 + 12*z_hrv - 10*z_vilopuls + 8*(sömntimmar-7.5)"}


def stillasittande() -> None:
    nu = datetime.now()
    if not 8 <= nu.hour < 23 or time.time() - _senast.get("stilla", 0) < STILLA_MINUTER * 60:
        return
    start = time.time() - STILLA_MINUTER * 60
    hr = db.query_samples("hr", start)
    if len(hr) < STILLA_MINUTER / 3:  # klockan bärs inte
        return
    steg = sum(v for _, v in db.query_samples("steps", start))
    if steg >= STILLA_STEG:
        return
    vid_datorn = sum(len(db.query_samples(f"dator_{k}", start)) for k in ("kod", "spel", "chatt", "webb", "annat"))
    _senast["stilla"] = time.time()
    text = f"{int(steg)} steg senaste {STILLA_MINUTER} minuterna"
    if vid_datorn > STILLA_MINUTER * 0.6:
        text += f", varav {vid_datorn} minuter vid datorn"
    bus.publish("nudge.move", {"title": "Dags att resa på dig", "body": text + ". Fem minuter räcker."})


def morgonbrief() -> dict[str, Any]:
    ah = aterhamtning()
    igar = time.time() - 86400
    steg = sum(v for _, v in db.query_samples("steps", igar))
    dator = {k: len(db.query_samples(f"dator_{k}", igar)) for k in ("kod", "spel", "chatt", "webb")}
    fakta = {"aterhamtning": ah, "steg_senaste_dygnet": int(steg), "minuter_vid_datorn": dator}
    r = llm.chat(settings.model_orchestrator, [
        {"role": "system", "content": "Du är idrottsläkare i ett läkarteam. Skriv en morgonbrief på svenska till en "
         "18-åring som sitter mycket vid datorn och vill börja träna. Max 4 meningar. Använd bara siffrorna i "
         "datan, hitta inte på några. Avsluta med ett konkret träningsförslag för dagen anpassat efter "
         "återhämtningen (vila, lätt promenad, intervaller eller styrka)."},
        {"role": "user", "content": json.dumps(fakta, ensure_ascii=False)}])
    brief = {"datum": datetime.now().strftime("%Y-%m-%d"), "text": r.content.strip(), "fakta": fakta}
    bus.publish("brief.morgon", brief)
    return brief


def _loop() -> None:
    while True:
        try:
            stillasittande()
            nu = datetime.now()
            dag = nu.strftime("%Y-%m-%d")
            if nu.hour == 7 and nu.minute >= 30 and _senast.get("brief") != dag:
                _senast["brief"] = dag
                morgonbrief()
            if nu.weekday() == 6 and nu.hour == 19 and _senast.get("vecka") != dag:
                _senast["vecka"] = dag
                from . import konsiliet

                konsiliet.start_async({"kind": "question", "hours": 168, "question":
                                       "Veckogenomgång: hur har sömn, stress, aktivitet och återhämtning sett ut "
                                       "den här veckan jämfört med tidigare, och vad är viktigast att ändra?"})
        except Exception:
            log.exception("rutin")
        time.sleep(60)


_started = False


def start() -> None:
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_loop, name="rutiner", daemon=True).start()
