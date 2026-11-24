"""Verktygen som läkaragenterna kan använda. Varje resultat bär referens-ID:n (ref).

Granskaren godkänner bara påståenden vars källor är ref:ar som faktiskt returnerats under mötet.
Ref-format:
  S:<metric>:<start>-<end>   tidsserieutsnitt (unix-sekunder)
  B:<metric>:h<timme>        personlig baslinje
  N:<id>                     sömnpass
  J:<id>                     journalanteckning
  L:<id>                     provsvar
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Callable

import numpy as np

from . import db
from .config import settings

METRIC_NAMES = {
    "hr": "puls (slag/min)", "hrv_rmssd": "HRV RMSSD (ms)", "spo2": "syremättnad (%)",
    "steps": "steg", "resp_rate": "andningsfrekvens (andetag/min)", "skin_temp": "hudtemperatur (°C)",
    "resting_hr": "vilopuls (slag/min)", "calories": "energi (kcal)",
    "dator_kod": "minuter vid datorn och kodade (1 per minut)", "dator_spel": "minuter vid datorn och spelade",
    "dator_chatt": "minuter i chattappar på datorn", "dator_webb": "minuter i webbläsaren på datorn",
}


def _fmt_t(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def hamta_serie(metric: str, timmar_bakat: float = 24, slut_timmar_bakat: float = 0) -> dict[str, Any]:
    end = time.time() - slut_timmar_bakat * 3600
    start = end - timmar_bakat * 3600
    pts = db.query_samples(metric, start, end)
    ref = f"S:{metric}:{int(start)}-{int(end)}"
    if not pts:
        return {"ref": ref, "metric": metric, "antal": 0, "kommentar": "ingen data i perioden"}
    a = np.array(pts)
    v = a[:, 1]
    # Nedsampla till högst 48 punkter så att modellen ser formen utan att kontexten svämmar över.
    bins = np.array_split(a, min(16, len(a)))
    kurva = [[_fmt_t(float(b[0, 0])), round(float(np.median(b[:, 1])), 1)] for b in bins if len(b)]
    imax, imin = int(np.argmax(v)), int(np.argmin(v))
    return {
        "ref": ref, "metric": metric, "enhet": METRIC_NAMES.get(metric, metric),
        "period": [_fmt_t(start), _fmt_t(end)], "antal": int(len(v)),
        "median": round(float(np.median(v)), 1), "min": [round(float(v[imin]), 1), _fmt_t(float(a[imin, 0]))],
        "max": [round(float(v[imax]), 1), _fmt_t(float(a[imax, 0]))],
        "kurva_median": kurva,
    }


def jamfor_baslinje(metric: str, timme: int | None = None, dagar: int = 28) -> dict[str, Any]:
    timme = datetime.now().hour if timme is None else int(timme)
    now = time.time()
    rows = db.conn().execute(
        "SELECT ts, value FROM samples WHERE metric=? AND ts BETWEEN ? AND ?",
        (metric, now - dagar * 86400, now),
    ).fetchall()
    vals = np.array([v for ts, v in rows if datetime.fromtimestamp(ts).hour == timme])
    ref = f"B:{metric}:h{timme}"
    if len(vals) < 30:
        return {"ref": ref, "kommentar": f"för lite historik ({len(vals)} punkter) för baslinje"}
    med = float(np.median(vals))
    return {"ref": ref, "metric": metric, "timme": timme, "dagar": dagar, "antal": int(len(vals)),
            "median": round(med, 1), "p10": round(float(np.percentile(vals, 10)), 1),
            "p90": round(float(np.percentile(vals, 90)), 1)}


def hamta_somn(natter: int = 7) -> dict[str, Any]:
    rows = db.conn().execute(
        "SELECT * FROM sleep WHERE end > ? ORDER BY start DESC", (time.time() - natter * 86400,)
    ).fetchall()
    out = []
    for r in rows:
        stages = json.loads(r["stages"])
        dur: dict[str, float] = {}
        for s in stages:
            dur[s["stage"]] = dur.get(s["stage"], 0) + (s["end"] - s["start"]) / 60
        out.append({"ref": f"N:{r['id']}", "start": _fmt_t(r["start"]), "slut": _fmt_t(r["end"]),
                    "total_min": round((r["end"] - r["start"]) / 60),
                    "faser_min": {k: round(v) for k, v in dur.items()}})
    return {"natter": out, "antal": len(out)}


def sok_journal(sokord: str = "", max_antal: int = 8) -> dict[str, Any]:
    q = "SELECT id, date, unit, author, kind, title, substr(text,1,700) text FROM journal"
    args: list[Any] = []
    if sokord:
        q += " WHERE text LIKE ? OR title LIKE ? OR kind LIKE ?"
        args = [f"%{sokord}%"] * 3
    q += " ORDER BY date DESC LIMIT ?"
    args.append(max_antal)
    rows = [dict(r) for r in db.conn().execute(q, args)]
    return {"traffar": [{"ref": f"J:{r.pop('id')}", **r} for r in rows], "antal": len(rows)}


def hamta_labb(analyt: str = "", max_antal: int = 20) -> dict[str, Any]:
    q = "SELECT id, date, analyte, value_raw, unit, ref_low, ref_high, flag FROM labs"
    args: list[Any] = []
    if analyt:
        q += " WHERE analyte LIKE ?"
        args.append(f"%{analyt}%")
    q += " ORDER BY date DESC LIMIT ?"
    args.append(max_antal)
    rows = [dict(r) for r in db.conn().execute(q, args)]
    return {"svar": [{"ref": f"L:{r.pop('id')}", **r} for r in rows], "antal": len(rows)}


def fraga_medgemma(fraga: str) -> dict[str, Any]:
    """Medicinsk bakgrundskunskap från den medicinska modellen. Ger ingen ref: kunskap, inte data."""
    from . import llm

    r = llm.chat(settings.model_specialist, [
        {"role": "system", "content": "Du är en medicinsk kunskapskälla. Svara kort och sakligt på svenska, "
         "max 120 ord. Säg tydligt när evidensen är osäker. Ställ inga diagnoser på enskilda personer."},
        {"role": "user", "content": fraga},
    ], temperature=0.2, num_ctx=4096)
    return {"svar": r.content.strip(), "kalla": "MedGemma (bakgrundskunskap, ej persondata)"}


TOOLS: dict[str, tuple[Callable[..., dict[str, Any]], dict[str, Any]]] = {
    "hamta_serie": (hamta_serie, {
        "description": "Hämta en tidsserie från klockan som sammanfattning (median, min, max, percentiler, nedsamplad kurva).",
        "parameters": {"type": "object", "properties": {
            "metric": {"type": "string", "enum": list(METRIC_NAMES)},
            "timmar_bakat": {"type": "number", "description": "periodens längd i timmar"},
            "slut_timmar_bakat": {"type": "number", "description": "hur många timmar sedan perioden slutar, 0 = nu"}},
            "required": ["metric"]}}),
    "jamfor_baslinje": (jamfor_baslinje, {
        "description": "Personens normala nivå för ett mätvärde vid en viss timme på dygnet, senaste veckorna.",
        "parameters": {"type": "object", "properties": {
            "metric": {"type": "string", "enum": list(METRIC_NAMES)},
            "timme": {"type": "integer", "description": "0-23, utelämna för nuvarande timme"}},
            "required": ["metric"]}}),
    "hamta_somn": (hamta_somn, {
        "description": "Sömnpass med faser (djup, lätt, REM, vaken) för de senaste nätterna.",
        "parameters": {"type": "object", "properties": {"natter": {"type": "integer"}}}}),
    "sok_journal": (sok_journal, {
        "description": "Sök i journalanteckningar från 1177.",
        "parameters": {"type": "object", "properties": {"sokord": {"type": "string"}}}}),
    "hamta_labb": (hamta_labb, {
        "description": "Hämta provsvar från 1177, valfritt filtrerat på analys.",
        "parameters": {"type": "object", "properties": {"analyt": {"type": "string"}}}}),
    "fraga_medgemma": (fraga_medgemma, {
        "description": "Fråga den medicinska modellen om allmän medicinsk kunskap (inte om personens data).",
        "parameters": {"type": "object", "properties": {"fraga": {"type": "string"}}, "required": ["fraga"]}}),
}


def schemas(names: list[str]) -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": n, **TOOLS[n][1]}} for n in names]


def run(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        return {"fel": f"okänt verktyg {name}"}
    fn = TOOLS[name][0]
    try:
        return fn(**{k: v for k, v in args.items() if not k.startswith("_")})
    except TypeError as e:
        return {"fel": f"fel argument: {e}"}
    except Exception as e:  # ett trasigt verktyg ska ge agenten ett felsvar, inte krascha mötet
        return {"fel": f"verktyget misslyckades: {type(e).__name__}: {e}"}
