"""Faktabladet: allt räknas deterministiskt INNAN någon språkmodell läser datan.

Bakgrund (eval/RESULTAT.md): när specialisterna fick råa serier blandade de ihop värden, t.ex. kallades
den observerade pulsen 65 för "baslinjen" fast baslinjekällan sa 73,4. Nu får de färdiga, tydligt
namngivna fält: observerat_* är det som mättes nu, baslinje_* är personens normala nivå, skillnad_*
är differensen. Kvalitetskontroller (isolerade spikar, hopp mellan minuter, luckor) och träningsöverlapp
räknas också här, så att modellen inte behöver gissa om ett värde är ett mätfel eller ett löppass.

Varje del har en egen ref (F:...) och bär inbäddade ref:ar till rådatan (N:, L:, J:) där de finns.
Brådskan föreslås av öppna regler i `regelbradska`, inte av språkmodellen.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import numpy as np

from . import db

NIVAER = ["ingen", "bevaka", "ta_upp_med_varden", "kontakta_vard_nu"]


# Mobilens skärmtid (mobilappen, Skarmtid.kt): en punkt per minut och kategori, som datorn.
MOBILKAT = ("spel", "sociala", "video", "chatt", "webb", "annat")
DATORNAMN = {"kod": "programmering", "spel": "spel", "chatt": "chatt", "webb": "webb", "annat": "annat"}


def _hm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def _dag(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _r(x: float | None, d: int = 1) -> float | None:
    if x is None:
        return None
    v = round(float(x), d)
    return int(v) if d == 0 or v == int(v) else v


def _v(metric: str, a: float, b: float) -> np.ndarray:
    return np.array(db.query_samples(metric, a, b), dtype=float).reshape(-1, 2)


def _pass(a: float, b: float) -> list[dict[str, Any]]:
    rows = db.conn().execute("SELECT start, COALESCE(end, ?) e, typ FROM exercise WHERE start < ? AND COALESCE(end, ?) > ? "
                             "AND source NOT LIKE '%emulator%' ORDER BY start", (time.time(), b, time.time(), a)).fetchall()
    out = []
    for s, e, typ in rows:
        hr = _v("hr", s, e)
        efter = _v("hr", e + 600, e + 1200)
        out.append({"typ": typ, "start": _hm(s), "minuter": int((e - s) / 60),
                    "medelpuls_under_passet": _r(hr[:, 1].mean(), 0) if len(hr) else None,
                    "maxpuls_under_passet": _r(hr[:, 1].max(), 0) if len(hr) else None,
                    "puls_10_till_20_min_efter_passet": _r(np.median(efter[:, 1]), 0) if len(efter) else None})
    return out


def _baslinje(metric: str, timme: int) -> tuple[float, float] | None:
    try:
        from . import vakt
        b = vakt.baslinje(metric, timme)
        if b:
            return b[0], b[1]
    except Exception:
        pass
    return None


def _kvalitet(hr: np.ndarray) -> dict[str, Any]:
    """Tecken på mätfel i en pulsserie: isolerade spikar, orimliga hopp mellan minuter, luckor."""
    if len(hr) < 3:
        return {}
    v, t = hr[:, 1], hr[:, 0]
    d = np.abs(np.diff(v))
    dt = np.diff(t)
    tata = dt <= 90
    spikar = []
    for i in range(1, len(v) - 1):
        if v[i] >= 130 and v[i - 1] < 100 and v[i + 1] < 100 and t[i + 1] - t[i - 1] <= 600:
            spikar.append({"tid": _hm(t[i]), "varde": _r(v[i], 0), "grannarnas_medel": _r((v[i - 1] + v[i + 1]) / 2, 0)})
    span_min = (t[-1] - t[0]) / 60
    forvantat = span_min + 1 if np.median(dt) <= 90 else span_min / 5 + 1
    hopp = float((d[tata] > 25).mean()) if tata.any() else 0.0
    saknas = max(0.0, 1 - len(v) / forvantat)
    if hopp >= 0.25 or saknas >= 0.25:
        tolkning = "hoppig signal med luckor: klockan sitter troligen löst, värdena är inte tillförlitliga"
    elif spikar:
        tolkning = "enstaka isolerade spikar med normala grannvärden: sannolikt mätfel, inte verklig puls"
    else:
        tolkning = "ren signal, inga tecken på mätfel"
    return {
        "andel_hopp_over_25_slag_mellan_minuter": _r(hopp, 2), "andel_saknade_minuter": _r(saknas, 2),
        "isolerade_spikar": spikar[:8], "antal_isolerade_spikar": len(spikar), "tolkning": tolkning,
    }


def _episoder(a: float, b: float, bas: float) -> list[dict[str, Any]]:
    """Perioder i vila (inga steg, inget pass) där pulsen ligger minst 35 över vilobaslinjen och över 110
    i minst 3 minuter i följd."""
    hr = _v("hr", a, b)
    if len(hr) < 3:
        return []
    steg = {int(ts // 60) + k for ts, s in db.query_samples("steps", a - 600, b) if s >= 5 for k in range(-3, 4)}
    gr = max(bas + 35, 110)
    out, cur = [], []
    for ts, v in hr:
        hog = v >= gr and int(ts // 60) not in steg and not db.under_pass(ts - 60, ts)
        if hog and (not cur or ts - cur[-1][0] <= 150):
            cur.append((ts, v))
        else:
            if len(cur) >= 3:
                out.append(cur)
            cur = [(ts, v)] if hog else []
    if len(cur) >= 3:
        out.append(cur)
    res = []
    for ep in out:
        i0 = int(np.searchsorted(hr[:, 0], ep[0][0]))
        fore = hr[max(0, i0 - 5):i0, 1]
        res.append({"start": _hm(ep[0][0]), "minuter": int((ep[-1][0] - ep[0][0]) / 60) + 1,
                    "max": _r(max(v for _, v in ep), 0), "puls_strax_fore": _r(np.median(fore), 0) if len(fore) else None,
                    "pagar_fortfarande": bool(b - ep[-1][0] < 180)})
    return res


def _odi(sp: np.ndarray) -> tuple[int, float] | None:
    """Syrefall på minst 4 procentenheter (som ODI). Kräver tät mätning (minst varannan minut)."""
    if len(sp) < 60 or np.median(np.diff(sp[:, 0])) > 130:
        return None
    ref = float(np.percentile(sp[:, 1], 90))
    fall, i_fall = 0, False
    for v in sp[:, 1]:
        if not i_fall and v <= ref - 4:
            fall, i_fall = fall + 1, True
        elif i_fall and v >= ref - 1:
            i_fall = False
    timmar = (sp[-1, 0] - sp[0, 0]) / 3600
    return fall, (fall / timmar if timmar > 0.5 else 0.0)


def _natt(a: float, b: float, sid: str | None) -> dict[str, Any]:
    n: dict[str, Any] = {"natt_till": _dag(b), "somnade": _hm(a), "vaknade": _hm(b)}
    if sid:
        n["ref"] = f"N:{sid}"
        row = db.conn().execute("SELECT stages FROM sleep WHERE id=?", (sid,)).fetchone()
        vaken = sum(s["end"] - s["start"] for s in json.loads(row[0]) if s["stage"] == "awake") if row else 0
        n["somn_timmar"] = _r((b - a - vaken) / 3600, 1)
    hrv = _v("hrv_rmssd", a, b)
    hr = _v("hr", a, b)
    if len(hrv):
        n["hrv_median_ms"] = _r(np.median(hrv[:, 1]), 0)
    if len(hr) >= 10:
        n["nattpuls_lagsta_10min"] = _r(np.convolve(hr[:, 1], np.ones(10) / 10, "valid").min(), 0)
    for metric, namn, d in (("skin_temp", "hudtemp_median_c", 2), ("resp_rate", "andning_median_per_min", 1),
                            ("spo2", "spo2_median", 0)):
        x = _v(metric, a, b)
        if len(x):
            n[namn] = _r(np.median(x[:, 1]), d)
    sp = _v("spo2", a, b)
    o = _odi(sp)
    if o:
        n["spo2_fall_antal"], n["spo2_fall_per_timme"] = o[0], _r(o[1], 1)
        n["spo2_lagsta"] = _r(sp[:, 1].min(), 0)
        if 1 <= o[0] <= 2 and o[1] < 5:
            n["spo2_tolkning"] = ("enstaka fall en natt: vanligen mätfel (tryck mot klockan, sovställning) "
                                  "snarare än andningsuppehåll; ett mönster kräver upprepade fall flera nätter")
    return n


NATTFALT = ["somn_timmar", "hrv_median_ms", "nattpuls_lagsta_10min", "hudtemp_median_c", "andning_median_per_min",
            "spo2_median"]


def natter(nu: float, antal: int = 7) -> dict[str, Any]:
    rows = db.conn().execute("SELECT id, start, end FROM sleep WHERE end <= ? AND end > ? AND source NOT LIKE '%emulator%' "
                             "ORDER BY end DESC", (nu, nu - 28 * 86400)).fetchall()
    alla = [_natt(r[1], r[2], r[0]) for r in rows]
    senaste, aldre = alla[:antal], alla[antal:]
    out: dict[str, Any] = {"ref": "F:natter", "beskrivning": "senaste nätterna, nyast först",
                           "natter": senaste}
    if aldre:
        bas = {}
        for f in NATTFALT:
            vals = [n[f] for n in aldre if n.get(f) is not None]
            if len(vals) >= 5:
                bas[f] = _r(np.median(vals), 2 if f == "hudtemp_median_c" else 1)
        out["baslinje_natt"] = {"beskrivning": f"median av {len(aldre)} tidigare nätter", **bas}
        tre = senaste[:3]
        skillnad = {}
        for f, b in bas.items():
            vals = [n[f] for n in tre if n.get(f) is not None]
            if vals:
                skillnad[f] = _r(float(np.mean(vals)) - b, 2 if f == "hudtemp_median_c" else 1)
        out["skillnad_senaste_3_natter_mot_baslinje"] = {
            "beskrivning": "medel av de 3 senaste nätterna minus baslinjen: negativt = lägre än normalt", **skillnad}
        out["riktning_senaste_3_natter_mot_baslinje"] = {
            f: ("högre än baslinjen" if v > 0 else "lägre än baslinjen" if v < 0 else "samma som baslinjen")
            for f, v in skillnad.items()}
        if bas.get("hrv_median_ms") and "hrv_median_ms" in skillnad:
            out["skillnad_senaste_3_natter_mot_baslinje"]["hrv_procent"] = _r(100 * skillnad["hrv_median_ms"] / bas["hrv_median_ms"], 0)
        odi = [n.get("spo2_fall_per_timme") for n in senaste if n.get("spo2_fall_per_timme") is not None]
        if odi:
            out["natter_med_minst_5_syrefall_per_timme"] = sum(1 for x in odi if x >= 5)
            out["syrefall_definition"] = "fall på minst 4 procentenheter under nattens 90:e percentil (som ODI)"
        sov = [n["somn_timmar"] for n in senaste if n.get("somn_timmar")]
        if sov:
            out["medel_somn_timmar_senaste"] = _r(np.mean(sov), 1)
    # pågående natt (larm mitt i natten)
    h = datetime.fromtimestamp(nu).hour
    if h < 9:
        senast_slut = rows[0][2] if rows else nu - 12 * 3600
        a = max(senast_slut + 3600, nu - 8 * 3600)
        pg = _natt(a, nu, None)
        pg.pop("vaknade", None)
        pg["somnade"] = None
        pg["beskrivning"] = f"pågående natt, data {_hm(a)}-{_hm(nu)}"
        out["pagaende_natt"] = pg
    return out


def dagar(nu: float, antal: int = 7) -> dict[str, Any]:
    idag = datetime.fromtimestamp(nu).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    out = []
    for i in range(antal):
        a = idag - i * 86400
        b = min(a + 86400, nu)
        steg = _v("steps", a, b)
        d: dict[str, Any] = {"datum": _dag(a) + (" (idag, hittills)" if i == 0 else ""),
                             "steg": int(steg[:, 1].sum()) if len(steg) else 0}
        dator = {}
        for kat in ("kod", "spel", "chatt", "webb", "annat"):
            x = _v(f"dator_{kat}", a, b)
            if len(x):
                dator[DATORNAMN[kat]] = len(x)
        if dator:
            d["minuter_vid_datorn_per_kategori"] = dator
        mobil = {kat: len(x) for kat in MOBILKAT if len(x := _v(f"mobil_{kat}", a, b))}
        if mobil:
            d["minuter_med_mobilen_per_kategori"] = mobil
        km = [x for kat in MOBILKAT for x in _v(f"mobil_{kat}", a + 18 * 3600, min(a + 30 * 3600, nu))[:, 0]]
        if km:
            d["mobil_minuter_efter_23"] = int(sum(1 for t in km if t >= a + 23 * 3600))
            d["sista_mobilminut_pa_kvallen"] = _hm(max(km))
        # kvällen: 18 den här dagen till 06 nästa morgon
        kv = [x for kat in ("kod", "spel", "chatt", "webb", "annat") for x in _v(f"dator_{kat}", a + 18 * 3600, min(a + 30 * 3600, nu))[:, 0]]
        if kv:
            d["dator_minuter_efter_23"] = int(sum(1 for t in kv if t >= a + 23 * 3600))
            d["sista_datorminut_pa_kvallen"] = _hm(max(kv))
        p = _pass(a, b)
        if p:
            d["traningspass"] = p
        out.append(d)
    res: dict[str, Any] = {"ref": "F:dagar", "beskrivning": "dygn, nyast först", "dagar": out}
    hist = []
    for i in range(antal, 28):
        a = idag - i * 86400
        s = _v("steps", a, a + 86400)
        if len(s):
            hist.append(s[:, 1].sum())
    if len(hist) >= 5:
        res["baslinje_steg_per_dag"] = int(np.median(hist))
    return res


def aktivitet_och_aterhamtning(nu: float, dagar_bakat: int = 14) -> dict[str, Any] | None:
    """Jämför nätterna efter aktiva dagar med nätterna efter stillasittande dagar."""
    idag = datetime.fromtimestamp(nu).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    grupper: dict[str, list[dict[str, Any]]] = {"aktiva": [], "stillasittande": []}
    for i in range(1, dagar_bakat + 1):
        a = idag - i * 86400
        s = _v("steps", a, a + 86400)
        steg = s[:, 1].sum() if len(s) else 0
        row = db.conn().execute("SELECT id, start, end FROM sleep WHERE start BETWEEN ? AND ? ORDER BY start LIMIT 1",
                                (a + 18 * 3600, a + 30 * 3600)).fetchone()
        if not row:
            continue
        n = _natt(row[1], row[2], row[0])
        n["steg_dagen_fore"] = int(steg)
        if steg >= 8000:
            grupper["aktiva"].append(n)
        elif steg < 4000:
            grupper["stillasittande"].append(n)
    if not grupper["aktiva"] or not grupper["stillasittande"]:
        return None
    res: dict[str, Any] = {"ref": "F:aktivitet", "beskrivning": "nätterna efter dagar med minst 8000 steg jämfört "
                           "med nätterna efter dagar under 4000 steg"}
    for g, ns in grupper.items():
        res[g] = {"antal_dagar": len(ns), "steg_median": int(np.median([n["steg_dagen_fore"] for n in ns]))}
        for f in ("hrv_median_ms", "nattpuls_lagsta_10min", "somn_timmar"):
            vals = [n[f] for n in ns if n.get(f) is not None]
            if vals:
                res[g][f"foljande_natt_{f}"] = _r(np.median(vals), 1)
    return res


def larm(trigger: dict[str, Any], nu: float) -> dict[str, Any] | None:
    metric = trigger.get("metric")
    if trigger.get("kind") != "anomaly" or metric not in ("hr", "spo2", "resp_rate", "skin_temp", "hrv_rmssd"):
        return None
    w = trigger.get("window") or [nu - 600, nu]
    a, b = float(w[0]), float(w[1])
    if metric == "hrv_rmssd":
        return None  # nattrend: allt finns i F:natter
    x = _v(metric, a, b)
    out: dict[str, Any] = {"ref": "F:larm", "matvarde": metric, "period": f"{_hm(a)}-{_hm(b)}"}
    if len(x):
        out.update({"observerat_median": _r(np.median(x[:, 1]), 1), "observerat_min": _r(x[:, 1].min(), 1),
                    "observerat_max": _r(x[:, 1].max(), 1), "antal_matpunkter": len(x)})
    bas = _baslinje(metric, datetime.fromtimestamp(b).hour)
    if bas and len(x):
        out["baslinje_samma_timme_median"] = _r(bas[0], 1)
        out["baslinje_spridning_sd"] = _r(bas[1], 1)
        out["skillnad_observerat_minus_baslinje"] = _r(out["observerat_median"] - bas[0], 1)
        out["riktning_mot_baslinje"] = "högre" if out["skillnad_observerat_minus_baslinje"] > 0 else "lägre"
    fore = _v(metric, a - 3600, a - 300)
    if len(fore):
        out["median_timmen_fore_larmet"] = _r(np.median(fore[:, 1]), 1)
    steg = _v("steps", a - 600, b)
    out["steg_10_min_fore_och_under"] = int(steg[:, 1].sum()) if len(steg) else 0
    p = _pass(a - 1800, b)
    out["traningspass_under_eller_strax_fore"] = p or "inget"
    dator = {DATORNAMN[kat]: len(_v(f"dator_{kat}", a, b)) for kat in ("kod", "spel", "chatt", "webb", "annat")}
    dator = {k: v for k, v in dator.items() if v}
    out["minuter_vid_datorn_under_perioden"] = dator or "inga"
    mobil = {kat: len(x) for kat in MOBILKAT if len(x := _v(f"mobil_{kat}", a, b))}
    out["minuter_med_mobilen_under_perioden"] = mobil or "inga"
    if metric == "hr":
        hr60 = _v("hr", b - 3600, b)
        out["kvalitet_senaste_timmen"] = _kvalitet(hr60)
        if len(hr60) >= 3:
            out["storsta_okning_pa_2_minuter_senaste_timmen"] = _r(max(
                (hr60[j, 1] - hr60[i, 1] for i in range(len(hr60)) for j in range(i + 1, min(i + 3, len(hr60)))
                 if hr60[j, 0] - hr60[i, 0] <= 150), default=0), 0)
        b0 = _baslinje("hr", datetime.fromtimestamp(b).hour)
        idag = datetime.fromtimestamp(nu).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        ep = _episoder(idag, nu, b0[0] if b0 else 70)
        out["pulsepisoder_i_vila_idag"] = ep or "inga"
    if metric in ("spo2", "resp_rate"):
        for m2 in ("spo2", "resp_rate", "hr"):
            if m2 != metric:
                y = _v(m2, a, b)
                if len(y):
                    out[f"samtidigt_{m2}_median"] = _r(np.median(y[:, 1]), 1)
    return out


def puls_dygn(nu: float, timmar: float = 24) -> dict[str, Any] | None:
    a = nu - timmar * 3600
    hr = _v("hr", a, nu)
    if len(hr) < 10:
        return None
    imax = int(np.argmax(hr[:, 1]))
    pass_ = db.conn().execute("SELECT start, COALESCE(end, ?) FROM exercise WHERE start < ? AND COALESCE(end, ?) > ?",
                              (nu, nu, nu, a)).fetchall()
    under_pass = np.zeros(len(hr), bool)
    for s, e in pass_:
        under_pass |= (hr[:, 0] >= s) & (hr[:, 0] <= e + 600)
    steg = {int(ts // 60) for ts, s in db.query_samples("steps", a, nu) if s >= 5}
    dt = float(np.median(np.diff(hr[:, 0]))) / 60
    hog = hr[:, 1] >= 140
    out: dict[str, Any] = {
        "ref": "F:puls", "period": f"senaste {int(timmar)} timmarna",
        "median": _r(np.median(hr[:, 1]), 0), "max": _r(hr[imax, 1], 0), "max_tid": _hm(hr[imax, 0]),
        "max_under_traningspass": bool(under_pass[imax]),
        "minuter_over_140": int(hog.sum() * dt), "varav_under_eller_direkt_efter_pass": int((hog & under_pass).sum() * dt),
        "varav_med_steg_samma_minut": int(sum(1 for i in np.nonzero(hog)[0] if int(hr[i, 0] // 60) in steg) * dt),
        "kvalitet": _kvalitet(hr),
    }
    return out


def just_nu(nu: float) -> dict[str, Any]:
    out: dict[str, Any] = {"ref": "F:nu", "klockan": _hm(nu), "period": "senaste 15 minuterna"}
    for metric, namn in (("hr", "puls_median"), ("spo2", "spo2_median"), ("resp_rate", "andning_median")):
        x = _v(metric, nu - 900, nu)
        if len(x):
            out[namn] = _r(np.median(x[:, 1]), 0)
    s = _v("steps", nu - 900, nu)
    out["steg"] = int(s[:, 1].sum()) if len(s) else 0
    if "puls_median" in out:
        bas = _baslinje("hr", datetime.fromtimestamp(nu).hour)
        if bas:
            out["puls_baslinje_samma_timme"] = _r(bas[0], 0)
            out["skillnad_puls_mot_baslinje"] = _r(out["puls_median"] - bas[0], 0)
            out["riktning_puls_mot_baslinje"] = "högre" if out["skillnad_puls_mot_baslinje"] > 0 else "lägre"
        fore = _v("hr", nu - 3 * 3600, nu - 3600)
        if len(fore):
            out["puls_median_1_till_3_timmar_sedan"] = _r(np.median(fore[:, 1]), 0)
    x5 = _v("hr", nu - 300, nu)
    if len(x5):
        out["puls_senaste_5_min_median"] = _r(np.median(x5[:, 1]), 0)
        out["puls_senaste_5_min_max"] = _r(x5[:, 1].max(), 0)
    s5 = _v("steps", nu - 900, nu)
    out["steg_senaste_15_min_per_minut_max"] = int(s5[:, 1].max()) if len(s5) else 0
    v60 = _v("hr", nu - 3600, nu)
    s60 = _v("steps", nu - 3600, nu)
    if len(v60) >= 30:
        out["puls_median_senaste_timmen"] = _r(np.median(v60[:, 1]), 0)
        out["steg_senaste_timmen"] = int(s60[:, 1].sum()) if len(s60) else 0
    p = _pass(nu - 900, nu)
    if p:
        out["traningspass"] = p
    return out


def prover(nu: float) -> dict[str, Any] | None:
    rows = [dict(r) for r in db.conn().execute(
        "SELECT id, date, analyte, value, value_raw, unit, ref_low, ref_high, flag FROM labs ORDER BY date DESC")]
    if not rows:
        return None
    senaste: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["analyte"] in senaste:
            continue
        v, lo, hi = r["value"], r["ref_low"], r["ref_high"]
        utanfor = None
        if v is not None and lo is not None and v < lo:
            utanfor = "under referensintervallet"
        elif v is not None and hi is not None and v > hi:
            utanfor = "över referensintervallet"
        dagar_sedan = int((nu - datetime.strptime(r["date"], "%Y-%m-%d").timestamp()) / 86400)
        senaste[r["analyte"]] = {"ref": f"L:{r['id']}", "analys": r["analyte"], "varde": r["value_raw"],
                                 "enhet": r["unit"], "referens": f"{lo if lo is not None else ''}-{hi if hi is not None else ''}",
                                 "datum": r["date"], "dagar_sedan": dagar_sedan, "bedomning_mot_referens": utanfor or "inom"}
    return {"ref": "F:prover", "beskrivning": "senaste provsvaret per analys", "prover": list(senaste.values())}


def journal(max_antal: int = 6) -> dict[str, Any] | None:
    rows = [dict(r) for r in db.conn().execute(
        "SELECT id, date, kind, title, substr(text,1,300) text FROM journal ORDER BY date DESC LIMIT ?", (max_antal,))]
    if not rows:
        return None
    return {"ref": "F:journal", "anteckningar": [{"ref": f"J:{r.pop('id')}", **r} for r in rows]}


def somnskuld(nu: float) -> dict[str, Any] | None:
    """Sömnskuld med samma räkning som vardagen (vardag.somn): behov minus sovna timmar, summerat över
    de senaste sju morgnarna. Plus jämförelse mot personens egen baslinje."""
    try:
        from . import vardag
        s = vardag.somn(nu)
    except Exception:
        return None
    nn = s.get("natter") or []
    if not nn:
        return None
    timmar = [n["timmar"] for n in nn]
    out: dict[str, Any] = {
        "ref": "F:somnskuld", "beskrivning": "samma räkning som appens sömnskuld: summa av (behov - sömn) per natt",
        "somnbehov_timmar": s["behov_h"], "natter_med_data": len(nn),
        "somnskuld_timmar_senaste_7_natter": s["skuld_h"],
        "medel_somn_timmar_senaste_7": _r(np.mean(timmar), 1),
        "natter_under_7_timmar": sum(1 for t in timmar if t < 7),
        "natter_med_datorn_efter_midnatt": s.get("sena_natter_vid_datorn", 0),
    }
    aldre = db.conn().execute("SELECT start, end, stages FROM sleep WHERE end <= ? AND end > ? AND source NOT LIKE '%emulator%'",
                              (nu - 7 * 86400, nu - 28 * 86400)).fetchall()
    if len(aldre) >= 5:
        tim = [(e - a - sum(x["end"] - x["start"] for x in json.loads(st) if x["stage"] == "awake")) / 3600 for a, e, st in aldre]
        out["baslinje_somn_timmar_tidigare_veckor"] = _r(np.median(tim), 1)
        out["skillnad_medel_somn_mot_baslinje_timmar"] = _r(out["medel_somn_timmar_senaste_7"] - np.median(tim), 1)
    return out


def sena_kvallar(nu: float, antal: int = 7) -> dict[str, Any] | None:
    """Datorn efter 23:00 per kväll (dator_*-mätvärdena), de senaste kvällarna, nyast först."""
    idag = datetime.fromtimestamp(nu).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    kvallar = []
    for i in range(antal):
        a = idag - i * 86400 + 23 * 3600  # 23:00 den kvällen
        b = min(a + 7 * 3600, nu)        # till 06:00
        if a >= nu:
            continue
        ts = sorted(t for kat in ("kod", "spel", "chatt", "webb", "annat") for t in _v(f"dator_{kat}", a, b)[:, 0])
        per = {DATORNAMN[k]: len(_v(f"dator_{k}", a, b)) for k in ("kod", "spel", "chatt", "webb", "annat")}
        kvallar.append({"kvall": _dag(a), "minuter_vid_datorn_efter_23": len(ts),
                        "sista_datorminut": _hm(ts[-1]) if ts else None,
                        "per_kategori": {k: v for k, v in per.items() if v} or "inga"})
    if not any(k["minuter_vid_datorn_efter_23"] for k in kvallar):
        return {"ref": "F:kvallar", "beskrivning": "datorn efter 23:00", "kvallar_med_datorn_efter_23": 0}
    return {"ref": "F:kvallar", "beskrivning": "datorn efter 23:00 per kväll, nyast först",
            "kvallar_med_datorn_efter_23": sum(1 for k in kvallar if k["minuter_vid_datorn_efter_23"]),
            "kvallar_med_datorn_efter_01": sum(1 for k in kvallar if k["sista_datorminut"] and "01:00" <= k["sista_datorminut"] < "06:00"),
            "kvallar": kvallar}


def traningsbelastning(nu: float, dagar_bakat: int = 7) -> dict[str, Any]:
    """Träningspass de senaste dygnen och minuter i hög pulszon (vardag.belastning) de senaste tre."""
    pass_ = _pass(nu - dagar_bakat * 86400, nu)
    out: dict[str, Any] = {"ref": "F:belastning", "period": f"senaste {dagar_bakat} dygnen",
                           "antal_traningspass": len(pass_), "traningsminuter_totalt": sum(p["minuter"] for p in pass_),
                           "pass": pass_ or "inga"}
    try:
        from . import vardag
        b = vardag.belastning(nu)
        out["minuter_i_zon_4_5_per_dag_senaste_3"] = b.get("hart_min_per_dag") or "inga"
        out["tranade_igar"] = b.get("tranade_igar")
    except Exception:
        pass
    return out


def faktaark(trigger: dict[str, Any], nu: float | None = None) -> dict[str, dict[str, Any]]:
    nu = nu or time.time()
    timmar = float(trigger.get("hours") or 24)
    delar = [
        larm(trigger, nu),
        just_nu(nu),
        puls_dygn(nu, min(max(timmar, 24), 48)),
        natter(nu),
        dagar(nu, 14 if timmar > 200 else 7),
        aktivitet_och_aterhamtning(nu) if timmar > 200 else None,
        somnskuld(nu),
        sena_kvallar(nu),
        traningsbelastning(nu),
        prover(nu),
        journal(),
    ]
    return {d["ref"]: d for d in delar if d}


# ---------------------------------------------------------------- brådska efter öppna regler

def regelbradska(trigger: dict[str, Any], f: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """Brådskan efter uttryckliga kliniska tumregler. Returnerar nivå och skälen.

    Regler (i ordning, högsta nivån vinner):
      kontakta_vard_nu   bara om vakten larmat akut OCH mätningen håller: puls i vila >= 140 (median) utan
                         träningspass, utan steg och utan tecken på mätfel; eller SpO2 median < 90 i vakenhet.
      ta_upp_med_varden  provsvar utanför referens senaste 180 dagarna; minst 3 nätter med >= 5 syrefall/timme
                         (eller pågående natt); minst 2 pulsepisoder i vila idag med plötslig start.
      bevaka             avvikelselarm som inte förklaras av träning eller mätfel; tre nätter med HRV minst 15 %
                         under baslinjen; medelsömn under 6 timmar.
      ingen              annars.
    """
    niva, skal = 0, []

    def hoj(n: str, s: str) -> None:
        nonlocal niva
        skal.append(f"{n}: {s}")
        niva = max(niva, NIVAER.index(n))

    L = f.get("F:larm") or {}
    kval = L.get("kvalitet_senaste_timmen") or {}
    matfel = (kval.get("andel_hopp_over_25_slag_mellan_minuter") or 0) >= 0.25 or \
             (kval.get("andel_saknade_minuter") or 0) >= 0.25
    traning = L.get("traningspass_under_eller_strax_fore") not in (None, "inget") or L.get("steg_10_min_fore_och_under", 0) >= 300
    if trigger.get("kind") == "anomaly":
        med = L.get("observerat_median")
        if trigger.get("level") == "akut" and not matfel and not traning:
            if L.get("matvarde") == "hr" and med is not None and med >= 140:
                hoj("kontakta_vard_nu", f"puls i vila median {med} utan träning, steg eller mätfel")
            elif L.get("matvarde") == "spo2" and med is not None and med < 90:
                hoj("kontakta_vard_nu", f"syremättnad median {med} %")
            elif trigger.get("metric") == "fall_detected":
                hoj("kontakta_vard_nu", "klockan registrerade ett fall")
        if matfel:
            hoj("bevaka", "larmet ser ut som mätfel (hoppiga värden eller luckor): dra åt klockan och mät om")
        elif traning:
            skal.append("ingen: larmet sammanfaller med träning eller rörelse")
        else:
            hoj("bevaka", "vaktens avvikelselarm")
        ep = L.get("pulsepisoder_i_vila_idag")
        if isinstance(ep, list) and len(ep) >= 2 and not matfel:  # episoder i hoppig data är mätfel
            hoj("ta_upp_med_varden", f"{len(ep)} pulsepisoder i vila idag med plötslig start")
    nu_ = f.get("F:nu") or {}
    if trigger.get("kind") == "question" and nu_.get("puls_baslinje_samma_timme") and nu_.get("puls_median_senaste_timmen") \
            and nu_.get("steg_senaste_timmen", 999) < 100 \
            and nu_["puls_median_senaste_timmen"] - nu_["puls_baslinje_samma_timme"] >= 25:
        # samma sak som vaktens baslinjeregel: vilopulsen har legat långt över det normala i en timme utan rörelse
        hoj("bevaka", f"vilopuls {nu_['puls_median_senaste_timmen']} senaste timmen utan rörelse mot normalt "
                      f"{nu_['puls_baslinje_samma_timme']}")
    for p in (f.get("F:prover") or {}).get("prover", []):
        if p["bedomning_mot_referens"] != "inom" and p["dagar_sedan"] <= 180:
            hoj("ta_upp_med_varden", f"{p['analys']} {p['varde']} {p['enhet']} {p['bedomning_mot_referens']}")
    N = f.get("F:natter") or {}
    if (N.get("natter_med_minst_5_syrefall_per_timme") or 0) >= 3 or \
            ((N.get("pagaende_natt") or {}).get("spo2_fall_per_timme") or 0) >= 5:
        hoj("ta_upp_med_varden", "upprepade nattliga syrefall (minst 5 per timme)")
    sk = N.get("skillnad_senaste_3_natter_mot_baslinje") or {}
    bas = N.get("baslinje_natt") or {}
    if sk.get("hrv_median_ms") is not None and bas.get("hrv_median_ms") and sk["hrv_median_ms"] <= -0.15 * bas["hrv_median_ms"]:
        tecken = [t for t, ok in (("hudtemperatur upp", (sk.get("hudtemp_median_c") or 0) >= 0.3),
                                  ("andning upp", (sk.get("andning_median_per_min") or 0) >= 1),
                                  ("nattpuls upp", (sk.get("nattpuls_lagsta_10min") or 0) >= 4)) if ok]
        pass_ = [p for d in (f.get("F:dagar") or {}).get("dagar", [])[:4] for p in d.get("traningspass", [])]
        if (sk.get("hudtemp_median_c") or 0) >= 0.3:
            tolkning = "hudtemperaturen har stigit: mönstret talar för begynnande infektion"
        elif pass_:
            tolkning = (f"{len(pass_)} träningspass senaste dygnen och normal hudtemperatur: talar för "
                        "träningsbelastning snarare än infektion")
        else:
            tolkning = "ingen träning och normal temperatur: belastning, sömn eller stress, följ upp"
        hoj("bevaka", "HRV under baslinjen tre nätter" + (f" med {', '.join(tecken)}" if tecken else "") + f"; {tolkning}")
    if (N.get("medel_somn_timmar_senaste") or 9) < 6:
        hoj("bevaka", f"medelsömn {N['medel_somn_timmar_senaste']} timmar")
    return NIVAER[niva], skal
