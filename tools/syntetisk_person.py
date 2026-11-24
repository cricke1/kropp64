"""SYNTETISK TESTDATA: en påhittad 18-åring under fem veckor, för användbarhetstestet (docs/ANVANDBARHET.md).

Inget här är uppmätt på en människa. Alla punkter får källan "syntetisk-vecka" så att de syns som testdata
i appen och webben och kan raderas. Används av:
  tools/fyll_testserver.py   skickar datan till en SEPARAT testserver över HTTP
  tools/simulera_vecka.py    kör vakten och knuffarna minut för minut i en engångsdatabas

Personen: sitter mycket inne, kodar på eftermiddagen och spelar på kvällen, vill börja träna. 28 dagar
vardag utan träning (baslinjen, som Health Connect läser bakåt vid första installationen), sedan testveckan
måndag-söndag och dagarna fram till nu:

  mån  installation, kodpass 13-17 (AFK), spel till 00:30
  tis  sen spelkväll till 02:40 med en stressig match 23:00-23:40 (hög puls vid datorn)
  ons  passdag: sov till 09:40, löppass 30 min 17:40, kod på kvällen
  tor  dålig natt: spel till 03:05, upp 07:10 (3 h 50 min sömn)
  fre  natten mot lördag: förhöjd vilopuls, låg HRV och hudtemperatur +1,2 °C (vakten startar en tråd)
  lör  passdag men trött: frågar teamet "varför är jag så trött idag?"
  sön  promenadpass 30 min, veckosammanfattning 19:00
  mån  bra natt, löppass 32 min i zon 2
  tis  i dag
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

KALLA = "syntetisk-vecka"


def _ts(d: datetime, h: float) -> float:
    return (d + timedelta(hours=h)).timestamp()


def veckostart(nu: float) -> datetime:
    idag = datetime.fromtimestamp(nu).replace(hour=0, minute=0, second=0, microsecond=0)
    return idag - timedelta(days=idag.weekday() + 7)


def dagar(nu: float) -> list[dict]:
    """En post per dygn: sömnen som SLUTAR den morgonen, datorblock, pass och promenader."""
    rnd = random.Random(7)
    v0 = veckostart(nu)
    start = v0 - timedelta(days=28)
    idag = datetime.fromtimestamp(nu).replace(hour=0, minute=0, second=0, microsecond=0)
    ut = []
    d = start
    while d <= idag:
        helg = d.weekday() >= 5
        dag = {"datum": d, "dator": [], "pass": [], "promenad": [], "sjuk": False, "stress": None}
        # sömnen som slutar den här morgonen (start räknas från midnatt, negativ = kvällen innan)
        if helg:
            dag["somn"] = (1.4 + rnd.uniform(-0.3, 0.4), 9.8 + rnd.uniform(-0.4, 0.4))
            dag["dator"] = [("spel", 13.0, 16.5), ("webb", 17.0, 17.5), ("kod", 20.0, 24.4)]
        else:
            dag["somn"] = (0.4 + rnd.uniform(-0.3, 0.4), 7.4 + rnd.uniform(-0.1, 0.2))
            dag["dator"] = [("kod", 16.0, 18.5), ("chatt", 19.0, 19.5), ("spel", 20.0, 24.2)]
            dag["promenad"] = [(7.75, 25), (15.4, 20)]
        dagnr = (d - v0).days
        if dagnr == 0:      # mån: installation, kodpass 13-17 utan rast
            dag["dator"] = [("kod", 13.0, 17.0), ("chatt", 17.0, 17.4), ("spel", 20.0, 24.5)]
            dag["promenad"] = [(7.75, 25)]
        elif dagnr == 1:    # tis: sen spelkväll med stressig match
            dag["dator"] = [("kod", 16.0, 18.5), ("spel", 20.0, 26.67)]
            dag["stress"] = (23.0, 23.67)
        elif dagnr == 2:    # ons: sov länge efter spelkvällen, löppass
            dag["somn"] = (2.92, 9.67)
            dag["promenad"] = []
            dag["pass"] = [("löpning", 17.67, 30, (118, 142))]
            dag["dator"] = [("kod", 12.0, 16.5), ("kod", 19.5, 24.0), ("spel", 24.0, 27.08)]
        elif dagnr == 3:    # tor: dålig natt (spel till 03:05, upp 07:10)
            dag["somn"] = (3.33, 7.17)
            dag["dator"] = [("kod", 16.0, 18.5), ("spel", 20.0, 24.6)]
        elif dagnr == 4:    # fre
            dag["dator"] = [("kod", 16.0, 18.0), ("spel", 20.0, 24.6)]
        elif dagnr == 5:    # lör: natten var sjuk
            dag["somn"] = (0.67, 9.5)
            dag["sjuk"] = True
            dag["dator"] = [("webb", 11.0, 12.0), ("spel", 14.0, 16.0), ("kod", 20.0, 23.5)]
        elif dagnr == 6:    # sön: promenadpass
            dag["pass"] = [("promenad", 14.0, 30, (98, 112))]
            dag["dator"] = [("kod", 16.0, 18.0), ("spel", 19.5, 23.2)]
        elif dagnr == 7:    # mån: bra natt, löppass i zon 2
            dag["somn"] = (-0.25, 7.75)
            dag["pass"] = [("löpning", 17.58, 32, (120, 134))]
            dag["dator"] = [("kod", 15.0, 17.0), ("spel", 20.0, 23.0)]
        elif dagnr == 8:    # tis (i dag)
            dag["somn"] = (0.17, 7.5)
            dag["dator"] = [("kod", 15.5, 18.0), ("spel", 20.0, 24.0)]
        ut.append(dag)
        d += timedelta(days=1)
    return ut


def generera(nu: float) -> dict:
    """Mätpunkter, sömnpass och träningspass fram till nu. Returnerar {samples, sleep, exercise}."""
    rnd = random.Random(42)
    dd = dagar(nu)
    samples: list[tuple[float, str, float]] = []
    sleep: list[dict] = []
    exercise: list[dict] = []
    # tillstånd per minut: sover, dator-kategori, promenad, pass
    sover: set[int] = set()
    sjuk: set[int] = set()
    dator: dict[int, str] = {}
    stress: set[int] = set()
    gang: set[int] = set()
    pass_min: dict[int, tuple[float, float]] = {}
    for dag in dd:
        d = dag["datum"]
        a, b = _ts(d, dag["somn"][0]), _ts(d, dag["somn"][1])
        if b > nu:
            continue
        stages, t = [], a
        while t < b:
            # 90-minuterscykler: lätt, djup, lätt, rem, med en kort vaken stund ibland
            for st, m in (("light", 25), ("deep", 25 if t - a < 4 * 3600 else 10), ("light", 20), ("rem", 20)):
                e = min(b, t + m * 60)
                if t < e:
                    stages.append({"start": t, "end": e, "stage": st})
                t = e
            if rnd.random() < 0.25 and t < b:
                e = min(b, t + 4 * 60)
                stages.append({"start": t, "end": e, "stage": "awake"})
                t = e
        sleep.append({"id": f"syn-{d:%Y%m%d}", "start": a, "end": b, "stages": stages, "source": KALLA})
        for m in range(int(a // 60), int(b // 60)):
            sover.add(m)
            if dag["sjuk"]:
                sjuk.add(m)
    for dag in dd:
        d = dag["datum"]
        for kat, h0, h1 in dag["dator"]:
            for m in range(int(_ts(d, h0) // 60), int(min(nu, _ts(d, h1)) // 60)):
                if m not in sover:
                    dator[m] = kat
        if dag["stress"]:
            for m in range(int(_ts(d, dag["stress"][0]) // 60), int(_ts(d, dag["stress"][1]) // 60)):
                stress.add(m)
        for h0, mins in dag["promenad"]:
            for m in range(int(_ts(d, h0) // 60), int(_ts(d, h0) // 60) + mins):
                gang.add(m)
        for i, (typ, h0, mins, (lo, hi)) in enumerate(dag["pass"]):
            s0 = _ts(d, h0)
            if s0 + mins * 60 > nu:
                continue
            exercise.append({"id": f"syn-pass-{d:%Y%m%d}-{i}", "start": s0, "end": s0 + mins * 60, "typ": typ, "source": KALLA})
            for m in range(int(s0 // 60), int(s0 // 60) + mins):
                pass_min[m] = (lo, hi, 110 if typ == "promenad" else 160)
                dator.pop(m, None)

    t0 = (dd[0]["datum"]).timestamp()
    for m in range(int(t0 // 60), int(nu // 60)):
        ts = m * 60.0
        h = datetime.fromtimestamp(ts).hour
        if m in pass_min:
            lo, hi, stegtakt = pass_min[m]
            # under passet: puls var 5:e sekund (träningsläget), uppvärmning de första 5 minuterna
            start = min(k for k in range(m - 60, m + 1) if k in pass_min)
            upp = min(1.0, (m - start) / 5)
            for s in range(0, 60, 5):
                v = 95 + upp * ((lo + hi) / 2 - 95) + (hi - lo) / 2 * math.sin((m - start) / 4 + s / 60) + rnd.gauss(0, 3)
                samples.append((ts + s, "hr", round(v)))
            samples.append((ts, "steps", round(stegtakt + rnd.gauss(0, 8))))
            continue
        if m in sover:
            bas = 54 + 3 * math.sin(m / 50)
            hr = bas + (14 if m in sjuk else 0) + rnd.gauss(0, 2)
            samples.append((ts, "hr", round(hr)))
            if m % 5 == 0:
                samples.append((ts, "hrv_rmssd", round(max(12, rnd.gauss(34 if m in sjuk else 56, 7)))))
            if m % 10 == 0:
                samples.append((ts, "spo2", round(min(100, rnd.gauss(96, 0.8)))))
                samples.append((ts, "resp_rate", round(rnd.gauss(15.5 if m in sjuk else 13.8, 0.6), 1)))
            continue
        if m in gang:
            samples.append((ts, "hr", round(rnd.gauss(98, 4))))
            samples.append((ts, "steps", round(rnd.gauss(105, 8))))
            continue
        kat = dator.get(m)
        if kat:
            samples.append((ts, f"dator_{kat}", 1.0))
            base = {"kod": 71, "spel": 79, "chatt": 70, "webb": 69, "annat": 70}[kat]
            hr = 104 if m in stress else base
            samples.append((ts, "hr", round(hr + rnd.gauss(0, 3))))
            if rnd.random() < 0.02:
                samples.append((ts, "steps", round(rnd.uniform(5, 25))))
            continue
        # vaken, inte vid datorn: lite rörelse i hemmet
        samples.append((ts, "hr", round(rnd.gauss(74 if 7 <= h < 23 else 66, 4))))
        if rnd.random() < 0.3:
            samples.append((ts, "steps", round(rnd.uniform(5, 40))))
    # hudtemperatur mot klockans baslinje (Health Connect), tre värden per natt
    for s in sleep:
        sj = datetime.fromtimestamp(s["end"]).date() == (veckostart(nu) + timedelta(days=5)).date()
        for k in range(3):
            samples.append((s["start"] + (k + 1) * (s["end"] - s["start"]) / 4, "skin_temp_delta",
                            round((1.2 if sj else 0.0) + rnd.gauss(0, 0.12), 2)))
    return {"samples": samples, "sleep": sleep, "exercise": exercise}
