"""Vakten. Körs hela tiden och letar avvikelser mot min egen baslinje.

Två nivåer:
  1. Akut (regelbaserat, millisekunder): t.ex. puls 140+ i vila, SpO2 under 88 %, klockans fall-larm.
     Larmar mobilen direkt, utan att vänta på någon språkmodell. Det är BARA dessa regler som
     kan leda till sms till anhöriga.
  2. Avvikelse (statistiskt): robust z-poäng mot min egen baslinje för samma timme på dygnet,
     plus trender över flera nätter (HRV). Kallar in konsiliet.

Reglerna utvärderas på mätpunkternas egen tid, inte på "nu". Data som kommer sent (Health Connect
synkar ofta timmar efteråt, och mobilen kan ha legat offline) utvärderas för den period den gäller.
Ett larm om något som hände för länge sedan märks som "i efterhand" och blir aldrig akut.

Baslinjen: median och MAD (median absolute deviation, robust mot enstaka träningspass) per mätvärde
och timme på dygnet, senaste 28 dagarna. För puls används bara vilominuter (inga steg, inget pass)
så att vilopuls jämförs med vilopuls. Baslinjen räknas om var sjätte timme och sparas i databasen.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np

from . import db, matning
from .bus import bus

log = logging.getLogger("vakt")

BASELINE_DAYS = 28
BASELINE_TTL = 6 * 3600
TICK_SECONDS = 60
MAD_TO_SD = 1.4826
MIN_SD = {"hr": 2.0, "resting_hr": 2.0, "hrv_rmssd": 5.0, "resp_rate": 0.7, "skin_temp": 0.2}
EFTERHAND_S = 30 * 60   # äldre än så: larmet gäller något som redan har hänt
COOLDOWN = {"akut": 15 * 60, "avvikelse": 6 * 3600}

SCHEMA = """
CREATE TABLE IF NOT EXISTS baslinje (
    metric TEXT NOT NULL, timme INTEGER NOT NULL, median REAL NOT NULL, sd REAL NOT NULL,
    n INTEGER NOT NULL, uppdaterad REAL NOT NULL, PRIMARY KEY (metric, timme));
CREATE TABLE IF NOT EXISTS vakt_state (rule TEXT PRIMARY KEY, senast REAL NOT NULL);
"""


@dataclass
class Finding:
    rule: str
    level: str          # "akut" eller "avvikelse"
    metric: str
    title: str
    detail: str
    z: float | None = None
    window: tuple[float, float] | None = None


# ---------------------------------------------------------------- hjälpfunktioner

def _schema() -> None:
    db.conn().executescript(SCHEMA)


def _window(metric: str, minutes: float, slut: float) -> np.ndarray:
    pts = db.query_samples(metric, slut - minutes * 60, slut)
    return np.array(pts, dtype=float).reshape(-1, 2)


def _resting(minutes: float, slut: float) -> bool:
    """Sant om nästan inga steg tagits under perioden och inget träningspass pågick."""
    start = slut - minutes * 60
    if db.under_pass(start, slut):
        return False
    steps = _window("steps", minutes, slut)
    return steps.size == 0 or float(steps[:, 1].sum()) < 20


def _vilominuter(start: float, slut: float) -> set[int]:
    """Minuter utan steg (±2 min) och utan pass."""
    steg = db.query_samples("steps", start, slut)
    rorelse = {int(ts // 60) + d for ts, v in steg if v >= 5 for d in range(-2, 3)}
    pass_ = db.conn().execute("SELECT start, COALESCE(end, ?) FROM exercise WHERE start < ? AND COALESCE(end, ?) > ?",
                              (time.time(), slut, time.time(), start)).fetchall()
    for a, b in pass_:
        rorelse |= set(range(int(a // 60) - 5, int(b // 60) + 15))  # och en stund efter passet
    alla = {int(ts // 60) for ts, _ in db.query_samples("hr", start, slut)}
    return alla - rorelse


def _rakna_baslinje(metric: str) -> None:
    nu = time.time()
    start, slut = nu - BASELINE_DAYS * 86400, nu - 2 * 3600  # utesluter det pågående fönstret
    pts = db.query_samples(metric, start, slut)
    if metric == "hr":
        vila = _vilominuter(start, slut)
        pts = [(ts, v) for ts, v in pts if int(ts // 60) in vila]
    per_timme: dict[int, list[float]] = {}
    for ts, v in pts:
        per_timme.setdefault(datetime.fromtimestamp(ts).hour, []).append(v)
    with db.tx() as c:
        c.execute("DELETE FROM baslinje WHERE metric=?", (metric,))
        for h, vals in per_timme.items():
            # Minst 3 dagars data för timmen, räknat i antal punkter med marginal för glesa källor.
            if len(vals) < 30:
                continue
            a = np.array(vals)
            med = float(np.median(a))
            sd = max(float(np.median(np.abs(a - med))) * MAD_TO_SD, MIN_SD.get(metric, 1e-3))
            c.execute("INSERT INTO baslinje VALUES (?,?,?,?,?,?)", (metric, h, med, sd, len(vals), nu))


def baslinje(metric: str, timme: int) -> tuple[float, float, int] | None:
    _schema()
    r = db.conn().execute("SELECT median, sd, n, uppdaterad FROM baslinje WHERE metric=? AND timme=?",
                          (metric, timme)).fetchone()
    senast = db.conn().execute("SELECT MAX(uppdaterad) FROM baslinje WHERE metric=?", (metric,)).fetchone()[0]
    if senast is None or time.time() - senast > BASELINE_TTL:
        _rakna_baslinje(metric)
        r = db.conn().execute("SELECT median, sd, n, uppdaterad FROM baslinje WHERE metric=? AND timme=?",
                              (metric, timme)).fetchone()
    return (r[0], r[1], r[2]) if r else None


def natter(antal: int, slut: float) -> list[tuple[float, float]]:
    """De senaste nätterna som (start, slut). Sömnpassen används när de finns, annars 00-06 lokal tid."""
    rows = db.conn().execute("SELECT start, end FROM sleep WHERE end <= ? AND source NOT LIKE '%emulator%' "
                             "ORDER BY end DESC LIMIT ?", (slut + 3600, antal)).fetchall()
    if len(rows) >= antal:
        return [(r[0], r[1]) for r in rows]
    out = []
    midnatt = datetime.fromtimestamp(slut).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    # Före 06 pågår natten fortfarande: senaste avslutade natt är gårdagens.
    dag_ts = midnatt - 86400 if datetime.fromtimestamp(slut).hour < 6 else midnatt
    for i in range(antal):
        s = dag_ts - i * 86400
        out.append((s, s + 6 * 3600))
    return out


# ---------------------------------------------------------------- regler (alla tar periodens sluttid)

def rule_fall(slut: float) -> Finding | None:
    """Klockans egen falldetektering."""
    pts = db.query_samples("fall_detected", slut - 5 * 60, slut)
    if any(v >= 1 for _, v in pts):
        return Finding("fall", "akut", "fall_detected", "Klockan registrerade ett fall",
                       "Pixel Watch falldetektering slog till.", window=(pts[0][0], pts[-1][0]))
    return None


def rule_hr_rest_acute(slut: float) -> Finding | None:
    hr = _window("hr", 10, slut)
    if len(hr) < 5 or not _resting(10, slut):
        return None
    med = float(np.median(hr[:, 1]))
    if med >= 140:
        return Finding("hr_rest_acute", "akut", "hr", "Mycket hög puls i vila",
                       f"Medianpuls {med:.0f} slag/min under 10 minuter utan rörelse.",
                       window=(hr[0, 0], hr[-1, 0]))
    return None


def rule_hr_sudden_jump(slut: float) -> Finding | None:
    """Plötsligt hopp i puls utan rörelse, till exempel en hjärtrusning. Kräver att höjningen
    håller i sig (minst 6 punkter) så att en enstaka felmätning inte larmar."""
    hr = _window("hr", 5, slut)
    if len(hr) < 6 or not _resting(5, slut):
        return None
    first, last = float(np.median(hr[:3, 1])), float(np.median(hr[-3:, 1]))
    if last - first >= 35 and last >= 110:
        return Finding("hr_sudden_jump", "akut", "hr", "Plötsligt pulshopp i vila",
                       f"Pulsen steg från {first:.0f} till {last:.0f} slag/min på några minuter utan rörelse.",
                       window=(hr[0, 0], hr[-1, 0]))
    return None


def rule_spo2_low(slut: float) -> Finding | None:
    sp = _window("spo2", 10, slut)
    if len(sp) < 3:
        return None
    med = float(np.median(sp[:, 1]))
    if med < 88:
        return Finding("spo2_low", "akut", "spo2", "Låg syremättnad",
                       f"SpO2 median {med:.0f} % under 10 minuter.", window=(sp[0, 0], sp[-1, 0]))
    return None


def rule_spo2_dips(slut: float) -> Finding | None:
    """Upprepade fall på minst 4 procentenheter under en timme (som ODI i sömnapnéutredningar)."""
    sp = _window("spo2", 60, slut)
    if len(sp) < 30:
        return None
    vals = sp[:, 1]
    ref = float(np.percentile(vals, 90))
    dips, in_dip = 0, False
    for v in vals:
        if not in_dip and v <= ref - 4:
            dips, in_dip = dips + 1, True
        elif in_dip and v >= ref - 1:
            in_dip = False
    if dips >= 5:
        return Finding("spo2_dips", "avvikelse", "spo2", "Upprepade syrefall",
                       f"{dips} fall på minst 4 procentenheter under en timme (referens {ref:.0f} %).",
                       window=(sp[0, 0], sp[-1, 0]))
    return None


def rule_metric_vs_baseline(metric: str, minutes: int, z_limit: float, label: str) -> Callable[[float], Finding | None]:
    def rule(slut: float) -> Finding | None:
        w = _window(metric, minutes, slut)
        if len(w) < 5:
            return None
        if metric == "hr" and not _resting(minutes, slut):
            return None
        # Vid datorn är man vaken. Baslinjen för en timme då man brukar sova säger då inget (spel kl. 02
        # jämfördes med sovpuls). Hög puls vid datorn hanteras av stressknuffen, och akutreglerna gäller alltid.
        # Även en halvtimme efter datorn: pulsen efter en spelmatch är inte vilopuls.
        if metric == "hr" and sum(len(db.query_samples(f"dator_{k}", slut - minutes * 60 - 1800, slut))
                                  for k in ("kod", "spel", "chatt", "webb", "annat")) >= 3:
            return None
        base = baslinje(metric, datetime.fromtimestamp(slut).hour)
        if base is None:
            return None
        med, sd, _ = base
        cur = float(np.median(w[:, 1]))
        z = (cur - med) / sd
        # Lägre vilopuls än vanligt är nästan alltid sömn eller vila (t.ex. en sovmorgon en timme då man
        # brukar sitta vid datorn), inget att starta en tråd om. Bara under 40 BPM räknas det.
        if metric == "hr" and z < 0 and cur >= 40:
            return None
        if abs(z) >= z_limit:
            riktning = "över" if z > 0 else "under"
            return Finding(f"baseline_{metric}", "avvikelse", metric, f"{label} avviker från din baslinje",
                           f"{label} {cur:.1f} mot normalt {med:.1f} vid den här tiden på dygnet "
                           f"({abs(z):.1f} SD {riktning}).", z=round(z, 2), window=(w[0, 0], w[-1, 0]))
        return None
    rule.__name__ = f"baseline_{metric}"
    return rule


def rule_skin_temp_delta(slut: float) -> Finding | None:
    """Hudtemperaturens avvikelse mot klockans egen baslinje (Health Connect), över natten."""
    w = _window("skin_temp_delta", 8 * 60, slut)
    if len(w) < 3:
        return None
    med = float(np.median(w[:, 1]))
    if med >= 1.0:
        return Finding("skin_temp_delta", "avvikelse", "skin_temp_delta", "Förhöjd hudtemperatur",
                       f"Hudtemperaturen {med:+.1f} °C mot din baslinje.", window=(w[0, 0], w[-1, 0]))
    return None


def rule_hrv_trend(slut: float) -> Finding | None:
    """Nattlig HRV under baslinjen tre nätter i rad. Ofta det första tecknet på infektion eller överbelastning."""
    n3 = natter(3, slut)
    meds = []
    for a, b in n3:
        vals = [v for _, v in db.query_samples("hrv_rmssd", a, b)]
        if len(vals) < 3:
            return None
        meds.append(float(np.median(vals)))
    hist = []
    for a, b in natter(28, n3[-1][0] - 3600)[:25]:
        vals = [v for _, v in db.query_samples("hrv_rmssd", a, b)]
        if vals:
            hist.append(float(np.median(vals)))
    if len(hist) < 10:
        return None
    med = float(np.median(hist))
    sd = max(float(np.median(np.abs(np.array(hist) - med))) * MAD_TO_SD, MIN_SD["hrv_rmssd"])
    if all(m < med - sd for m in meds):
        return Finding("hrv_trend", "avvikelse", "hrv_rmssd", "HRV låg tre nätter i rad",
                       f"Nattlig HRV {', '.join(f'{m:.0f}' for m in reversed(meds))} ms mot normalt {med:.0f} ms "
                       f"(median av {len(hist)} nätter).", window=(n3[-1][0], n3[0][1]))
    return None


RULES: list[Callable[[float], Finding | None]] = [
    rule_fall,
    rule_hr_rest_acute,
    rule_hr_sudden_jump,
    rule_spo2_low,
    rule_spo2_dips,
    rule_metric_vs_baseline("hr", 20, 3.5, "Vilopulsen"),
    rule_metric_vs_baseline("resp_rate", 30, 3.5, "Andningsfrekvensen"),
    rule_metric_vs_baseline("skin_temp", 60, 3.0, "Hudtemperaturen"),
    rule_skin_temp_delta,
    rule_hrv_trend,
]


# ---------------------------------------------------------------- utvärdering

def _senast(rule: str) -> float:
    r = db.conn().execute("SELECT senast FROM vakt_state WHERE rule=?", (rule,)).fetchone()
    return r[0] if r else 0.0


def _satt_senast(rule: str, ts: float) -> None:
    with db.tx() as c:
        c.execute("INSERT OR REPLACE INTO vakt_state(rule, senast) VALUES (?,?)", (rule, ts))


def evaluate(slut: float | None = None) -> list[Finding]:
    with matning.tid("Vakt, regelkoll"):
        return _evaluate(slut or time.time())


def _evaluate(slut: float) -> list[Finding]:
    _schema()
    found = []
    for rule in RULES:
        try:
            f = rule(slut)
        except Exception as e:  # en trasig regel får aldrig stoppa vakten
            log.exception("regel %s kraschade: %s", getattr(rule, "__name__", rule), e)
            continue
        if f is None:
            continue
        handelse_tid = f.window[1] if f.window else slut
        # Nedkylning räknas på när det hände, och sparas i databasen så att den överlever omstart.
        if abs(handelse_tid - _senast(f.rule)) < COOLDOWN[f.level]:
            continue
        _satt_senast(f.rule, handelse_tid)
        if time.time() - handelse_tid > EFTERHAND_S:
            f.level = "avvikelse"  # har redan hänt: aldrig akut, aldrig sms
            f.title += " (upptäckt i efterhand)"
            f.detail += f" Gäller {datetime.fromtimestamp(handelse_tid).strftime('%Y-%m-%d %H:%M')}."
        found.append(f)
    return found


HISTORIK_S = 24 * 3600
TRAD_MELLANRUM_S = 12 * 3600  # högst en tråd från vakten per tolv timmar (en natt), utom vid akuta larm


def trad_tillats(f: Finding, nu: float) -> bool:
    _schema()
    if f.level == "akut":
        _satt_senast("__trad__", nu)
        return True
    if nu - _senast("__trad__") < TRAD_MELLANRUM_S:
        return False
    _satt_senast("__trad__", nu)
    return True  # avvikelser äldre än så (t.ex. 30 dagars historik vid första installationen) blir ingen tråd


def _handle(f: Finding) -> None:
    historik = bool(f.window) and time.time() - f.window[1] > HISTORIK_S
    bus.publish("vakt.anomaly", {"rule": f.rule, "level": f.level, "metric": f.metric, "historik": historik,
                                 "title": f.title, "detail": f.detail, "z": f.z, "window": f.window})
    if historik:
        # Syns i tidslinjen, men en tråd om något som hände för flera dagar sedan går inte att göra något åt.
        return
    if not trad_tillats(f, time.time()):
        # Samma natt eller förmiddag har redan en tråd: teamet tittar på hela perioden ändå.
        return
    if f.level == "akut":
        bus.publish("alert.raise", {"level": "akut", "title": f.title, "body": f.detail, "rule": f.rule})
    from . import vardag

    # Snabbsvaret ur datan kommer inom sekunder, teamets lösning efter några minuter.
    vardag.starta_trad({"kind": "anomaly", "rule": f.rule, "level": f.level, "metric": f.metric,
                           "title": f.title, "detail": f.detail, "window": f.window})


_wake = threading.Event()
_sen_data: list[tuple[float, float]] = []
_lock = threading.Lock()
_started = False


def _loop() -> None:
    while True:
        _wake.wait(TICK_SECONDS)
        _wake.clear()
        with _lock:
            perioder = list(_sen_data)
            _sen_data.clear()
        tider = {time.time()}
        # Sent inkommande data: utvärdera var 10:e minut genom den period som fått ny data.
        for a, b in perioder:
            t = b
            while t > a - 600 and len(tider) < 200:
                tider.add(t)
                t -= 600
        for t in sorted(tider):
            for f in evaluate(t):
                _handle(f)


def notify_new_data(metrics: list[str], tmin: float | None = None, tmax: float | None = None) -> None:
    if tmin is not None and tmax is not None and tmax < time.time() - 5 * 60:
        with _lock:
            _sen_data.append((tmin, tmax))
    _wake.set()


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="vakt", daemon=True).start()
