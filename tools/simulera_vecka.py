"""Simulerar testveckan minut för minut och räknar notiser per dag, före och efter (docs/ANVANDBARHET.md).

SYNTETISK TESTDATA i en engångsdatabas (tools/syntetisk_person.py). Rör aldrig ~/.konsiliet.

  cd server && uv run python ../tools/simulera_vecka.py [--json ut.json]

Före = reglerna som de var i git före användbarhetsarbetet:
  - AFK-knuffen var 90:e minut 08-23 så länge klockan bars och stegen var under 150 (rutiner.stillasittande),
    utan snooze, utan hänsyn till spel eller pass. Mobilen visade den och skickade den vidare till klockan.
  - POST-skärmen kl. 07:30 varje dag, oavsett om man sov.
  - Varje avvikelse från vakten (den gamla vakten, även lägre puls än vanligt) gav tre notiser: avvikelsen,
    "Ny tråd startad" och lösningen. Egna frågor och söndagens veckotråd gav två (start och lösning).
Efter = vardag.tick() varje minut med budget, tysta timmar, snooze och fokusläge, POST-skärmen när natten
är slut, en notis per tråd (uppdateras på plats), veckotråden tyst om den inte hittar något för vården.

Personens svar på knuffarna är manus (samma i båda fallen där det går): se SVAR nedan.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import types
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROT / "tools"))
TMP = tempfile.mkdtemp(prefix="kropp64-sim-")
os.environ["KONSILIET_DB"] = os.path.join(TMP, "sim.db")
os.environ["KONSILIET_TILLAT_EMULATOR"] = "1"

import syntetisk_person as person  # noqa: E402
from konsiliet import db, vakt, vardag  # noqa: E402


def gammal_vakt() -> types.ModuleType:
    """Vakten som den var före ändringarna (git), för att räkna hur många trådar den gamla startade."""
    src = subprocess.run(["git", "-C", str(ROT), "show", "9bd0016:server/src/konsiliet/vakt.py"],
                         capture_output=True, text=True, check=True).stdout
    spec = importlib.util.spec_from_loader("konsiliet.vakt_fore", loader=None)
    m = importlib.util.module_from_spec(spec)
    m.__package__ = "konsiliet"
    sys.modules["konsiliet.vakt_fore"] = m
    exec(compile(src, "vakt_fore.py", "exec"), m.__dict__)
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    nu_real = time.time()
    g = person.generera(nu_real)
    db.insert_samples([(t, m, v, person.KALLA) for t, m, v in g["samples"]])
    with db.tx() as c:
        for s in g["sleep"]:
            c.execute("INSERT INTO sleep VALUES (?,?,?,?,?)", (s["id"], s["start"], s["end"], json.dumps(s["stages"]), s["source"]))
        for e in g["exercise"]:
            c.execute("INSERT INTO exercise VALUES (?,?,?,?,?)", (e["id"], e["start"], e["end"], e["typ"], e["source"]))
    v0 = person.veckostart(nu_real)
    t0, t1 = v0.timestamp(), (v0 + timedelta(days=7)).timestamp()
    dag = lambda ts: datetime.fromtimestamp(ts).strftime("%a %d/%m")
    fore: dict[str, list[str]] = defaultdict(list)
    efter: dict[str, list[str]] = defaultdict(list)
    vakna_fore: list[str] = []

    # ---------------- före
    senast = 0.0
    for m in range(int(t0 // 60), int(t1 // 60)):
        nu = m * 60.0
        h = datetime.fromtimestamp(nu).hour
        if h == 7 and datetime.fromtimestamp(nu).minute == 30:
            fore[dag(nu)].append("POST-skärmen 07:30")
            if any(s["start"] <= nu <= s["end"] for s in g["sleep"]):
                vakna_fore.append(dag(nu))
        if 8 <= h < 23 and nu - senast >= 90 * 60:
            start = nu - 90 * 60
            if len(db.query_samples("hr", start, nu)) >= 30 and sum(v for _, v in db.query_samples("steps", start, nu)) < 150:
                senast = nu
                fore[dag(nu)].append("AFK (mobil + klocka)")
    gv = gammal_vakt()
    fynd_fore = []
    for k in range(int(t0 // 600), int(t1 // 600)):
        for f in gv._evaluate(k * 600.0):
            fynd_fore.append((k * 600.0, f.rule, f.title))
            fore[dag(k * 600.0)] += ["avvikelse", "Ny tråd startad", "lösning"]
    fraga = (v0 + timedelta(days=5, hours=11)).timestamp()
    vecko = (v0 + timedelta(days=6, hours=19)).timestamp()
    fore[dag(fraga)] += ["Ny tråd startad (egen fråga)", "lösning (egen fråga)"]
    fore[dag(vecko)] += ["Ny tråd startad (veckan)", "lösning (veckan)"]

    # ---------------- efter
    with db.tx() as c:
        c.execute("DELETE FROM vakt_state")
    pub: list[tuple[float, str, dict]] = []
    klocka = {"nu": t0}
    vardag.publicera = lambda kind, p: pub.append((klocka["nu"], kind, p))
    # Manus: hur personen svarar (bara möjligt efter ändringarna).
    SVAR = {(1, 21): ("afk", "fokus", 120), (0, 14): ("afk", "snooze", 30), (1, 23): ("stress", "andas", None)}
    besvarade = set()
    slut = {e["end"]: e["id"] for e in g["exercise"]}
    fynd_efter = []
    for m in range(int(t0 // 60), int(t1 // 60)):
        nu = m * 60.0
        klocka["nu"] = nu
        n0 = len(pub)
        vardag.tick(nu, med_llm=False)
        for ts, pid in slut.items():
            if ts <= nu < ts + 60:
                vardag.efter_pass(pid, nu)
        if m % 10 == 0:
            for f in vakt._evaluate(nu):
                fynd_efter.append((nu, f.rule, f.title))
                historik = bool(f.window) and nu - f.window[1] > vakt.HISTORIK_S
                if not historik and vakt.trad_tillats(f, nu):
                    efter[dag(nu)].append(f"tråd: {f.title}")
        for ts, kind, p in pub[n0:]:
            efter[dag(ts)].append(f"{kind}: {p.get('title') or p.get('rubrik') or ''}")
            d = datetime.fromtimestamp(ts)
            key = ((d - v0).days, d.hour)
            if key in SVAR and key not in besvarade and kind.startswith("nudge"):
                besvarade.add(key)
                typ, svar, mi = SVAR[key]
                vardag.svara(typ, svar, mi, nu)
                efter[dag(ts)][-1] += f" -> svar: {svar}"
    efter[dag(fraga)].append("tråd: egen fråga (en notis när lösningen kommer, snabbsvaret syns i appen)")
    efter[dag(vecko)].append("tråd: veckan (tyst om inget ska tas upp med vården)")

    dagar_ = [dag((v0 + timedelta(days=i)).timestamp()) for i in range(7)]
    rad = lambda d, x: len([y for y in x.get(d, []) if not y.startswith("tråd: veckan")])
    tabell = [{"dag": d, "fore": len(fore.get(d, [])), "efter": rad(d, efter)} for d in dagar_]
    ut = {"vecka": dagar_[0], "tabell": tabell, "summa_fore": sum(r["fore"] for r in tabell),
          "summa_efter": sum(r["efter"] for r in tabell), "fore": fore, "efter": efter,
          "post_medan_personen_sov_fore": vakna_fore, "fynd_fore": fynd_fore, "fynd_efter": fynd_efter,
          "stoppade_efter": vardag.notis_statistik(t1 - 1, 7)}
    for r in tabell:
        print(f"{r['dag']:<10} före {r['fore']:>2}  efter {r['efter']:>2}")
    print(f"summa      före {ut['summa_fore']:>2}  efter {ut['summa_efter']:>2}")
    print("POST-skärmen medan personen sov (före):", ", ".join(vakna_fore) or "ingen")
    for d in dagar_:
        print(f"\n{d}\n  före:  " + "\n         ".join(fore.get(d, []) or ["-"]) + "\n  efter: " + "\n         ".join(efter.get(d, []) or ["-"]))
    if a.json:
        Path(a.json).write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
