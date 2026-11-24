"""Räknar om poängen i alla resultatfiler från de sparade körningarna (när poängsättningen ändrats)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HIT = Path(__file__).resolve().parent
sys.path.insert(0, str(HIT))
from poang import poang, sammanstall  # noqa: E402

for f in sorted((HIT / "resultat").glob("*.json")):
    d = json.loads(f.read_text())
    rader = []
    for gammal, k in zip(d["rader"], d["korningar"]):
        ny = {"scenario": k["scenario"], **poang(k)}
        for behall in ("domare", "ollama_minne_gib_efter"):
            if behall in gammal:
                ny[behall] = gammal[behall]
        rader.append(ny)
    d["rader"], d["sammanfattning"] = rader, sammanstall(rader)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str))
    print(f.name, d["sammanfattning"]["baslinjefel"], d["sammanfattning"]["tackning"])
subprocess.run([sys.executable, str(HIT / "rapport.py")])
