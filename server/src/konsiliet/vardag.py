"""Vardagen: det som gör att man öppnar appen varje dag och gör något av det.

Allt här är deterministisk kod, inga språkmodeller. Siffrorna kommer ur databasen och gränserna sätts här:

  idag()        Ett svar på fem sekunder: träna, ta det lugnt eller vila, varför på en rad, och planen
                ("Lätt pass 30 min, zon 2, puls 117-136 BPM"). Bygger på Headroom, nattens sömn, sömnskulden,
                belastningen senaste dygnen, veckans pass och om vakten eller tråden har något öppet.
  plan          Ett enkelt progressivt upplägg för den som börjar träna: 3 pass i veckan, nivån höjs en
                vecka i taget när minst två pass blev av veckan innan.
  zoner()       Pulszoner från maxpuls (Tanaka: 208 - 0,7 x ålder, eller uppmätt maxpuls om den är högre).
  somn()        Sömnskuld mot behovet, läggdags inför nästa väckning, sena kvällar vid datorn.
  pass_summering()  Efter ett pass: tid, medel- och maxpuls, minuter per zon och råd för återhämtningen.
  vecka()       Kort veckosammanfattning med ärliga siffror.
  notiser       Budget per dygn, tysta timmar, snooze och fokusläge ("jag är mitt i ett pass").
                Akuta larm går aldrig genom budgeten (de skickas av vakten direkt).
  knuffar       AFK för länge (väntar på en paus i spelet), stress vid datorn, läggdags, passpåminnelse.
  kort_svar()   Ett snabbsvar ur datan inom sekunder när en tråd startar, innan teamet är klart.
  atgarder()    1-3 konkreta handlingar i slutet av varje tråd.

Klockan är en parameter (nu) överallt, så att en hel vecka kan simuleras (tools/simulera_vecka.py).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable

import numpy as np

from . import db
from .bus import bus

log = logging.getLogger("vardag")

SCHEMA = """
CREATE TABLE IF NOT EXISTS installningar (nyckel TEXT PRIMARY KEY, varde TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notis_logg (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, typ TEXT NOT NULL, skickad INTEGER NOT NULL,
    skal TEXT, titel TEXT);
CREATE INDEX IF NOT EXISTS notis_logg_ts ON notis_logg(ts);
CREATE TABLE IF NOT EXISTS snooze (typ TEXT PRIMARY KEY, till REAL NOT NULL, svar TEXT);
CREATE TABLE IF NOT EXISTS vardag_state (nyckel TEXT PRIMARY KEY, varde TEXT NOT NULL);
"""

STANDARD: dict[str, Any] = {
    "alder": 18,
    "maxpuls": None,              # sätts om man vet sin maxpuls, annars formel eller uppmätt
    "pass_per_vecka": 3,
    "passdagar": [0, 2, 5],       # mån, ons, lör (0 = måndag)
    "passtid": "17:30",
    "vakna": "07:30",             # vardagar
    "vakna_helg": "10:00",
    "somnbehov_h": 8.0,
    "tyst_fran": "23:00",
    "tyst_till": "08:00",
    "notisbudget": 6,             # knuffar per dygn, akuta larm räknas inte
    "afk_minuter": 90,
    "knuffar": {"afk": True, "stress": True, "sova": True, "pass": True},
    "plan_start": None,           # datum YYYY-MM-DD, annars första passet
}

DAGNAMN = ["mån", "tis", "ons", "tor", "fre", "lör", "sön"]
ZON_NAMN = ["", "mycket lätt", "lätt, du kan prata i hela meningar", "medel, korta meningar",
            "hårt, några ord i taget", "max"]
ZON_PROCENT = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
BRADSKA_KLART = {"ingen": "Inget som behöver vården", "bevaka": "Håll koll, ingen vård behövs nu",
                 "ta_upp_med_varden": "Ta upp med vården (inte akut)", "kontakta_vard_nu": "Kontakta vården nu"}

_schema_ok = False
_lock = threading.Lock()


def _c():
    global _schema_ok
    c = db.conn()
    if not _schema_ok:
        c.executescript(SCHEMA)
        _schema_ok = True
    return c


# ---------------------------------------------------------------- inställningar och tillstånd

def installningar() -> dict[str, Any]:
    out = json.loads(json.dumps(STANDARD))
    for r in _c().execute("SELECT nyckel, varde FROM installningar"):
        if r[0] in STANDARD:
            out[r[0]] = json.loads(r[1])
    return out


def _klocka(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    h_, m_ = int(h), int(m)
    if not (0 <= h_ < 24 and 0 <= m_ < 60):
        raise ValueError(s)
    return h_, m_


def spara_installningar(andringar: dict[str, Any]) -> dict[str, Any]:
    """Validerar och sparar. Okända nycklar och orimliga värden avvisas med ValueError."""
    ok: dict[str, Any] = {}
    for k, v in andringar.items():
        if k not in STANDARD:
            raise ValueError(f"okänd inställning {k}")
        if k in ("passtid", "vakna", "vakna_helg", "tyst_fran", "tyst_till"):
            _klocka(str(v))
            v = str(v)
        elif k == "passdagar":
            v = sorted({int(x) for x in v if 0 <= int(x) <= 6})
        elif k in ("pass_per_vecka", "notisbudget", "afk_minuter", "alder"):
            v = int(v)
            lo, hi = {"pass_per_vecka": (1, 7), "notisbudget": (0, 30), "afk_minuter": (30, 240), "alder": (10, 100)}[k]
            if not lo <= v <= hi:
                raise ValueError(f"{k} ska vara {lo}-{hi}")
        elif k == "somnbehov_h":
            v = float(v)
            if not 5 <= v <= 11:
                raise ValueError("somnbehov_h ska vara 5-11")
        elif k == "maxpuls":
            v = None if v in (None, "") else int(v)
            if v is not None and not 120 <= v <= 230:
                raise ValueError("maxpuls ska vara 120-230")
        elif k == "knuffar":
            v = {kk: bool(v.get(kk, True)) for kk in STANDARD["knuffar"]}
        elif k == "plan_start":
            v = None if not v else datetime.strptime(str(v), "%Y-%m-%d").strftime("%Y-%m-%d")
        ok[k] = v
    with db.tx() as c:
        _c()
        for k, v in ok.items():
            c.execute("INSERT OR REPLACE INTO installningar VALUES (?,?)", (k, json.dumps(v)))
    return installningar()


def _state(k: str, d: Any = None) -> Any:
    r = _c().execute("SELECT varde FROM vardag_state WHERE nyckel=?", (k,)).fetchone()
    return json.loads(r[0]) if r else d


def _satt_state(k: str, v: Any) -> None:
    with db.tx() as c:
        _c()
        c.execute("INSERT OR REPLACE INTO vardag_state VALUES (?,?)", (k, json.dumps(v)))


# ---------------------------------------------------------------- små hjälpare

def _dag(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _midnatt(ts: float) -> float:
    return datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _veckostart(ts: float) -> float:
    d = datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0)
    return (d - timedelta(days=d.weekday())).timestamp()


def _hm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def tid_text(timmar: float) -> str:
    """7.6 -> '7 h 36 min'. Alltid med enhet."""
    m = int(round(timmar * 60))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def _tal(x: float, d: int = 0) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def _testdata_ok(source: str) -> bool:
    return db.TILLAT_TESTDATA or not db.ar_testkalla(source)


def _vid_klockslag(ts: float, hhmm: str) -> float:
    h, m = _klocka(hhmm)
    return datetime.fromtimestamp(ts).replace(hour=h, minute=m, second=0, microsecond=0).timestamp()


def tysta_timmar(nu: float, inst: dict[str, Any] | None = None) -> bool:
    inst = inst or installningar()
    fran, till = _klocka(inst["tyst_fran"]), _klocka(inst["tyst_till"])
    t = datetime.fromtimestamp(nu)
    x = t.hour * 60 + t.minute
    a, b = fran[0] * 60 + fran[1], till[0] * 60 + till[1]
    return (a <= x or x < b) if a > b else (a <= x < b)


DATOR = ("kod", "spel", "chatt", "webb", "annat")


def dator_minuter(a: float, b: float) -> dict[str, int]:
    return {k: len(db.query_samples(f"dator_{k}", a, b)) for k in DATOR}


# ---------------------------------------------------------------- zoner

def maxpuls(inst: dict[str, Any] | None = None, nu: float | None = None) -> tuple[int, str]:
    inst = inst or installningar()
    if inst.get("maxpuls"):
        return int(inst["maxpuls"]), "angiven i inställningarna"
    formel = int(round(208 - 0.7 * int(inst["alder"])))
    nu = nu or time.time()
    # Uppmätt: 99:e percentilen av pulsen under pass senaste 60 dagarna (en enstaka spik räknas inte).
    hr = []
    for p in pass_lista(nu - 60 * 86400, nu):
        hr += [v for _, v in db.query_samples("hr", p["start"], p["slut"] or nu)]
    if len(hr) >= 300:
        uppmatt = int(np.percentile(hr, 99))
        if uppmatt > formel:
            return uppmatt, "uppmätt under dina pass"
    return formel, f"uppskattad: 208 - 0,7 x {inst['alder']} år"


def zoner(inst: dict[str, Any] | None = None, nu: float | None = None) -> dict[str, Any]:
    mx, kalla = maxpuls(inst, nu)
    z = []
    for i in range(1, 6):
        lo, hi = int(round(mx * ZON_PROCENT[i - 1])), int(round(mx * ZON_PROCENT[i])) - (1 if i < 5 else 0)
        z.append({"zon": i, "lo": lo, "hi": hi, "procent": f"{int(ZON_PROCENT[i - 1] * 100)}-{int(ZON_PROCENT[i] * 100)} %",
                  "betyder": ZON_NAMN[i]})
    return {"maxpuls": mx, "maxpuls_kalla": kalla, "zoner": z}


def zon_for(bpm: float, zz: dict[str, Any]) -> int:
    for z in zz["zoner"]:
        if bpm <= z["hi"]:
            return z["zon"] if bpm >= z["lo"] else 0
    return 5


# ---------------------------------------------------------------- pass

def pass_lista(a: float, b: float) -> list[dict[str, Any]]:
    rows = _c().execute("SELECT id, start, end, typ, source FROM exercise WHERE start < ? AND COALESCE(end, ?) > ? "
                        "ORDER BY start", (b, b, a)).fetchall()
    return [{"id": r[0], "start": r[1], "slut": r[2], "typ": r[3], "kalla": r[4]} for r in rows if _testdata_ok(r[4])]


def pass_summering(pid: str, nu: float | None = None) -> dict[str, Any] | None:
    nu = nu or time.time()
    r = _c().execute("SELECT id, start, end, typ, source FROM exercise WHERE id=?", (pid,)).fetchone()
    if not r:
        return None
    start, slut = r[1], r[2] or nu
    hr = db.query_samples("hr", start, slut)
    zz = zoner(nu=nu)
    minuter = [0.0] * 6
    for i, (ts, v) in enumerate(hr):
        dt = min(60.0, (hr[i + 1][0] - ts) if i + 1 < len(hr) else 1.0)
        minuter[zon_for(v, zz)] += dt / 60
    vals = [v for _, v in hr]
    hart = minuter[4] + minuter[5]
    # Målzonen för passet: den plan som gällde den dagen.
    plan = plan_for_dag(start)
    mal = plan["zon"] if plan and plan.get("zon") and plan.get("typ") != "Promenad" else (1 if r[3] == "promenad" else 2)
    i_mal = (minuter[mal] / max(1e-6, sum(minuter[1:]))) if mal and sum(minuter[1:]) else None
    if not vals:
        rad = "Ingen puls registrerades under passet, så det går inte att säga hur hårt det var."
    elif hart >= 15:
        rad = "Hårt pass. Ta en lätt dag i morgon och sov minst " + tid_text(installningar()["somnbehov_h"]) + "."
    elif hart >= 5:
        rad = "Medelhårt pass. Lätt pass eller vila i morgon beroende på Headroom."
    else:
        rad = "Lätt pass. Kroppen återhämtar sig snabbt, du kan träna igen i morgon om Headroom är över 55."
    vecka = len([p for p in pass_lista(_veckostart(start), _veckostart(start) + 7 * 86400) if _langd_min(p, nu) >= 10])
    inst = installningar()
    return {"id": r[0], "typ": r[3], "start": start, "slut": r[2], "minuter": round((slut - start) / 60),
            "puls_medel": round(float(np.mean(vals))) if vals else None,
            "puls_max": round(float(max(vals))) if vals else None,
            "zon_minuter": [round(m) for m in minuter[1:]], "under_zon1_minuter": round(minuter[0]),
            "malzon": mal, "andel_i_malzon": round(i_mal * 100) if i_mal is not None else None,
            "rad": rad, "pass_denna_vecka": vecka, "mal_per_vecka": inst["pass_per_vecka"],
            "kalla": r[4], "maxpuls": zz["maxpuls"]}


def _langd_min(p: dict[str, Any], nu: float) -> float:
    return ((p["slut"] or nu) - p["start"]) / 60


def belastning(nu: float) -> dict[str, Any]:
    """Minuter i zon 4-5 per dag de senaste tre dygnen, mätt med pulsen under passen."""
    zz = zoner(nu=nu)
    per_dag: dict[str, float] = {}
    for p in pass_lista(nu - 3 * 86400, nu):
        hr = db.query_samples("hr", p["start"], p["slut"] or nu)
        hart = 0.0
        for i, (ts, v) in enumerate(hr):
            if zon_for(v, zz) >= 4:
                hart += min(60.0, (hr[i + 1][0] - ts) if i + 1 < len(hr) else 1.0) / 60
        per_dag[_dag(p["start"])] = per_dag.get(_dag(p["start"]), 0) + hart
    igar = _dag(_midnatt(nu) - 3600)
    return {"hart_min_per_dag": {k: round(v) for k, v in per_dag.items()},
            "hart_igar_min": round(per_dag.get(igar, 0)), "tranade_igar": any(_dag(p["start"]) == igar and _langd_min(p, nu) >= 10
                                                                           for p in pass_lista(_midnatt(nu) - 86400, _midnatt(nu)))}


# ---------------------------------------------------------------- plan

NIVAER = [
    {"niva": 1, "typ": "Lätt pass", "minuter": 20, "zon": 2, "forslag": "rask promenad eller lugn jogg"},
    {"niva": 2, "typ": "Lätt pass", "minuter": 30, "zon": 2, "forslag": "jogg, cykel eller rask promenad i backe"},
    {"niva": 3, "typ": "Lätt pass", "minuter": 35, "zon": 2, "forslag": "jogg eller cykel",
     "tredje": {"typ": "Styrka", "minuter": 25, "zon": None, "forslag": "kroppsvikt: knäböj, armhävningar, plankan, 3 varv"}},
    {"niva": 4, "typ": "Lätt pass", "minuter": 40, "zon": 2, "forslag": "jogg eller cykel",
     "tredje": {"typ": "Intervaller", "minuter": 30, "zon": 4, "forslag": "10 min uppvärmning, 4 x 3 min hårt med 2 min lugnt emellan"}},
]


def _plan_start(inst: dict[str, Any], nu: float) -> float:
    if inst.get("plan_start"):
        return datetime.strptime(inst["plan_start"], "%Y-%m-%d").timestamp()
    forsta = pass_lista(0, nu)
    return forsta[0]["start"] if forsta else nu


def plan_niva(nu: float, inst: dict[str, Any] | None = None) -> dict[str, Any]:
    """Nivån höjs ett steg för varje avslutad vecka med minst två pass (av tre), högst nivå 4."""
    inst = inst or installningar()
    start = _veckostart(_plan_start(inst, nu))
    denna = _veckostart(nu)
    klara, v = 0, start
    while v < denna:
        n = len([p for p in pass_lista(v, v + 7 * 86400) if _langd_min(p, nu) >= 10])
        if n >= 2:
            klara += 1
        v += 7 * 86400
    vecka_nr = int((denna - start) // (7 * 86400)) + 1
    return {**NIVAER[min(3, klara)], "vecka_nr": vecka_nr, "veckor_med_minst_2_pass": klara}


def veckan(nu: float, inst: dict[str, Any] | None = None) -> dict[str, Any]:
    inst = inst or installningar()
    mal = inst["pass_per_vecka"]
    vs = _veckostart(nu)
    gjorda = [p for p in pass_lista(vs, vs + 7 * 86400) if _langd_min(p, nu) >= 10 and p["start"] <= nu]
    # Veckor i rad med målet nått (förra veckan och bakåt), plus den här om den redan är klar.
    streak, v = 0, vs - 7 * 86400
    while v > vs - 52 * 7 * 86400:
        if len([p for p in pass_lista(v, v + 7 * 86400) if _langd_min(p, nu) >= 10]) >= mal:
            streak += 1
            v -= 7 * 86400
        else:
            break
    if len(gjorda) >= mal:
        streak += 1
    return {"pass": len(gjorda), "mal": mal, "veckor_i_rad": streak,
            "dagar": [_dag(p["start"]) for p in gjorda], "passdagar": [DAGNAMN[d] for d in inst["passdagar"]]}


def plan_for_dag(ts: float) -> dict[str, Any] | None:
    i = idag(ts, snabb=True)
    return i.get("plan")


# ---------------------------------------------------------------- sömn

def natter(nu: float, antal: int = 7) -> list[dict[str, Any]]:
    """Sömnpass som slutat de senaste `antal` morgnarna, ett per morgon (det längsta)."""
    rows = _c().execute("SELECT id, start, end, stages, source FROM sleep WHERE end > ? AND end <= ? ORDER BY end",
                        (_midnatt(nu) - (antal - 1) * 86400, nu)).fetchall()
    per: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not _testdata_ok(r[4]):
            continue
        vaken = sum(s["end"] - s["start"] for s in json.loads(r[3]) if s.get("stage") == "awake")
        h = (r[2] - r[1] - vaken) / 3600
        d = _dag(r[2])
        if d not in per or h > per[d]["timmar"]:
            per[d] = {"id": r[0], "dag": d, "start": r[1], "slut": r[2], "timmar": round(h, 2)}
    return [per[k] for k in sorted(per)]


def nasta_vakna(nu: float, inst: dict[str, Any]) -> float:
    for d in range(0, 3):
        t = datetime.fromtimestamp(nu) + timedelta(days=d)
        klock = inst["vakna_helg"] if t.weekday() >= 5 else inst["vakna"]
        cand = _vid_klockslag(t.timestamp(), klock)
        if cand > nu + 3 * 3600 or (d > 0 and cand > nu):
            return cand
    return nu + 8 * 3600


def somn(nu: float, inst: dict[str, Any] | None = None) -> dict[str, Any]:
    inst = inst or installningar()
    behov = float(inst["somnbehov_h"])
    nn = natter(nu, 7)
    skuld = round(sum(max(0.0, behov - n["timmar"]) for n in nn), 1)
    senaste = nn[-1] if nn and nn[-1]["dag"] == _dag(nu) else None
    # Sena kvällar: datorn efter midnatt (00-05) de senaste sju nätterna.
    sena = 0
    for d in range(7):
        a = _midnatt(nu) - d * 86400
        if any(db.query_samples(f"dator_{k}", a, min(nu, a + 5 * 3600)) for k in DATOR):
            sena += 1
    vakna = nasta_vakna(nu, inst)
    # Med sömnskuld över 5 timmar flyttas läggdags 30 minuter tidigare.
    extra = 0.5 if skuld >= 5 else 0.0
    lagg = vakna - (behov + extra) * 3600 - 15 * 60
    kvall_start = _vid_klockslag(nu, "18:00") if datetime.fromtimestamp(nu).hour >= 12 else _vid_klockslag(nu, "18:00") - 86400
    dator_kvall = dator_minuter(kvall_start, nu)
    return {"behov_h": behov, "natt": senaste, "natter": nn, "skuld_h": skuld, "natter_med_data": len(nn),
            "sena_natter_vid_datorn": sena, "nasta_vakna": vakna, "laggdags": lagg,
            "laggdags_text": f"Läggdags {_hm(lagg)} för {tid_text(behov + extra)} sömn till {_hm(vakna)}",
            "dator_i_kvall_min": dator_kvall, "extra_for_skuld_h": extra}


# ---------------------------------------------------------------- idag

def _aterhamtning(nu: float) -> dict[str, Any]:
    from . import rutiner

    try:
        return rutiner.aterhamtning(datetime.fromtimestamp(nu))
    except Exception:
        log.exception("aterhamtning")
        return {"poang": None, "delar": {}}


def _oppet(nu: float) -> dict[str, Any] | None:
    """Något öppet från vakten eller tråden som gör att man ska vila: akut larm senaste dygnet, eller en
    tråd senaste tre dygnen som landade i "ta upp med vården" eller "kontakta vården nu"."""
    c = db.conn()
    for r in c.execute("SELECT ts, payload FROM events WHERE kind='alert.raise' AND ts > ? AND ts <= ? ORDER BY ts DESC",
                       (nu - 86400, nu)):
        p = json.loads(r[1])
        if p.get("level") == "akut" and p.get("rule"):
            return {"typ": "akut", "text": f"Vakten larmade akut {_hm(r[0])}: {p.get('title', '')}".rstrip(": ")}
    for r in c.execute("SELECT id, ended, verdict FROM consults WHERE ended > ? AND ended <= ? AND verdict IS NOT NULL "
                       "ORDER BY ended DESC", (nu - 3 * 86400, nu)):
        v = json.loads(r[2])
        if v.get("bradska") in ("ta_upp_med_varden", "kontakta_vard_nu"):
            return {"typ": "trad", "consult_id": r[0], "bradska": v["bradska"],
                    "text": "Tråden " + datetime.fromtimestamp(r[1]).strftime("%d/%m") + ": " + BRADSKA_KLART[v["bradska"]].lower()}
    return None


def headroom_baslinje(nu: float, dagar: int = 14) -> float | None:
    """Median av Headroom de senaste 14 dagarna (i dag oräknad). Gamla dagar sparas, de ändras inte."""
    vals = []
    for d in range(1, dagar + 1):
        t = _midnatt(nu) - d * 86400 + 12 * 3600
        key = f"headroom:{_dag(t)}"
        v = _state(key)
        if v is None:
            v = _aterhamtning(t).get("poang")
            if v is not None:
                _satt_state(key, v)
        if v is not None:
            vals.append(v)
    return float(np.median(vals)) if len(vals) >= 5 else None


def somn_baslinje(nu: float) -> float | None:
    """Personens vanliga sömnlängd: median av de senaste 14 nätterna (i natt oräknad)."""
    nn = [n["timmar"] for n in natter(_midnatt(nu) - 1, 14)]
    return float(np.median(nn)) if len(nn) >= 5 else None


def _feber(nu: float) -> float | None:
    """Hudtemperaturens avvikelse i natt (Health Connect, mot klockans egen baslinje)."""
    nn = natter(nu, 1)
    a, b = (nn[-1]["start"] - 3600, nn[-1]["slut"] + 3600) if nn else (nu - 14 * 3600, nu)
    w = [v for _, v in db.query_samples("skin_temp_delta", a, min(b, nu))]
    return float(np.median(w)) if len(w) >= 3 else None


def idag(nu: float | None = None, snabb: bool = False) -> dict[str, Any]:
    """Dagens svar. Beslut: trana, lugnt, vila eller klart. Allt deterministiskt, siffror med enheter.

    Dygnet byter vid 04, inte vid midnatt: för den som spelar till två är 00:30 fortfarande i går kväll."""
    nu = nu or time.time()
    verklig_nu = nu
    if datetime.fromtimestamp(nu).hour < 4:
        nu = _midnatt(nu) - 60
    inst = installningar()
    zz = zoner(inst, nu)
    z = {x["zon"]: x for x in zz["zoner"]}
    ah = _aterhamtning(nu)
    H = ah.get("poang")
    sm = somn(nu, inst)
    S = sm["natt"]["timmar"] if sm["natt"] else None
    bel = belastning(nu)
    vk = veckan(nu, inst)
    niva = plan_niva(nu, inst)
    oppet = None if snabb else _oppet(nu)
    feber = _feber(nu)
    idag_pass = [p for p in pass_lista(_midnatt(nu), verklig_nu) if _langd_min(p, verklig_nu) >= 10]
    hoppat = _state("pass_hoppat") == _dag(nu)
    passdag = datetime.fromtimestamp(nu).weekday() in inst["passdagar"]

    delar: list[str] = []
    if H is not None:
        delar.append(f"Headroom {H} av 100")
    if S is not None:
        delar.append(f"{tid_text(S)} sömn")
    if sm["skuld_h"] >= 3:
        delar.append(f"sömnskuld {tid_text(sm['skuld_h'])} på {sm['natter_med_data']} nätter")

    def plan_av(n: dict[str, Any], zon: int | None) -> dict[str, Any]:
        if zon:
            lo, hi = z[zon]["lo"], z[zon]["hi"]
            text = f"{n['typ']} {n['minuter']} min, zon {zon}, puls {lo}-{hi} BPM"
        else:
            lo = hi = None
            text = f"{n['typ']} {n['minuter']} min"
        return {"typ": n["typ"], "minuter": n["minuter"], "zon": zon, "puls_lo": lo, "puls_hi": hi,
                "text": text, "forslag": n["forslag"]}

    lugn = {"typ": "Promenad", "minuter": 30, "forslag": "i lugn takt, gärna utomhus i dagsljus"}
    # Kalibrerat mot personens egen vardag: Headroom jämförs med hans eget 14-dagarsmedian och sömnen med hans
    # egen vanliga sömnlängd. En vanlig dag för honom ger träning, en sämre dag ett lugnt pass och bara tydliga
    # avvikelser (eller sjukdomstecken) vila. Absoluta golv finns kvar för det som alltid är för lite.
    hb = headroom_baslinje(nu)
    sb = somn_baslinje(nu)
    dH = (H - hb) if H is not None and hb is not None else None
    dS = (S - sb) if S is not None and sb is not None else None
    hd = ah.get("delar", {})
    z_hrv = (hd.get("hrv") or {}).get("z")
    z_vp = (hd.get("vilopuls") or {}).get("z")
    if hb is not None and H is not None:
        delar[0] = f"Headroom {H} av 100 (din vanliga nivå {round(hb)})"
    beslut, skal = "trana", []
    if idag_pass:
        beslut, skal = "klart", [f"du har redan kört ett pass i dag ({round(_langd_min(idag_pass[-1], nu))} min)"]
    elif oppet:
        beslut, skal = "vila", [oppet["text"]]
    elif feber is not None and feber >= 1.0:
        beslut, skal = "vila", [f"hudtemperaturen {_tal(feber, 1)} °C över din baslinje i natt, kan vara en förkylning på väg"]
    elif z_hrv is not None and z_vp is not None and z_hrv <= -2 and z_vp >= 2:
        beslut, skal = "vila", ["låg HRV och hög vilopuls i natt jämfört med din baslinje, ett vanligt tecken på infektion eller överbelastning"]
    elif S is not None and S < 5:
        beslut, skal = "vila", [f"bara {tid_text(S)} sömn"]
    elif dH is not None and dH <= -20:
        beslut, skal = "vila", [f"Headroom {H} av 100, {round(-dH)} under din vanliga nivå"]
    elif dH is None and H is not None and H < 30:
        beslut, skal = "vila", [f"Headroom bara {H} av 100"]
    else:
        if dH is not None and dH <= -8:
            beslut = "lugnt"; skal.append(f"Headroom {H} av 100, {round(-dH)} under din vanliga nivå")
        elif dH is None and H is not None and H < 45:
            beslut = "lugnt"; skal.append(f"Headroom {H} av 100")
        if S is not None and (S < 6 or (dS is not None and dS <= -1.0)):
            beslut = "lugnt"; skal.append(f"{tid_text(S)} sömn" + (f", {tid_text(-dS)} mindre än du brukar" if dS is not None and dS < 0 else ""))
        if bel["hart_igar_min"] >= 15:
            beslut = "lugnt"; skal.append(f"hårt pass i går ({bel['hart_igar_min']} min i zon 4-5)")
        if beslut == "trana" and vk["pass"] >= vk["mal"]:
            beslut = "lugnt"; skal.append(f"veckans {vk['mal']} pass är redan klara")
        elif beslut == "trana" and bel["tranade_igar"] and niva["niva"] <= 2:
            beslut = "lugnt"; skal.append("du tränade i går, och i början behöver kroppen en dag emellan")
        elif beslut == "trana" and hoppat:
            beslut = "lugnt"; skal.append("du valde att hoppa över passet i dag")
        elif beslut == "trana" and not passdag:
            beslut = "lugnt"; skal.append(f"inte en passdag (dina passdagar: {', '.join(vk['passdagar'])})")
    if beslut == "trana" and sm["skuld_h"] >= 5:
        # Sömnskulden stoppar inte passet (lätt träning hjälper sömnen), men passet hålls lätt och kort.
        skal.append(f"sömnskuld {tid_text(sm['skuld_h'])}, så passet hålls lätt")

    if beslut == "trana":
        tredje = niva.get("tredje")
        intervaller_ok = dH is not None and dH >= 5 and sm["skuld_h"] < 5
        n = tredje if tredje and vk["pass"] == vk["mal"] - 1 and (intervaller_ok or tredje["typ"] == "Styrka") else niva
        if sm["skuld_h"] >= 5 and n.get("zon") == 2:
            n = {**n, "minuter": min(n["minuter"], 25)}
        plan = plan_av(n, n["zon"])
        rubrik = "Träna i dag"
        skal = ([f"en vanlig dag för dig ({'Headroom ' + str(H) + ', vanligt ' + str(round(hb))})"] if dH is not None
                else []) + [f"pass {vk['pass'] + 1} av {vk['mal']} den här veckan"] + skal
    elif beslut == "lugnt":
        plan = plan_av(lugn, 1) | {"text": f"Promenad 30 min, under {z[2]['lo']} BPM"}
        rubrik = "Ta det lugnt i dag"
    elif beslut == "vila":
        plan = plan_av({**lugn, "minuter": 20}, 1) | {"text": f"Vila. Högst en lugn promenad, 20 min under {z[2]['lo']} BPM"}
        rubrik = "Vila i dag"
    else:
        plan = {"typ": "Klart", "minuter": 0, "zon": None, "puls_lo": None, "puls_hi": None,
                "text": "Dagens pass är klart. Ät, drick och sov ordentligt", "forslag": ""}
        rubrik = "Klart för i dag"

    varfor = ", ".join(skal[:2])
    varfor = varfor[:1].upper() + varfor[1:] if varfor else ""
    if H is None and S is None:
        varfor = ("Ingen natt uppmätt än, så rådet bygger bara på planen. " + varfor).strip()
    matt = ", ".join(delar)
    return {
        "datum": _dag(nu), "ts": nu, "beslut": beslut, "rubrik": rubrik, "varfor": varfor, "matt": matt,
        "kort": f"{rubrik}: {plan['text']}", "plan": plan, "headroom": H, "headroom_delar": ah.get("delar", {}),
        "somn": {k: sm[k] for k in ("behov_h", "natt", "skuld_h", "natter_med_data", "sena_natter_vid_datorn",
                                    "laggdags", "laggdags_text", "nasta_vakna")},
        "veckan": vk, "niva": {k: niva[k] for k in ("niva", "vecka_nr", "veckor_med_minst_2_pass")},
        "belastning": bel, "oppet": oppet, "zoner": zz, "passdag": passdag,
        "ordlista": {
            "Headroom": "Återhämtning 0-100 ur nattens HRV, vilopuls och sömn mot din egen baslinje. Över 55: redo att träna.",
            "Zon": f"Pulszon i procent av maxpuls ({zz['maxpuls']} BPM, {zz['maxpuls_kalla']}). Zon 2 = {z[2]['lo']}-{z[2]['hi']} BPM: "
                   "du kan prata i hela meningar.",
            "Sömnskuld": f"Summan av det som saknats mot ditt sömnbehov ({tid_text(inst['somnbehov_h'])}) de senaste 7 nätterna.",
            "Stresstest": "Träningspass. Minuter med puls över 100 BPM räknas som last.",
        },
        "headroom_baslinje": round(hb) if hb is not None else None,
        "somn_baslinje_h": round(sb, 2) if sb is not None else None,
        "regler": ("Jämfört med din egen vanliga nivå (median senaste 14 dagarna). Vila: akut larm senaste dygnet, "
                   "tråd med 'ta upp med vården' senaste 3 dygnen, hudtemp +1 °C, låg HRV och hög vilopuls samma natt "
                   "(z -2/+2), Headroom 20 under din vanliga nivå, eller under 5 h sömn. Lugnt: Headroom 8 under din "
                   "vanliga nivå, en timme mindre sömn än du brukar eller under 6 h, hårt pass i går, veckans pass klara, "
                   "vilodag mellan pass i början, eller inte en passdag. Annars träning. Sömnskuld över 5 h ger ett "
                   "kortare, lätt pass."),
    }


# ---------------------------------------------------------------- notiser: budget, tysta timmar, snooze

PRIO = {"afk": 1, "stress": 1, "sova": 2, "pass": 2, "brief": 3, "vecka": 3, "pass_klart": 3}
SVAR = {
    "afk": [{"id": "snooze", "label": "Om 30 min", "minuter": 30}, {"id": "fokus", "label": "Mitt i ett pass (2 h)", "minuter": 120},
            {"id": "inte_nu", "label": "Inte i dag", "minuter": 0}],
    "stress": [{"id": "andas", "label": "Andas 60 s på klockan", "minuter": 0}, {"id": "inte_nu", "label": "Inte nu", "minuter": 180}],
    "sova": [{"id": "snooze", "label": "Om 20 min", "minuter": 20}, {"id": "inte_nu", "label": "Inte i kväll", "minuter": 0}],
    "pass": [{"id": "snooze", "label": "Om 1 h", "minuter": 60}, {"id": "inte_nu", "label": "Inte i dag", "minuter": 0}],
}

# Byts ut i simuleringen så att inget publiceras på bussen.
publicera: Callable[[str, dict[str, Any]], Any] = lambda kind, payload: bus.publish(kind, payload)


def _logg(typ: str, skickad: bool, skal: str, titel: str, nu: float) -> None:
    with db.tx() as c:
        _c()
        c.execute("INSERT INTO notis_logg(ts, typ, skickad, skal, titel) VALUES (?,?,?,?,?)",
                  (nu, typ, int(skickad), skal, titel))


def skickade_idag(nu: float) -> int:
    return _c().execute("SELECT COUNT(*) FROM notis_logg WHERE skickad=1 AND ts >= ? AND ts <= ?",
                        (_midnatt(nu), nu)).fetchone()[0]


def snoozad(typ: str, nu: float) -> bool:
    r = _c().execute("SELECT till FROM snooze WHERE typ=?", (typ,)).fetchone()
    return bool(r and r[0] > nu)


def fokus_till(nu: float) -> float | None:
    r = _c().execute("SELECT till FROM snooze WHERE typ='fokus'").fetchone()
    return r[0] if r and r[0] > nu else None


def svara(typ: str, svar: str, minuter: int | None = None, nu: float | None = None) -> dict[str, Any]:
    """Svar på en knuff: snooze (om N min), inte_nu (resten av dagen eller kvällen), fokus (inga AFK- eller
    stressknuffar på N min), klar (gjorde det)."""
    nu = nu or time.time()
    if typ not in SVAR and typ != "fokus":
        raise ValueError(f"okänd knuff {typ}")
    till = None
    if svar == "av":  # avsluta snooze eller fokusläge
        with db.tx() as c:
            _c(); c.execute("DELETE FROM snooze WHERE typ=?", (typ,))
        _logg(f"svar.{typ}", False, svar, "", nu)
        return {"typ": typ, "svar": svar, "till": None}
    if svar == "fokus" or typ == "fokus":
        till = nu + (minuter or 120) * 60
        with db.tx() as c:
            _c(); c.execute("INSERT OR REPLACE INTO snooze VALUES ('fokus', ?, 'fokus')", (till,))
    elif svar == "snooze":
        till = nu + (minuter or 30) * 60
    elif svar == "inte_nu":
        if typ == "stress":
            till = nu + (minuter or 180) * 60
        elif typ == "sova":
            till = _midnatt(nu) + (86400 if datetime.fromtimestamp(nu).hour >= 12 else 0) + 6 * 3600
        else:
            till = _midnatt(nu) + 86400
        if typ == "pass":
            _satt_state("pass_hoppat", _dag(nu))
    elif svar in ("klar", "andas"):
        till = nu + 30 * 60
    else:
        raise ValueError(f"okänt svar {svar}")
    if till and svar != "fokus" and typ != "fokus":
        with db.tx() as c:
            _c(); c.execute("INSERT OR REPLACE INTO snooze VALUES (?,?,?)", (typ, till, svar))
    if typ == "afk" and svar == "snooze" and till:
        # "Om 30 min" betyder en ny påminnelse då, inte först efter nästa hela intervall.
        _satt_state("afk_senast", till - int(installningar()["afk_minuter"]) * 60)
    _logg(f"svar.{typ}", False, svar, "", nu)
    return {"typ": typ, "svar": svar, "till": till}


def notis(typ: str, titel: str, text: str, nu: float, extra: dict[str, Any] | None = None,
          trots_tyst: bool = False) -> bool:
    """Skickar en knuff om budget, tysta timmar, snooze och fokus tillåter. Loggar alltid beslutet."""
    inst = installningar()
    prio = PRIO.get(typ, 1)
    skal = ""
    if typ in inst["knuffar"] and not inst["knuffar"][typ]:
        skal = "avstängd i inställningarna"
    elif snoozad(typ, nu):
        skal = "snoozad"
    elif typ in ("afk", "stress") and fokus_till(nu):
        skal = "fokusläge"
    elif tysta_timmar(nu, inst) and not trots_tyst:
        skal = "tysta timmar"
    else:
        n = skickade_idag(nu)
        budget = int(inst["notisbudget"])
        # Två platser hålls för det som betyder mest (läggdags, pass), AFK och stress får resten.
        if prio == 1 and n >= budget - 2:
            skal = f"budget ({n} av {budget} i dag, två platser sparas åt läggdags och pass)"
        elif prio == 2 and n >= budget:
            skal = f"budget ({n} av {budget} i dag)"
    skickad = not skal
    _logg(typ, skickad, skal or "skickad", titel, nu)
    if skickad:
        kind = {"afk": "nudge.move", "pass_klart": "pass.klart"}.get(typ, f"nudge.{typ}")
        publicera(kind, {"typ": typ, "title": titel, "body": text, "actions": SVAR.get(typ, []),
                         "budget": {"skickade_idag": skickade_idag(nu), "per_dag": inst["notisbudget"]}, **(extra or {})})
    return skickad


def notis_statistik(nu: float, dagar: int = 7) -> dict[str, Any]:
    rows = _c().execute("SELECT ts, typ, skickad, skal FROM notis_logg WHERE ts > ? AND ts <= ?",
                        (_midnatt(nu) - (dagar - 1) * 86400, nu)).fetchall()
    per: dict[str, dict[str, Any]] = {}
    for ts, typ, sk, skal in rows:
        d = per.setdefault(_dag(ts), {"skickade": 0, "stoppade": 0, "per_typ": {}, "svar": 0})
        if typ.startswith("svar."):
            d["svar"] += 1
        elif sk:
            d["skickade"] += 1
            d["per_typ"][typ] = d["per_typ"].get(typ, 0) + 1
        else:
            d["stoppade"] += 1
    inst = installningar()
    return {"per_dag": per, "budget": inst["notisbudget"], "idag": skickade_idag(nu),
            "tysta": f"{inst['tyst_fran']}-{inst['tyst_till']}", "fokus_till": fokus_till(nu)}


# ---------------------------------------------------------------- knuffarna

def _vid_datorn(a: float, b: float) -> int:
    return sum(dator_minuter(a, b).values())


def afk(nu: float) -> bool:
    inst = installningar()
    grans = int(inst["afk_minuter"])
    senast = _state("afk_senast", 0) or 0
    ignorerade = _state("afk_ignorerade", 0) or 0
    # Två ignorerade knuffar i rad: glesare, var tredje timme i stället för var 90:e minut.
    intervall = grans * 60 * (2 if ignorerade >= 2 else 1)
    if nu - senast < intervall or db.under_pass(nu - grans * 60, nu):
        return False
    # Snoozad, fokusläge eller tysta timmar: inget försök alls (och inget i loggen varje minut).
    if snoozad("afk", nu) or fokus_till(nu) or tysta_timmar(nu, inst) or not inst["knuffar"]["afk"]:
        return False
    start = nu - grans * 60
    hr = db.query_samples("hr", start, nu)
    if len(hr) < grans / 3:  # klockan bärs inte
        return False
    steg = sum(v for _, v in db.query_samples("steps", start, nu))
    if steg >= 150:
        return False
    vid = _vid_datorn(start, nu)
    # Mitt i en spelmatch: vänta på en paus (två minuter utan aktivitet), högst 30 minuter.
    spelar = len(db.query_samples("dator_spel", nu - 180, nu)) >= 2
    vantar = _state("afk_vantar_sedan")
    if spelar and _vid_datorn(nu - 120, nu) > 0:
        if not vantar:
            _satt_state("afk_vantar_sedan", nu)
            return False
        if nu - vantar < 30 * 60:
            return False
    _satt_state("afk_vantar_sedan", None)
    if senast:  # följdes förra knuffen? (minst 100 steg inom 15 minuter)
        f = sum(v for _, v in db.query_samples("steps", senast, senast + 15 * 60))
        _satt_state("afk_ignorerade", 0 if f >= 100 else ignorerade + 1)
    text = f"{int(steg)} steg på {grans} min"
    if vid > grans * 0.6:
        text += f", {vid} min vid datorn"
    text += ". Res dig och gå i fem minuter, till exempel och fyll på vattnet."
    _satt_state("afk_senast", nu)
    return notis("afk", f"AFK i {grans} min", text, nu)


def stress(nu: float) -> bool:
    """Hög puls medan man sitter still vid datorn, jämfört med samma timmes vilopuls (baslinjen)."""
    if nu - (_state("stress_senast", 0) or 0) < 3 * 3600 or snoozad("stress", nu) or fokus_till(nu):
        return False
    if _vid_datorn(nu - 600, nu) < 8 or db.under_pass(nu - 1800, nu):
        return False
    if sum(v for _, v in db.query_samples("steps", nu - 600, nu)) >= 20:
        return False
    hr = [v for _, v in db.query_samples("hr", nu - 600, nu)]
    if len(hr) < 5:
        return False
    from . import vakt

    b = vakt.baslinje("hr", datetime.fromtimestamp(nu).hour)
    if not b:
        return False
    med = float(np.median(hr))
    if med < max(85.0, b[0] + 20):
        return False
    kat = max(dator_minuter(nu - 600, nu).items(), key=lambda kv: kv[1])[0]
    vad = {"kod": "kodpasset", "spel": "spelandet", "chatt": "chatten", "webb": "surfandet"}.get(kat, "datorn")
    _satt_state("stress_senast", nu)
    return notis("stress", "Termisk strypning: hög puls vid datorn",
                 f"Klockfrekvens {med:.0f} BPM i 10 min under {vad}, fast du sitter still. Din vilopuls den här tiden "
                 f"är {b[0]:.0f} BPM. Kan vara spänning, koffein eller stress. Andas lugnt i 60 sekunder på klockan.",
                 nu, {"puls": round(med), "baslinje": round(b[0])}, trots_tyst=True)  # man sitter vid datorn: väcker ingen


def laggdags(nu: float) -> bool:
    """Påminnelse 30 minuter före läggdags, bara om man sitter vid datorn (då stör den inte sömnen)."""
    inst = installningar()
    sm = somn(nu, inst)
    lagg = sm["laggdags"]
    if not (lagg - 30 * 60 <= nu <= lagg + 90 * 60) or _state("sova_skickad") == _dag(lagg):
        return False
    if _vid_datorn(nu - 600, nu) < 5:
        return False
    k = sm["dator_i_kvall_min"]
    tot = sum(k.values())
    delar = [f"{tid_text(k[x] / 60)} {n}" for x, n in (("spel", "spel"), ("kod", "kod")) if k[x] >= 20]
    text = f"{sm['laggdags_text']}."
    if tot >= 60:
        text += f" Du har suttit vid datorn {tid_text(tot / 60)} i kväll" + (f" ({', '.join(delar)})" if delar else "") + "."
    if sm["skuld_h"] >= 3:
        text += f" Sömnskuld {tid_text(sm['skuld_h'])} senaste veckan."
    text += " Spara, sänk ljuset och lägg mobilen utom räckhåll."
    titel = "Dags att varva ned" if nu < lagg else f"Läggdags var {_hm(lagg)}"
    ok = notis("sova", titel, text, nu, {"laggdags": lagg}, trots_tyst=True)
    if ok or not snoozad("sova", nu):
        _satt_state("sova_skickad", _dag(lagg))
    return ok


def pass_paminnelse(nu: float) -> bool:
    inst = installningar()
    if _state("pass_paminnelse") == _dag(nu) or snoozad("pass", nu):
        return False
    t = _vid_klockslag(nu, inst["passtid"])
    if not (t <= nu <= t + 3 * 3600) or datetime.fromtimestamp(nu).weekday() not in inst["passdagar"]:
        return False
    i = idag(nu)
    if i["beslut"] != "trana":
        _satt_state("pass_paminnelse", _dag(nu))
        return False
    ok = notis("pass", "Passdag", f"{i['plan']['text']}. {i['plan']['forslag'].capitalize()}. Starta på klockan: "
               "Kropp64, Starta pass." + (f" {i['veckan']['pass']} av {i['veckan']['mal']} pass klara den här veckan."
                                         if i["veckan"]["pass"] else ""), nu, {"plan": i["plan"]})
    if not snoozad("pass", nu):
        _satt_state("pass_paminnelse", _dag(nu))
    return ok


def efter_pass(pid: str, nu: float | None = None) -> dict[str, Any] | None:
    nu = nu or time.time()
    s = pass_summering(pid, nu)
    # Inga notiser om gamla pass (t.ex. historik som kommer in i efterhand) eller väldigt korta.
    if not s or s["minuter"] < 3 or nu - (s["slut"] or nu) > 2 * 3600:
        return s
    # Health Connect skickar samma pass igen vid varje synk. Utan det här kom "Stresstest klart" en gång i
    # timmen för samma pass (sett i riktig data 27 nov: samma promenad notifierad två gånger).
    notifierade = _state("pass_notifierade", [])
    if pid in notifierade:
        return s
    _satt_state("pass_notifierade", (notifierade + [pid])[-50:])
    z ="".join(f", zon {i + 1}: {m} min" for i, m in enumerate(s["zon_minuter"]) if m)
    puls = f"Medelpuls {s['puls_medel']} BPM, max {s['puls_max']} BPM{z}." if s["puls_medel"] else ""
    notis("pass_klart", f"Stresstest klart: {s['minuter']} min {s['typ']}",
          f"{puls} {s['rad']} Pass {s['pass_denna_vecka']} av {s['mal_per_vecka']} den här veckan.".strip(), nu,
          {"pass": s}, trots_tyst=True)
    return s


# ---------------------------------------------------------------- morgon och vecka

def morgon(nu: float, med_llm: bool = True) -> dict[str, Any] | None:
    """POST-skärmen skrivs när natten är slut, inte på ett fast klockslag: när ett sömnpass som slutat de senaste
    tre timmarna kommer in (minst 3 h långt, slut efter 04), eller senast 90 minuter efter väckningstiden."""
    if _state("brief_dag") == _dag(nu):
        return None
    inst = installningar()
    h = datetime.fromtimestamp(nu).hour
    if not 4 <= h < 14:  # en morgonrapport kl. 23 hjälper ingen (t.ex. första installationen en kväll)
        return None
    nn = natter(nu, 1)
    vaken = bool(nn) and nn[-1]["dag"] == _dag(nu) and nu - nn[-1]["slut"] < 3 * 3600 and nn[-1]["timmar"] >= 3
    vakna = _vid_klockslag(nu, inst["vakna_helg"] if datetime.fromtimestamp(nu).weekday() >= 5 else inst["vakna"])
    if not (vaken or nu >= vakna + 90 * 60):
        return None
    _satt_state("brief_dag", _dag(nu))
    from . import rutiner

    brief = rutiner.morgonbrief(nu=nu, med_llm=med_llm, publicera_fn=publicera)
    _logg("brief", True, "skickad", brief.get("rubrik", ""), nu)
    return brief


def vecka(nu: float | None = None) -> dict[str, Any]:
    nu = nu or time.time()
    inst = installningar()
    vk = veckan(nu, inst)
    vs = _veckostart(nu)
    sm = somn(nu, inst)
    nn = [n for n in sm["natter"] if n["slut"] >= vs]
    snitt = round(float(np.mean([n["timmar"] for n in nn])), 2) if nn else None
    pass_ = [pass_summering(p["id"], nu) for p in pass_lista(vs, nu)]
    pass_ = [p for p in pass_ if p and p["minuter"] >= 10]
    zon_min = [sum(p["zon_minuter"][i] for p in pass_) for i in range(5)]
    notiser = notis_statistik(nu, 7)
    afk_ = _c().execute("SELECT ts FROM notis_logg WHERE typ='afk' AND skickad=1 AND ts > ? AND ts <= ?", (vs, nu)).fetchall()
    foljda = sum(1 for (ts,) in afk_ if sum(v for _, v in db.query_samples("steps", ts, ts + 900)) >= 100)
    hr_mitt = []
    for d in range(7):
        try:
            p = _aterhamtning(vs + d * 86400 + 12 * 3600).get("poang") if vs + d * 86400 + 12 * 3600 <= nu else None
        except Exception:
            p = None
        if p is not None:
            hr_mitt.append(p)
    rader = [f"{vk['pass']} av {vk['mal']} pass" + (f", {sum(zon_min)} min puls i zon 1-5" if pass_ else "") + "."]
    if snitt is not None:
        rader.append(f"Sömn {tid_text(snitt)} i snitt på {len(nn)} nätter, behov {tid_text(sm['behov_h'])}.")
    if sm["sena_natter_vid_datorn"]:
        rader.append(f"Vid datorn efter midnatt {sm['sena_natter_vid_datorn']} av 7 nätter.")
    if hr_mitt:
        rader.append(f"Headroom {round(float(np.mean(hr_mitt)))} i snitt ({min(hr_mitt)}-{max(hr_mitt)}).")
    if afk_:
        rader.append(f"{foljda} av {len(afk_)} AFK-knuffar följdes av en promenad.")
    if vk["pass"] >= vk["mal"]:
        nasta = f"Målet nått, {vk['veckor_i_rad']} veckor i rad. Nästa vecka: samma upplägg, planen går upp en nivå."
    elif vk["pass"] >= 2:
        nasta = "Två pass räcker för att planen ska gå vidare. Nästa vecka: sikta på tre."
    else:
        nasta = f"Nästa vecka: börja med två pass. Lägg dem på {', '.join(vk['passdagar'][:2])}."
    if snitt is not None and snitt < sm["behov_h"] - 0.75:
        nasta += f" Och läggdags {_hm(sm['laggdags'])}, sömnen är det som ger mest headroom."
    return {"vecka_start": _dag(vs), "pass": vk, "zon_minuter": zon_min, "somn_snitt_h": snitt,
            "somnskuld_h": sm["skuld_h"], "sena_natter": sm["sena_natter_vid_datorn"], "headroom": hr_mitt,
            "afk_knuffar": len(afk_), "afk_foljda": foljda, "notiser": notiser, "rader": rader, "nasta": nasta,
            "text": " ".join(rader) + " " + nasta}


def vecka_rutin(nu: float) -> bool:
    if datetime.fromtimestamp(nu).weekday() != 6 or datetime.fromtimestamp(nu).hour < 19 or _state("vecka_dag") == _dag(nu):
        return False
    _satt_state("vecka_dag", _dag(nu))
    v = vecka(nu)
    publicera("vecka.summering", v)
    _logg("vecka", True, "skickad", "Veckan", nu)
    return True


def tick(nu: float | None = None, med_llm: bool = True) -> None:
    """Körs varje minut av rutinerna."""
    nu = nu or time.time()
    with _lock:
        for f in (lambda: morgon(nu, med_llm), lambda: pass_paminnelse(nu), lambda: laggdags(nu),
                  lambda: stress(nu), lambda: afk(nu), lambda: vecka_rutin(nu)):
            try:
                f()
            except Exception:
                log.exception("vardag")


# ---------------------------------------------------------------- tråden: snabbsvar och åtgärder

def _eta(nu: float) -> int:
    rows = db.conn().execute("SELECT ended - started FROM consults WHERE ended IS NOT NULL ORDER BY started DESC LIMIT 10").fetchall()
    tider = [r[0] for r in rows if r[0] and r[0] > 0]
    eta = float(np.median(tider)) if tider else 120.0
    try:
        from . import konsiliet

        eta *= 1 + konsiliet._q.qsize()
    except Exception:
        pass
    return int(round(eta))


def kort_svar(cid: str, trigger: dict[str, Any], nu: float | None = None) -> dict[str, Any]:
    """Det datan säger direkt, utan språkmodell, medan teamet arbetar. Samma regelverk som tråden använder."""
    from . import fakta

    nu = nu or time.time()
    t0 = time.perf_counter()
    f = fakta.faktaark(trigger, nu)
    niva, skal = fakta.regelbradska(trigger, f)
    i = idag(nu)
    rader: list[str] = []
    if trigger.get("kind") == "anomaly":
        rader.append(f"Vakten såg: {trigger.get('title', '')}. {trigger.get('detail', '')}".strip())
        L = f.get("F:larm") or {}
        steg = L.get("steg_10_min_fore_och_under")
        if steg is not None:
            rader.append(f"{int(steg)} steg runt larmet" + (", inget pass" if L.get("traningspass_under_eller_strax_fore") in (None, "inget")
                                                            else ", under ett pass") + ".")
    sm = i["somn"]
    if sm["natt"]:
        rader.append(f"Sömn i natt {tid_text(sm['natt']['timmar'])}, behov {tid_text(sm['behov_h'])}.")
    if sm["skuld_h"] >= 1:
        rader.append(f"Sömnskuld {tid_text(sm['skuld_h'])} på {sm['natter_med_data']} nätter.")
    if sm["sena_natter_vid_datorn"]:
        rader.append(f"Vid datorn efter midnatt {sm['sena_natter_vid_datorn']} av 7 nätter.")
    if i["headroom"] is not None:
        rader.append(f"Headroom {i['headroom']} av 100.")
    if i["belastning"]["hart_igar_min"]:
        rader.append(f"{i['belastning']['hart_igar_min']} min i zon 4-5 i går.")
    regel = BRADSKA_KLART[niva]
    skal_klart = [s.split(": ", 1)[-1] for s in skal if not s.startswith("ingen")][:2]
    eta = _eta(nu)
    out = {"consult_id": cid, "bradska_regel": niva, "bradska_text": regel, "skal": skal_klart, "rader": rader[:6],
           "eta_s": eta, "idag": i["kort"],
           "text": f"Snabbsvar ur datan: {regel}" + (f" ({'; '.join(skal_klart)})" if skal_klart else "") + ". "
                   + " ".join(rader[:4]) + f" Teamet svarar om cirka {max(1, round(eta / 60))} min.",
           "sekunder": round(time.perf_counter() - t0, 2)}
    publicera("consult.kort", out)
    return out


def starta_trad(trigger: dict[str, Any]) -> str:
    """Startar en tråd och skickar snabbsvaret direkt i en egen tråd (påverkar inte teamets kö)."""
    from . import konsiliet

    cid = konsiliet.start_async(trigger)

    def _kort() -> None:
        try:
            kort_svar(cid, trigger)
        except Exception:
            log.exception("kort svar")

    threading.Thread(target=_kort, name="kort-svar", daemon=True).start()
    return cid


def atgarder(trigger: dict[str, Any], verdict: dict[str, Any], nu: float | None = None) -> list[str]:
    """1-3 konkreta handlingar. Brådskan styr den första (alltid saklig), sedan teamets granskade råd,
    sedan dagens plan. Inga nya siffror utöver dagens plan, som räknas i koden."""
    nu = nu or time.time()
    ut: list[str] = []
    b = verdict.get("bradska")
    if b == "kontakta_vard_nu":
        ut.append("Ring 1177 nu. Vid bröstsmärta, andnöd eller svimning: ring 112.")
    elif b == "ta_upp_med_varden":
        ut.append("Boka en tid på vårdcentralen och ta med besöksunderlaget (PDF under Inställningar).")
    regel_skal = " ".join(verdict.get("bradska_regel_skal") or [])
    if "mätfel" in regel_skal:
        ut.append("Dra åt armbandet ett hål och låt klockan mäta igen i 10 minuter.")
    for r in verdict.get("rad") or []:
        if isinstance(r, str) and r.strip() and len(ut) < 3 and r.strip() not in ut:
            ut.append(r.strip().rstrip(".") + ".")
    if len(ut) < 3 and b != "kontakta_vard_nu":
        try:
            i = idag(nu)
            ut.append(f"{i['rubrik']}: {i['plan']['text']}.")
        except Exception:
            pass
    return ut[:3]


def _krok_verdict(m: Any, verdict: dict[str, Any]) -> None:
    verdict["atgarder"] = atgarder(m.trigger, verdict)


def registrera_krokar() -> None:
    from . import konsiliet

    if _krok_verdict not in konsiliet.KROKAR_VERDICT:
        konsiliet.KROKAR_VERDICT.append(_krok_verdict)
