"""Skriver eval/RESULTAT.md från alla körningar i eval/resultat/."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HIT = Path(__file__).resolve().parent
sys.path.insert(0, str(HIT))
from scenarier import HOLDOUT, HOLDOUT2, HOLDOUT3, HOLDOUT4, HOLDOUT5, SCENARIER  # noqa: E402


def main() -> None:
    def ordning(p: Path) -> tuple[int, int, float]:
        n = p.stem
        grupp = 5 if "holdout5" in n else 4 if "holdout4" in n else 3 if "holdout3" in n else 2 if "holdout2" in n else 1 if "holdout" in n else 0
        return (grupp, 0 if n.endswith("baslinje") else 1, p.stat().st_mtime)
    filer = sorted((HIT / "resultat").glob("*.json"), key=ordning)
    data = [json.loads(f.read_text()) for f in filer]
    data = [d for d in data if d.get("rader")]
    def agg(*monster: str) -> dict:
        from poang import sammanstall
        rader = [r for m in monster for f in sorted((HIT / "resultat").glob(m)) for r in json.loads(f.read_text())["rader"]]
        return sammanstall(rader) if rader else {}

    slut = [("Gamla pipelinen, 16 tränade scenarier", agg("2026-11-24-baslinje.json")),
            ("Nuvarande (v8), 16 tränade scenarier", agg("2026-11-2?-v8.json")),
            ("Gamla pipelinen, 16 holdout-scenarier", agg("*holdout*-baslinje.json")),
            ("Nuvarande (v8), 16 holdout-scenarier", agg("*holdout*-v8.json")),
            ("v8, tränade, 4 körningar sammanslagna", agg("2026-11-2?-v8.json", "2026-11-2?-v8-rep*.json")),
            ("v8, holdout, alla omkörningar sammanslagna", agg("*holdout*-v8.json", "*holdout*-v8-final.json",
                                                              "*holdout5-v8-rep*.json")),
            ("v8 med gemma4:12b, 16 holdout-scenarier", agg("*holdout*-v8-gemma12b.json")),
            ("v8 med gemma4:e4b, 16 holdout-scenarier", agg("*holdout*-v8-gemma4e4b.json"))]
    topp = ["# Utvärdering av konsiliet", "",
            "## Slutsiffran", "",
            "| Körning | n | Godtagbar brådska | Exakt | Över-/undertriage | Täckning av måste-fynd | Strykandel | "
            "Median s (max) | Utdatatokens/möte |", "|---|---|---|---|---|---|---|---|---|"]
    for namn, s_ in slut:
        if s_:
            topp.append(f"| {namn} | {s_['n']} | {s_['bradska_godtagbar']:.0%} | {s_['bradska_exakt']:.0%} | "
                        f"{s_['overtriage']}/{s_['undertriage']} | {s_['tackning']:.0%} | "
                        f"{s_['strykandel']:.0%} | {s_['sek_median']:.0f} ({s_['sek_max']:.0f}) | {s_['ut_tokens_medel']} |")
    topp += ["",
             "## Modellval", "",
             "qwen3.5:9b är kvar som modell. Samma v8 och samma 16 holdout-scenarier med gemma4:12b: samma brådska "
             "(16 av 16 godtagbara, 14 exakta mot 16, de två andra ett steg högre), bättre täckning (98 % mot 94 %) och "
             "klart bättre källdisciplin (granskaren strök 5 % mot 16 %), men median 156 s mot 118 s och 12,3 GiB i "
             "Ollama mot 8,4 GiB. Med gemma4:12b nådde swappen 10,8 GB och disken 8 GB ledigt. Den här datorn delas "
             "med röst, webb och vakt, så den extra tiden och minnet vägde tyngre. Med mer minne är gemma4:12b det "
             "första att byta till. gemma4:e4b (med 2,5 gånger större svarstak, eftersom den annars klipptes mitt i JSON) "
             "var sämre: 12 av 16 godtagbara med 4 övertriage, 69 % täckning och i snitt 0,5 belagda påståenden per "
             "möte, eftersom den skrev långa, utfyllda svar (6 752 utdatatokens per möte mot 1 806) som ofta klipptes. "
             "Båda gemma-modellerna är borttagna igen.", "",
             "## Metod", "",
             "- **Data:** en syntetisk person, minutupplöst simulering av 28 dygn (`eval/sim.py`). All data är märkt "
             "`syntetisk` och skrivs till slängbara databaser under `eval/tmp/`, aldrig till den riktiga.",
             "- **Klocka:** varje scenario körs i en egen process vars klocka flyttas till scenariots tidpunkt "
             "(03:40 för nattliga syrefall, 21:40 för pulsrusningen). Vaktens egna regler får titta på datan och "
             "deras larm fryses i `eval/utlosare.json`, så att alla varianter får exakt samma utlösare.",
             "- **Facit** (`eval/scenarier.py`): rätt brådska, vilka brådskor som är godtagbara, fynd som måste finnas "
             "(reguljära uttryck) och påståenden som inte får göras (räknas bara utan negation).",
             "- **Tränade scenarier:** 16. Förbättringarna gjordes medan de kördes, så de är optimistiska.",
             "- **Holdout:** 16 scenarier i fem omgångar, var och en skriven innan den kördes. När en holdout-omgång "
             "visade ett fel rättades orsaken generellt (inte scenariot) och en ny omgång skrevs för att mäta igen. "
             "Holdout 5 är delvis förorenad: vilopulsregeln för frågor skrevs efter att holdout 5:s faktablad "
             "(men inte teamets svar) setts. Första körningen av varje omgång: holdout 1 och 2 med v4 (10 av 10 "
             "brådska), holdout 3 med v5 (2 av 2), holdout 4 med v7 (2 av 2, ett missat fynd), holdout 5 med v8 "
             "(2 av 2).",
             "- **Tid:** modellen laddas ur före varje scenario, så tiden inkluderar en kall modellstart. Körningar "
             "som överlappade en annan modell i minnet (swap) är omkörda; minnet efter varje scenario sparas "
             "(`ollama_minne_gib_efter`).",
             "- **Domare:** medgemma:4b (en annan modell än Qwen som kör mötet) svarar på ja/nej-frågor mot facit. Den "
             "är för snäll (gav den gamla pipelinens holdout 2, med 1 av 5 rätt brådska, 5,0) och redovisas bara "
             "som komplement.",
             "- **Spridning:** v8 är körd fyra gånger på de 16 tränade scenarierna (v8, v8-rep2 till rep4) och två "
             "gånger på alla 16 holdout-scenarier (v8 och v8-final), holdout 5 fyra gånger. Oförändrad kod och modell. "
             "Tränade: brådskan godtagbar i 64 av 64 trådar och exakt i 14 av 16 i varje körning (samma två scenarier "
             "hamnar ett steg högre), täckning 90,6-94,3 % (medel 91,9 %), strykandel 8,7-16,3 %, median 123-128 s. "
             "Holdout: brådskan exakt i 36 av 36 trådar, ingen över- eller undertriage, täckning 93,8 % och 96,9 % i "
             "de två hela körningarna. Det som varierar är detaljer: 3 overifierade siffror på 64 tränade trådar och "
             "5 baslinjefel på 36 holdout-trådar (en siffra kallas baslinje fast den inte är det). Övriga varianter "
             "är körda en gång; skillnader på några procentenheter i täckning är brus.", "",
             "## Alla körningar", ""]
    rad = topp + [
           "Genereras av `eval/rapport.py`.",
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
    for sc in SCENARIER + HOLDOUT + HOLDOUT2 + HOLDOUT3 + HOLDOUT4 + HOLDOUT5:
        celler = []
        for d in data:
            r = next((x for x in d["rader"] if x["scenario"] == sc.id), None)
            celler.append("-" if not r else f"{'ok' if r['godtagbar'] else 'FEL'} {r['bradska'] or '?'} {r['tackning']:.0%}")
        rad.append(f"| {sc.id} | {sc.facit.bradska} | " + " | ".join(celler) + " |")
    (HIT / "RESULTAT.md").write_text("\n".join(rad) + "\n")


if __name__ == "__main__":
    main()
