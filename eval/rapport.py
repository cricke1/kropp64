"""Skriver eval/RESULTAT.md från alla körningar i eval/resultat/."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HIT = Path(__file__).resolve().parent
sys.path.insert(0, str(HIT))
from scenarier import HOLDOUT, HOLDOUT2, HOLDOUT3, HOLDOUT4, SCENARIER  # noqa: E402


def main() -> None:
    def ordning(p: Path) -> tuple[int, int, float]:
        n = p.stem
        grupp = 4 if "holdout4" in n else 3 if "holdout3" in n else 2 if "holdout2" in n else 1 if "holdout" in n else 0
        return (grupp, 0 if n.endswith("baslinje") else 1, p.stat().st_mtime)
    filer = sorted((HIT / "resultat").glob("*.json"), key=ordning)
    data = [json.loads(f.read_text()) for f in filer]
    data = [d for d in data if d.get("rader")]
    rad = ["# Utvärdering av konsiliet", "",
           "Genereras av `eval/rapport.py`. 15 scenarier med syntetisk data och känt facit (se `eval/scenarier.py`).",
           "Brådska godtagbar = inom facits godtagbara nivåer. Täckning = andel måste-fynd i slutbedömningen.",
           "Förbjudna = påståenden som inte får göras (utan negation). Strykandel = granskarens strykningar / specialistpåståenden.",
           "Overifierade = siffror i slutbedömningens egen text som inte finns i någon hämtad källa.",
           "Baslinjefel = meningar som kallar en siffra baslinje fast den inte är ett baslinjevärde.", "",
           "Mac mini M4 16 GB, Ollama, en förfrågan i taget.", "",
           "| Variant | n | Brådska godtagbar | Exakt | Över/under | Täckning | Förbjudna | Strykandel | Belagda/möte | "
           "Overifierade | Baslinjefel | Sek median (max) | Prompt-/ut-tokens | Domare |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in data:
        s = d["sammanfattning"]
        sa = "-" if s["strykandel"] is None else f"{s['strykandel']:.0%}"
        rad.append(f"| {d['datum']} {d['variant']} | {s['n']} | {s['bradska_godtagbar']:.0%} | {s['bradska_exakt']:.0%} | "
                   f"{s['overtriage']}/{s['undertriage']} | {s['tackning']:.0%} | {s['forbjudna']} | "
                   f"{sa} | "
                   f"{s['belagda_medel']} | {s['overifierade_siffror']} | {s['baslinjefel']} | "
                   f"{s['sek_median']:.0f} ({s['sek_max']:.0f}) | {s['prompt_tokens_medel']}/{s['ut_tokens_medel']} | "
                   f"{s.get('domare_medel', '-')} |")
    rad += ["", "## Varianter", ""]
    for d in data:
        rad.append(f"- **{d['datum']} {d['variant']}**: {d.get('beskrivning') or ''} "
                   f"{('`' + ' '.join(f'{k}={v}' for k, v in d['env'].items()) + '`') if d.get('env') else ''}")
    rad += ["", "## Per scenario (brådska, täckning)", "",
            "| Scenario | Facit | " + " | ".join(d["variant"] for d in data) + " |",
            "|---|---|" + "---|" * len(data)]
    for sc in SCENARIER + HOLDOUT + HOLDOUT2 + HOLDOUT3 + HOLDOUT4:
        celler = []
        for d in data:
            r = next((x for x in d["rader"] if x["scenario"] == sc.id), None)
            celler.append("-" if not r else f"{'ok' if r['godtagbar'] else 'FEL'} {r['bradska'] or '?'} {r['tackning']:.0%}")
        rad.append(f"| {sc.id} | {sc.facit.bradska} | " + " | ".join(celler) + " |")
    (HIT / "RESULTAT.md").write_text("\n".join(rad) + "\n")


if __name__ == "__main__":
    main()
