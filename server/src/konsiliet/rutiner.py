"""Återkommande rutiner: återhämtningspoäng (Headroom), POST-skärmen och veckans tråd. Knuffarna ligger i vardag.py.

Återhämtningspoängen är en öppen formel, inte en svart låda (alla siffror visas i appen):

    poäng = 50 + 12 * z_hrv - 10 * z_vilopuls + 8 * (sömntimmar - 7.5)   (klämd till 0-100)
    z begränsas till ±3 och spridningen har ett golv (HRV 5 ms, puls 2 slag/min).

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

_senast: dict[str, float] = {}


# Minsta spridning som räknas som en standardavvikelse. Utan golv ger en mycket jämn baslinje
# enorma z-värden för små skillnader (en natt med 4 slag lägre vilopuls blev z = -6,7).
GOLV = {"hrv_rmssd": 5.0, "hr": 2.0}
Z_MAX = 3.0


def _robust(vals: list[float], metric: str = "") -> tuple[float, float] | None:
    if len(vals) < 20 and not (metric == "hr" and len(vals) >= 7):
        return None
    a = np.array(vals)
    med = float(np.median(a))
    return med, max(float(np.median(np.abs(a - med))) * MAD_TO_SD, GOLV.get(metric, 1e-6))


def _z(v: float, b: tuple[float, float]) -> float:
    return float(max(-Z_MAX, min(Z_MAX, (v - b[0]) / b[1])))


def _sovfonster(natt_slut: datetime) -> tuple[float, float]:
    """Nattens fönster: sömnpasset som slutade den morgonen (00-18), annars 00-06.

    En fast period 00-06 passar dåligt för den som spelar till två och sover till tio: då räknades
    vaken tid vid datorn som natt, vilket gav för hög vilopuls och för låg HRV (och för låg Headroom)."""
    start = natt_slut.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.conn().execute("SELECT start, end, source FROM sleep WHERE end > ? AND end <= ? ORDER BY end - start DESC",
                             (start.timestamp(), (start + timedelta(hours=18)).timestamp())).fetchall()
    rows = [r for r in rows if db.TILLAT_TESTDATA or not db.ar_testkalla(r[2])]
    if rows and rows[0][1] - rows[0][0] >= 3 * 3600:
        return rows[0][0], rows[0][1]
    return start.timestamp(), (start + timedelta(hours=6)).timestamp()


def _natt(metric: str, natt_slut: datetime) -> list[float]:
    """Värden under natten som slutar natt_slut (sömnpasset om det finns, annars 00-06)."""
    a, b = _sovfonster(natt_slut)
    return [v for _, v in db.query_samples(metric, a, b)]


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
    b = _robust(hist_hrv, "hrv_rmssd")
    if hrv_n and b:
        z = _z(float(np.median(hrv_n)), b)
        delar["hrv"] = {"natt_ms": round(float(np.median(hrv_n)), 1), "baslinje_ms": round(b[0], 1), "z": round(z, 2)}
        poang += 12 * z
    b = _robust(hist_hr, "hr") if len(hist_hr) >= 7 else None
    if len(hr_n) >= 10 and b:
        vila = float(min(np.convolve(hr_n, np.ones(10) / 10, mode="valid")))
        z = _z(vila, b)
        delar["vilopuls"] = {"natt": round(vila, 1), "baslinje": round(b[0], 1), "z": round(z, 2)}
        poang -= 10 * z
    row = db.conn().execute("SELECT start, end, stages FROM sleep WHERE end > ? AND end <= ? ORDER BY end DESC LIMIT 1",
                            ((dag - timedelta(hours=18)).timestamp(), dag.timestamp() + 60)).fetchone()
    if row:
        vaken = sum(s["end"] - s["start"] for s in json.loads(row["stages"]) if s["stage"] == "awake")
        h = (row["end"] - row["start"] - vaken) / 3600
        delar["somn"] = {"timmar": round(h, 2)}
        poang += 8 * (h - 7.5)
    if not delar:
        return {"poang": None, "delar": {}, "kommentar": "för lite data"}
    return {"poang": int(max(0, min(100, round(poang)))), "delar": delar,
            "formel": "50 + 12*z_hrv - 10*z_vilopuls + 8*(sömntimmar-7.5), z begränsat till ±3"}


def _inom_granser(text: str, plan: dict[str, Any]) -> str | None:
    """Gränser som koden sätter för idrottsläkarens text: inga fler minuter än planen och ingen puls
    utanför planens zon. Returnerar skälet om texten går utanför."""
    import re

    for m in re.finditer(r"(\d+)\s*(?:-\s*(\d+)\s*)?min", text):
        if int(m.group(2) or m.group(1)) > max(plan.get("minuter") or 0, 30):
            return f"fler minuter ({m.group(0)}) än planen ({plan.get('minuter')} min)"
    lo, hi = plan.get("puls_lo"), plan.get("puls_hi")
    for m in re.finditer(r"(\d{2,3})\s*(?:-\s*(\d{2,3})\s*)?(?:BPM|slag)", text, re.I):
        for v in (int(m.group(1)), int(m.group(2) or m.group(1))):
            if lo is not None and hi is not None and not lo - 1 <= v <= hi + 1:
                return f"puls {v} utanför planens zon ({lo}-{hi} BPM)"
    return None


def morgonbrief(nu: float | None = None, med_llm: bool = True, publicera_fn: Any = None) -> dict[str, Any]:
    """POST-skärmen. Beslutet och planen räknas i koden (vardag.idag) och står först, så att svaret syns
    direkt. Idrottsläkaren skriver sedan 2-3 meningar om varför, inom de gränser koden satt. Texten granskas
    som i tråden; går den utanför används kodens egen text."""
    from . import vardag

    nu = nu or time.time()
    dag = datetime.fromtimestamp(nu)
    ah = aterhamtning(dag)
    i = vardag.idag(nu)
    igar = nu - 86400
    steg = sum(v for _, v in db.query_samples("steps", igar, nu))
    dator = {k: len(db.query_samples(f"dator_{k}", igar, nu)) for k in ("kod", "spel", "chatt", "webb")}
    fakta = {"aterhamtning": ah, "steg_senaste_dygnet": int(steg), "minuter_vid_datorn": dator,
             "beslut": i["rubrik"], "plan": i["plan"], "varfor": i["varfor"],
             "somn_timmar": (i["somn"]["natt"] or {}).get("timmar"), "somnskuld_timmar": i["somn"]["skuld_h"],
             "pass_denna_vecka": i["veckan"]["pass"], "mal_pass_per_vecka": i["veckan"]["mal"]}
    reserv = f"{i['varfor']}." if i["varfor"] else ""
    text, skal = reserv, "språkmodellen användes inte"
    if med_llm:
        from .konsiliet import kontrollera

        msgs = [
            {"role": "system", "content": "Du är idrottsläkare i ett läkarteam. Personen: "
             f"{settings.profil}. Beslutet för dagen är redan fattat av regelverket: '{i['kort']}'. Skriv 2-3 korta "
             "meningar på svenska som förklarar varför, utifrån datan, och ett tips för att passet eller vilan ska bli av. "
             "Ändra inte beslutet. Använd bara siffror som står i datan, exakt som de står. Nämn inga andra minuter eller "
             "pulsvärden än planens. Inga utropstecken."},
            {"role": "user", "content": json.dumps(fakta, ensure_ascii=False)}]
        refs = {"F:morgon": {"ref": "F:morgon", **fakta}}
        for _ in range(2):  # siffrorna granskas som i tråden; ett nytt försök om något inte stämmer
            text = llm.chat(settings.model_orchestrator, msgs).content.strip()
            skal = next((s for s in (kontrollera(m, ["F:morgon"], refs) for m in text.split(". ") if m) if s), None) \
                or _inom_granser(text, i["plan"])
            if not skal:
                break
            msgs += [{"role": "assistant", "content": text},
                     {"role": "user", "content": f"Granskaren: {skal}. Skriv om med bara siffror ur datan."}]
        if skal:
            text = reserv
    p = ah.get("poang")
    post = "POST: OK" if i["beslut"] in ("trana", "klart") else (f"POST: varning, headroom {p}" if p is not None else "POST: varning")
    brief = {"datum": dag.strftime("%Y-%m-%d"), "rubrik": f"{post}. {i['rubrik']}", "kort": i["kort"], "beslut": i["beslut"],
             "varfor": i["varfor"], "plan": i["plan"], "text": text, "fakta": fakta, "granskad": not skal,
             "skrivet_av": "idrottsläkaren" if not skal else "regelverket"}
    (publicera_fn or bus.publish)("brief.morgon", brief)
    return brief


def _loop() -> None:
    from . import vardag

    vardag.registrera_krokar()
    while True:
        try:
            nu = datetime.now()
            # AFK, stress, läggdags, passpåminnelse, POST-skärmen (när natten är slut) och veckan.
            vardag.tick(nu.timestamp())
            dag = nu.strftime("%Y-%m-%d")
            if nu.weekday() == 6 and nu.hour == 19 and _senast.get("vecka") != dag:
                _senast["vecka"] = dag
                # Teamets genomgång kommer efter den korta veckosammanfattningen och ger ingen egen notis
                # om den inte hittar något som ska tas upp med vården ("tyst").
                vardag.starta_trad({"kind": "question", "hours": 168, "tyst": True, "question":
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
