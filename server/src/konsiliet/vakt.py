"""Vakten. Körs hela tiden och letar avvikelser mot min egen baslinje.

Två nivåer:
  1. Akut (regelbaserat, millisekunder): t.ex. puls 150 i vila eller SpO2 under 88 %.
     Larmar mobilen direkt, utan att vänta på någon språkmodell.
  2. Avvikelse (statistiskt): robust z-poäng mot samma timme på dygnet de senaste 28 dagarna,
     plus trender över flera nätter (HRV, vilopuls). Kallar in konsiliet.

Baslinjen är median och MAD (median absolute deviation) per mätvärde och timme. MAD i stället för
standardavvikelse så att enstaka träningspass inte förstör baslinjen.
"""
from __future__ import annotations

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
TICK_SECONDS = 60
MAD_TO_SD = 1.4826  # MAD * 1.4826 ~ standardavvikelse för normalfördelning


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

def _window(metric: str, minutes: float) -> np.ndarray:
    pts = db.query_samples(metric, time.time() - minutes * 60)
    return np.array(pts, dtype=float).reshape(-1, 2)


def _baseline(metric: str, hour: int) -> tuple[float, float] | None:
    """Median och robust spridning för given timme på dygnet, senaste BASELINE_DAYS dagarna."""
    now = time.time()
    rows = db.conn().execute(
        "SELECT ts, value FROM samples WHERE metric=? AND ts BETWEEN ? AND ?",
        (metric, now - BASELINE_DAYS * 86400, now - 3600),
    ).fetchall()
    vals = [v for ts, v in rows if datetime.fromtimestamp(ts).hour == hour]
    if len(vals) < 60:
        return None
    a = np.array(vals)
    med = float(np.median(a))
    mad = float(np.median(np.abs(a - med))) * MAD_TO_SD
    return med, max(mad, 1e-6)


def _resting(minutes: float) -> bool:
    """Sant om nästan inga steg tagits under perioden."""
    steps = _window("steps", minutes)
    return steps.size == 0 or float(steps[:, 1].sum()) < 20


# ---------------------------------------------------------------- regler

def rule_hr_rest_acute() -> Finding | None:
    hr = _window("hr", 10)
    if len(hr) < 5 or not _resting(10):
        return None
    med = float(np.median(hr[:, 1]))
    if med >= 140:
        return Finding("hr_rest_acute", "akut", "hr", "Mycket hög puls i vila",
                       f"Medianpuls {med:.0f} slag/min de senaste 10 minuterna utan rörelse.",
                       window=(hr[0, 0], hr[-1, 0]))
    return None


def rule_hr_sudden_jump() -> Finding | None:
    """Plötsligt hopp i puls utan rörelse, till exempel en hjärtrusning."""
    hr = _window("hr", 5)
    if len(hr) < 6 or not _resting(5):
        return None
    first, last = np.median(hr[:3, 1]), np.median(hr[-3:, 1])
    if last - first >= 35 and last >= 110:
        return Finding("hr_sudden_jump", "akut", "hr", "Plötsligt pulshopp i vila",
                       f"Pulsen steg från {first:.0f} till {last:.0f} på några minuter utan rörelse.",
                       window=(hr[0, 0], hr[-1, 0]))
    return None


def rule_spo2_low() -> Finding | None:
    sp = _window("spo2", 5)
    if len(sp) < 3:
        return None
    med = float(np.median(sp[:, 1]))
    if med < 88:
        return Finding("spo2_low", "akut", "spo2", "Lågt syremättnad",
                       f"SpO2 median {med:.0f} % de senaste 5 minuterna.", window=(sp[0, 0], sp[-1, 0]))
    return None


def rule_spo2_dips() -> Finding | None:
    """Upprepade fall på minst 4 procentenheter under natten (som ODI i sömnapnéutredningar)."""
    sp = _window("spo2", 60)
    if len(sp) < 30:
        return None
    vals = sp[:, 1]
    baseline = np.percentile(vals, 90)
    dips, in_dip = 0, False
    for v in vals:
        if not in_dip and v <= baseline - 4:
            dips, in_dip = dips + 1, True
        elif in_dip and v >= baseline - 1:
            in_dip = False
    if dips >= 5:
        return Finding("spo2_dips", "avvikelse", "spo2", "Upprepade syrefall",
                       f"{dips} fall på minst 4 procentenheter senaste timmen (baslinje {baseline:.0f} %).",
                       window=(sp[0, 0], sp[-1, 0]))
    return None


def rule_metric_vs_baseline(metric: str, minutes: int, z_limit: float, label: str) -> Callable[[], Finding | None]:
    def rule() -> Finding | None:
        w = _window(metric, minutes)
        if len(w) < 5:
            return None
        if metric == "hr" and not _resting(minutes):
            return None
        base = _baseline(metric, datetime.now().hour)
        if base is None:
            return None
        med, sd = base
        cur = float(np.median(w[:, 1]))
        z = (cur - med) / sd
        if abs(z) >= z_limit:
            riktning = "över" if z > 0 else "under"
            return Finding(f"baseline_{metric}", "avvikelse", metric, f"{label} avviker från din baslinje",
                           f"{label} {cur:.1f} mot normalt {med:.1f} vid den här tiden ({abs(z):.1f} SD {riktning}).",
                           z=z, window=(w[0, 0], w[-1, 0]))
        return None
    rule.__name__ = f"baseline_{metric}"
    return rule


def rule_hrv_trend() -> Finding | None:
    """Nattlig HRV under baslinjen tre nätter i rad. Ofta det första tecknet på infektion eller överbelastning."""
    now = time.time()
    nights = []
    for d in range(3):
        end = now - d * 86400
        pts = db.query_samples("hrv_rmssd", end - 86400, end)
        night = [v for ts, v in pts if datetime.fromtimestamp(ts).hour in (0, 1, 2, 3, 4, 5)]
        if len(night) < 10:
            return None
        nights.append(float(np.median(night)))
    hist = db.query_samples("hrv_rmssd", now - BASELINE_DAYS * 86400, now - 3 * 86400)
    hist_n = [v for ts, v in hist if datetime.fromtimestamp(ts).hour in (0, 1, 2, 3, 4, 5)]
    if len(hist_n) < 100:
        return None
    med = float(np.median(hist_n))
    sd = float(np.median(np.abs(np.array(hist_n) - med))) * MAD_TO_SD
    if all(n < med - 1.0 * sd for n in nights):
        return Finding("hrv_trend", "avvikelse", "hrv_rmssd", "HRV låg tre nätter i rad",
                       f"Nattlig HRV {', '.join(f'{n:.0f}' for n in reversed(nights))} ms mot normalt {med:.0f} ms.")
    return None


def rule_fall() -> Finding | None:
    """Klockans egen falldetektering: larma direkt."""
    pts = db.query_samples("fall_detected", time.time() - 5 * 60)
    if any(v >= 1 for _, v in pts):
        return Finding("fall", "akut", "fall_detected", "Klockan registrerade ett fall",
                       "Pixel Watch falldetektering slog till de senaste minuterna.")
    return None


RULES: list[Callable[[], Finding | None]] = [
    rule_fall,
    rule_hr_rest_acute,
    rule_hr_sudden_jump,
    rule_spo2_low,
    rule_spo2_dips,
    rule_metric_vs_baseline("hr", 20, 3.5, "Vilopulsen"),
    rule_metric_vs_baseline("resp_rate", 30, 3.5, "Andningsfrekvensen"),
    rule_metric_vs_baseline("skin_temp", 60, 3.0, "Hudtemperaturen"),
    rule_hrv_trend,
]

COOLDOWN = {"akut": 15 * 60, "avvikelse": 6 * 3600}
_last_fired: dict[str, float] = {}
_wake = threading.Event()
_started = False


def evaluate() -> list[Finding]:
    with matning.tid("Vakt, regelkoll"):
        return _evaluate()


def _evaluate() -> list[Finding]:
    found = []
    for rule in RULES:
        try:
            f = rule()
        except Exception as e:  # en trasig regel får aldrig stoppa vakten
            log.exception("regel %s kraschade: %s", getattr(rule, "__name__", rule), e)
            continue
        if f is None:
            continue
        if time.time() - _last_fired.get(f.rule, 0) < COOLDOWN[f.level]:
            continue
        _last_fired[f.rule] = time.time()
        found.append(f)
    return found


def _handle(f: Finding) -> None:
    bus.publish("vakt.anomaly", {"rule": f.rule, "level": f.level, "metric": f.metric,
                                 "title": f.title, "detail": f.detail, "z": f.z, "window": f.window})
    if f.level == "akut":
        bus.publish("alert.raise", {"level": "akut", "title": f.title, "body": f.detail, "rule": f.rule})
    from . import konsiliet

    konsiliet.start_async({"kind": "anomaly", "rule": f.rule, "level": f.level, "metric": f.metric,
                           "title": f.title, "detail": f.detail, "window": f.window})


def _loop() -> None:
    while True:
        _wake.wait(TICK_SECONDS)
        _wake.clear()
        for f in evaluate():
            _handle(f)


def notify_new_data(metrics: list[str]) -> None:
    _wake.set()


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="vakt", daemon=True).start()
