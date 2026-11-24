"""Kör utvärderingen: alla (eller valda) scenarier mot en variant av konsiliet, poängsätter och sparar.

    cd server && .venv/bin/python ../eval/kor.py <variant> [--src <sökväg till src>] [--bara id,id] [--env K=V ...]

Resultat: eval/resultat/<datum>-<variant>.json och en uppdaterad eval/RESULTAT.md.
All data är syntetisk och ligger i slängbara databaser under eval/tmp/ (gitignorerade).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HIT = Path(__file__).resolve().parent
sys.path.insert(0, str(HIT))

from poang import poang, sammanstall  # noqa: E402
from scenarier import HOLDOUT, SCENARIER  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant")
    ap.add_argument("--src", default=str(HIT.parent / "server" / "src"))
    ap.add_argument("--bara", default="")
    ap.add_argument("--env", nargs="*", default=[])
    ap.add_argument("--beskrivning", default="")
    ap.add_argument("--holdout", action="store_true", help="kör holdout-scenarierna i stället")
    a = ap.parse_args()

    alla = HOLDOUT if a.holdout else SCENARIER
    valda = [s for s in alla if not a.bara or s.id in a.bara.split(",")]
    env = {**os.environ, **dict(kv.split("=", 1) for kv in a.env)}
    env.pop("KONSILIET_DB", None)
    (HIT / "tmp").mkdir(exist_ok=True)
    (HIT / "resultat").mkdir(exist_ok=True)
    datum = time.strftime("%Y-%m-%d")
    ut = HIT / "resultat" / f"{datum}-{a.variant}.json"
    rader, korningar = [], []
    for sc in valda:
        fil = HIT / "tmp" / f"{a.variant}-{sc.id}.json"
        t0 = time.time()
        p = subprocess.run([sys.executable, str(HIT / "kor_ett.py"), sc.id, str(fil), "--src", a.src,
                            "--variant", a.variant], env=env, capture_output=True, text=True)
        if p.returncode != 0 or not fil.exists():
            print(f"{sc.id}: PROCESSFEL\n{p.stderr[-2000:]}", flush=True)
            continue
        res = json.loads(fil.read_text())
        pg = poang(res)
        rader.append({"scenario": sc.id, **pg})
        korningar.append(res)
        print(f"{sc.id:20s} {pg['bradska'] or '-':18s} facit {pg['facit']:18s} "
              f"{'OK ' if pg['godtagbar'] else 'FEL'} täckning {pg['tackning']:.2f} stryk {pg['strykningar']}/"
              f"{pg['pastaenden']} belagda {pg['belagda']} {res['sekunder']:.0f}s "
              f"{'vakt' if res['utlosare_fran_vakt'] else ''}{' KRASCH' if res.get('fel') else ''}"
              f" ({time.time() - t0:.0f}s)", flush=True)
        # spara löpande så att en avbruten körning inte går förlorad
        ut.write_text(json.dumps({"variant": a.variant, "datum": datum, "beskrivning": a.beskrivning,
                                  "env": dict(kv.split("=", 1) for kv in a.env), "src": a.src,
                                  "sammanfattning": sammanstall(rader), "rader": rader, "korningar": korningar},
                                 ensure_ascii=False, indent=1, default=str))
    print(json.dumps(sammanstall(rader), ensure_ascii=False, indent=1))
    subprocess.run([sys.executable, str(HIT / "rapport.py")])


if __name__ == "__main__":
    main()
