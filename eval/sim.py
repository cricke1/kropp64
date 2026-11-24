"""Syntetisk person för utvärderingen. ALL data härifrån är påhittad testdata och märks source='syntetisk'.

En minutupplöst simulering av 28 dygn: sömn, gång, träningspass och datoranvändning styr puls, HRV,
SpO2, hudtemperatur och andning. Scenarierna i scenarier.py lägger till det som ska hittas
(pulsrusning, förkylning, syrefall, mätfel ...). Datan skrivs till en slängbar SQLite-fil under eval/tmp/.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import numpy as np

KALLA = "syntetisk"


def _ema(x: np.ndarray, upp: float, ner: float) -> np.ndarray:
    """Asymmetriskt glidande medel: pulsen stiger fortare än den sjunker."""
    y = np.empty_like(x)
    v = 0.0
    au, an = 1 / upp, 1 / ner
    for i, xi in enumerate(x):
        v += (xi - v) * (au if xi > v else an)
        y[i] = v
    return y


def _ar1(rng: np.random.Generator, n: int, phi: float, sd: float) -> np.ndarray:
    e = rng.normal(0, sd, n)
    y = np.empty(n)
    v = 0.0
    for i in range(n):
        v = phi * v + e[i]
        y[i] = v
    return y


class Sim:
    def __init__(self, nu: float, dagar: int = 28, fro: int = 1) -> None:
        self.nu = int(nu) // 60 * 60
        self.tz = time.localtime(nu).tm_gmtoff
        self.n = dagar * 1440
        self.dagar = dagar
        self.t = self.nu - (self.n - 1) * 60 + np.arange(self.n) * 60
        self.rng = np.random.default_rng(fro)
        self.idag = (self.nu + self.tz) // 86400
        self.sover = np.zeros(self.n, bool)
        self.steg = np.zeros(self.n)
        self.intens = np.zeros(self.n)
        self.dator = np.full(self.n, "", dtype=object)
        self.hr_add = np.zeros(self.n)
        self.hrv_fak = np.ones(self.n)
        self.temp_add = np.zeros(self.n)
        self.resp_add = np.zeros(self.n)
        self.spo2_add = np.zeros(self.n)
        self.hr_satt: dict[int, float] = {}        # artefakter: exakt värde på en minut
        self.bortfall = np.zeros(self.n, bool)     # klockan registrerar inget
        self.extra: dict[str, np.ndarray] = {}     # metric -> mask med extra mätningar i vaket tillstånd
        self.natter: list[dict[str, Any]] = []
        self.pass_: list[dict[str, Any]] = []
        self.journal: list[dict[str, Any]] = []
        self.labb: list[dict[str, Any]] = []

    # ------------------------------------------------------------ tid
    def ts(self, dag: int, minut: float) -> int:
        """dag = 0 idag, 1 igår ...; minut från lokal midnatt (negativ = kvällen innan)."""
        return int((self.idag - dag) * 86400 - self.tz + minut * 60)

    def idx(self, ts: float) -> int:
        return int(np.clip((ts - self.t[0]) // 60, 0, self.n))

    def span(self, a: float, b: float) -> slice:
        return slice(self.idx(a), self.idx(b))

    def datum(self, dag: int) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(self.ts(dag, 720)))

    # ------------------------------------------------------------ beteende
    def natt(self, dag: int, start_min: float, slut_min: float) -> None:
        a, b = self.ts(dag, start_min), self.ts(dag, slut_min)
        if a < self.t[0] or a >= self.nu:
            return
        b = min(b, self.nu)
        self.sover[self.span(a, b)] = True
        if b <= self.nu - 1800:  # bara avslutade nätter blir sömnpass
            self.natter.append({"start": a, "slut": b, "stages": self._faser(a, b)})

    def _faser(self, a: int, b: int) -> list[dict[str, Any]]:
        out, t, cyk = [], a, 0
        fas = lambda s, e, st: out.append({"start": int(s), "end": int(min(e, b)), "stage": st})
        fas(t, t + 12 * 60, "light")
        t += 12 * 60
        while t < b - 600:
            djup = max(8, 35 - cyk * 9) * 60
            rem = min(35, 10 + cyk * 7) * 60
            for st, d in (("light", 25 * 60), ("deep", djup), ("light", 12 * 60), ("rem", rem)):
                if t >= b:
                    break
                fas(t, t + d, st)
                t += d
            if self.rng.random() < 0.4 and t < b:
                fas(t, t + 4 * 60, "awake")
                t += 4 * 60
            cyk += 1
        if t < b:
            fas(t, b, "light")
        return [s for s in out if s["end"] > s["start"]]

    def gang(self, dag: int, start_min: float, minuter: float, takt: float = 105) -> None:
        s = self.span(self.ts(dag, start_min), self.ts(dag, start_min + minuter))
        n = s.stop - s.start
        if n > 0:
            self.steg[s] = np.clip(self.rng.normal(takt, 8, n), 0, None)

    def traning(self, dag: int, start_min: float, minuter: float, typ: str, intens: float = 0.85,
                takt: float = 0) -> None:
        a, b = self.ts(dag, start_min), self.ts(dag, start_min + minuter)
        s = self.span(a, b)
        n = s.stop - s.start
        if n <= 0:
            return
        self.intens[s] = np.clip(intens + self.rng.normal(0, 0.04, n), 0, 1)
        if takt:
            self.steg[s] = np.clip(self.rng.normal(takt, 6, n), 0, None)
        self.pass_.append({"id": f"pass-{a}", "start": a, "end": min(b, self.nu) if b <= self.nu else None, "typ": typ})

    def datorblock(self, dag: int, start_min: float, slut_min: float, kat: str) -> None:
        s = self.span(self.ts(dag, start_min), self.ts(dag, slut_min))
        self.dator[s] = kat

    def standard(self, fran_dag: int | None = None, till_dag: int = 0, lagg: float = -40, upp: float = 450,
                 steg_mal: float = 5500, kvall: str = "spel", kvall_tid: tuple[float, float] = (19 * 60, 23 * 60)) -> None:
        """Vanliga dygn: sömn ungefär 23:20-07:30, gång till och från skolan, datorn på kvällen."""
        fran_dag = self.dagar if fran_dag is None else fran_dag
        for d in range(fran_dag, till_dag - 1, -1):
            j = self.rng.normal(0, 18)
            self.natt(d, lagg + j, upp + self.rng.normal(0, 10))
            # gång: morgon, lunch, eftermiddag och resten slumpat
            bitar = [(upp + 25, 15), (12 * 60, 10), (16 * 60, 18)]
            kvar = steg_mal - sum(m for _, m in bitar) * 105
            while kvar > 0:
                st = self.rng.uniform(9 * 60, 18.5 * 60)
                m = self.rng.uniform(4, 15)
                bitar.append((st, m))
                kvar -= m * 105
            for st, m in bitar:
                self.gang(d, st + self.rng.normal(0, 8), m)
            self.datorblock(d, kvall_tid[0] + self.rng.normal(0, 15), kvall_tid[1] + self.rng.normal(0, 15), kvall)

    # ------------------------------------------------------------ fysiologi
    def generera(self) -> dict[str, list[tuple[float, float]]]:
        r = self.rng
        n = self.n
        last = _ema(self.intens, 2.0, 6.0)
        gang = _ema(np.clip(self.steg / 110, 0, 1.6), 1.5, 4.0)
        # nattlig variation per natt
        natt_id = np.cumsum(np.r_[0, np.diff(self.sover.astype(int)) == 1])
        nf = np.exp(r.normal(0, 0.07, natt_id.max() + 2))[natt_id]
        nt = r.normal(0, 0.12, natt_id.max() + 2)[natt_id]

        hr = np.where(self.sover, 56.0, 71.0) + _ar1(r, n, 0.85, 1.6) + r.normal(0, 1.2, n)
        hr += gang * 30 * np.clip(1 - last, 0, 1) + last * 98  # under pass styr intensiteten, inte stegen
        hr += np.where(self.dator == "spel", 3.0, 0.0)
        hr += self.hr_add
        hrv = np.where(self.sover, 56.0 * nf, 38.0) * np.exp(r.normal(0, 0.14, n))
        hrv = hrv / (1 + 3.2 * last + 0.9 * gang) * self.hrv_fak
        spo2 = np.where(self.sover, 96.3, 97.6) + r.normal(0, 0.7, n) + self.spo2_add
        spo2 = np.minimum(spo2, 100)
        temp = np.where(self.sover, 34.1 + nt, 32.6) + r.normal(0, 0.09, n) + self.temp_add
        resp = np.where(self.sover, 14.2, 16.0) + r.normal(0, 0.6, n) + self.resp_add

        alder = (self.nu - self.t) / 3600
        i = np.arange(n)
        ute = self.bortfall
        out: dict[str, list[tuple[float, float]]] = {}

        def ta(metric: str, mask: np.ndarray, varden: np.ndarray, dec: int) -> None:
            mask = mask & ~ute
            if metric in self.extra:
                mask = mask | (self.extra[metric] & ~ute)
            out[metric] = [(float(self.t[k]), round(float(varden[k]), dec)) for k in np.nonzero(mask)[0]]

        hr_mask = (alder < 48) | (i % 5 == 0)
        hr_v = hr.copy()
        for k, v in self.hr_satt.items():
            hr_v[k] = v
            hr_mask[k] = True
        ta("hr", hr_mask, hr_v, 0)
        ta("hrv_rmssd", (self.sover & (i % 5 == 0)) | (~self.sover & (i % 60 == 0)), hrv, 1)
        ta("spo2", self.sover & ((alder < 72) | (i % 5 == 0)), spo2, 0)
        ta("skin_temp", self.sover & (i % 5 == 0), temp, 2)
        ta("resp_rate", self.sover & (i % 5 == 0), resp, 1)
        out["steps"] = [(float(self.t[k]), float(round(self.steg[k]))) for k in np.nonzero((self.steg >= 1) & ~ute)[0]]
        for kat in ("kod", "spel", "chatt", "webb", "annat"):
            out[f"dator_{kat}"] = [(float(self.t[k]), 1.0) for k in np.nonzero(self.dator == kat)[0]]
        # vilopuls per natt: lägsta 10-minutersmedel, sparas vid uppvaknandet
        vp = []
        for nt_ in self.natter:
            s = self.span(nt_["start"], nt_["slut"])
            seg = hr[s]
            if len(seg) >= 10:
                vp.append((float(nt_["slut"]), round(float(np.convolve(seg, np.ones(10) / 10, "valid").min()), 0)))
        out["resting_hr"] = vp
        self._hr_sann = hr
        self._serier = out
        return out

    # ------------------------------------------------------------ skrivning
    def skriv(self, path: Path, schema: str) -> dict[str, int]:
        serier = getattr(self, "_serier", None) or self.generera()
        if path.exists():
            path.unlink()
        for suf in ("-wal", "-shm"):
            p = Path(str(path) + suf)
            if p.exists():
                p.unlink()
        con = sqlite3.connect(path)
        con.executescript(schema)
        antal = {}
        for metric, pts in serier.items():
            con.executemany("INSERT OR REPLACE INTO samples(ts, metric, value, source) VALUES (?,?,?,?)",
                            [(t, metric, v, KALLA) for t, v in pts])
            antal[metric] = len(pts)
        for nt in self.natter:
            con.execute("INSERT INTO sleep(id, start, end, stages, source) VALUES (?,?,?,?,?)",
                        (f"natt-{nt['start']}", nt["start"], nt["slut"], json.dumps(nt["stages"]), KALLA))
        for p in self.pass_:
            con.execute("INSERT INTO exercise(id, start, end, typ, source) VALUES (?,?,?,?,?)",
                        (p["id"], p["start"], p["end"], p["typ"], KALLA))
        for j in self.journal:
            jid = hashlib.sha1(json.dumps(j, sort_keys=True).encode()).hexdigest()[:10]
            con.execute("INSERT INTO journal(id, date, unit, author, kind, title, text, fetched) VALUES (?,?,?,?,?,?,?,?)",
                        (jid, j["date"], j.get("unit", "Vårdcentralen (syntetisk testdata)"), j.get("author", "Läkare"),
                         j.get("kind", "anteckning"), j["title"], j["text"], self.nu))
        for lb in self.labb:
            lid = hashlib.sha1(json.dumps(lb, sort_keys=True).encode()).hexdigest()[:10]
            con.execute("INSERT INTO labs(id, date, analyte, value, value_raw, unit, ref_low, ref_high, flag, fetched) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (lid, lb["date"], lb["analyt"], lb["varde"], lb.get("raw", f"{lb['varde']:g}".replace(".", ",")),
                         lb["enhet"], lb.get("lag"), lb.get("hog"), lb.get("flagga"), self.nu))
        con.commit()
        con.close()
        antal["natter"], antal["pass"], antal["journal"], antal["labb"] = (len(self.natter), len(self.pass_),
                                                                           len(self.journal), len(self.labb))
        return antal

    # ------------------------------------------------------------ hjälp för utlösare
    def hr_median(self, minuter: int) -> float:
        return float(np.median(self._hr_sann[-minuter:]))

    def standardprover(self, dagar_sedan: int = 240) -> None:
        d = self.datum(dagar_sedan)
        for analyt, v, enh, lo, hi in (("Hb", 148, "g/L", 134, 170), ("Ferritin", 72, "µg/L", 15, 150),
                                       ("TSH", 1.6, "mIE/L", 0.4, 4.0), ("CRP", 1, "mg/L", None, 5)):
            self.labb.append({"date": d, "analyt": analyt, "varde": v, "enhet": enh, "lag": lo, "hog": hi,
                              "raw": "<1" if analyt == "CRP" else None})
        for lb in self.labb:
            if lb.get("raw") is None:
                lb.pop("raw")
        self.journal.append({"date": d, "kind": "anteckning", "title": "Hälsobesök",
                             "author": "Skolsköterska",
                             "text": "Hälsosamtal. Frisk, inga mediciner, inga kända allergier. Blodprover tagna, normala."})
