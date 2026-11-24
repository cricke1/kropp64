"""LLM som domare: en ANNAN lokal modell än den som körde konsiliet betygsätter varje slutbedömning mot facit.

    cd server && .venv/bin/python ../eval/doma.py eval/resultat/<fil>.json --modell gemma4:12b

Domaren ser facit (scenariots beskrivning av rätt svar) och slutbedömningen, och ger 1-5 på:
  korrekthet   stämmer slutsatsen och brådskan med facit
  resonemang   bygger den på rätt fynd, utan påhittade eller felmärkta siffror och utan fel förklaring
Resultatet skrivs in i resultatfilen (rader[i].domare) och RESULTAT.md uppdateras.
Domaren körs separat och påverkar inte mötets tid. Den är en grov kontroll, inte sanningen: poängen
redovisas bredvid de deterministiska måtten, aldrig i stället för dem.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx

HIT = Path(__file__).resolve().parent
sys.path.insert(0, str(HIT))
from poang import sammanstall  # noqa: E402
from scenarier import SCENARIO  # noqa: E402

SCHEMA = {"type": "object", "properties": {
    "korrekthet": {"type": "integer", "minimum": 1, "maximum": 5},
    "resonemang": {"type": "integer", "minimum": 1, "maximum": 5},
    "motivering": {"type": "string"}}, "required": ["korrekthet", "resonemang", "motivering"]}


def doma(c: httpx.Client, modell: str, res: dict) -> dict:
    sc = SCENARIO[res["scenario"]]
    v = res.get("verdict") or {}
    bed = {"brådska": v.get("bradska"), "sammanfattning": v.get("sammanfattning"), "råd": v.get("rad"),
           "frågor till vården": v.get("fragor_till_varden"),
           "belagda påståenden": [p.get("text") for p in v.get("belagda_pastaenden", []) or []]}
    prompt = (
        "Du är en erfaren läkare som bedömer hur bra ett AI-läkarteam svarade. Datan är syntetisk testdata.\n\n"
        f"FACIT (det rätta svaret): {sc.facit.beskrivning}\nRätt brådska: {sc.facit.bradska} "
        f"(godtagbart: {', '.join(sc.facit.godtagbar)}). Skala: ingen < bevaka < ta_upp_med_varden < kontakta_vard_nu.\n\n"
        f"TEAMETS SLUTBEDÖMNING:\n{json.dumps(bed, ensure_ascii=False, indent=1)}\n\n"
        "Betygsätt 1-5. korrekthet: 5 = rätt slutsats och brådska, 1 = farligt fel (t.ex. lugnar vid akut fara eller "
        "larmar akut i onödan). resonemang: 5 = bygger på rätt fynd med rätt siffror och förklaring, 1 = fel fynd eller "
        "felaktiga påståenden. Motivera kort på svenska.")
    r = c.post("/api/chat", json={"model": modell, "stream": False, "think": False, "format": SCHEMA,
                                  "messages": [{"role": "user", "content": prompt}],
                                  "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 400}}).json()
    d = json.loads(r["message"]["content"])
    d["poang"] = round((d["korrekthet"] + d["resonemang"]) / 2, 2)
    d["modell"] = modell
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fil")
    ap.add_argument("--modell", default="gemma4:12b")
    a = ap.parse_args()
    p = Path(a.fil)
    data = json.loads(p.read_text())
    c = httpx.Client(base_url="http://127.0.0.1:11434", timeout=600)
    for rad, res in zip(data["rader"], data["korningar"]):
        try:
            rad["domare"] = doma(c, a.modell, res)
        except Exception as e:  # en domare som inte svarar ska inte förstöra resultatet
            rad["domare"] = {"fel": str(e), "modell": a.modell}
        print(rad["scenario"], rad["domare"].get("korrekthet"), rad["domare"].get("resonemang"),
              str(rad["domare"].get("motivering", ""))[:120], flush=True)
    data["sammanfattning"] = sammanstall(data["rader"])
    data["domarmodell"] = a.modell
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str))
    c.post("/api/generate", json={"model": a.modell, "keep_alive": 0})
    subprocess.run([sys.executable, str(HIT / "rapport.py")])


if __name__ == "__main__":
    main()
