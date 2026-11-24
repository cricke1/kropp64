#!/usr/bin/env python3
"""Tokenredovisning för Konsiliet: moln (Claude Code) och lokalt (Ollama på Mac minin).

Kör:  python3 tools/tokenredovisning.py [--fran 2026-11-24] [--db sökväg ...] [--json]

Moln
  Läser Claude Codes lokala sessionsloggar (~/.claude/projects/*/*.jsonl och subagents/*.jsonl).
  En session räknas med om
    - den har arbetat i /Users/sture/konsiliet, /Users/sture/Desktop/claude/konsiliet eller
      /Users/sture/Desktop/claude (fältet cwd i loggen), och
    - loggen nämner "konsiliet" någonstans, och
    - den har poster från --fran och framåt.
  Subagenter till en medräknad session räknas med (de startades av sessionen för projektet).
  Allt delas i tre delar som redovisas var för sig:
    bygget      huvudsessionen från BYGGSTART (ägarens "nice du ska bygga allt") och alla bygg-subagenter
    idéfas      huvudsessionen före BYGGSTART, då idén till tävlingen söktes
    granskning  subagenter vars beskrivning är en granskning (review)
  Tävlingsformulärets molnsiffra är bygget. Den kasserade Discord-agenten körde inte i Claude Code och finns
  inte i loggarna.
  Varje API-svar loggas en gång per innehållsblock med samma usage, så svaren avdupliceras på
  (message.id, requestId). Bara poster med tidsstämpel >= --fran räknas.

  Kolumner (från API:ets usage-fält):
    input        input_tokens, ocachad input
    cache-skriv  cache_creation_input_tokens
    cache-läs    cache_read_input_tokens
    output       output_tokens (inklusive tänkande)
    utan cache   input + output
    allt         input + cache-skriv + cache-läs + output

Lokalt
  0. Tabellen llm_calls i serverns databas (ett rad per Ollama-anrop) när den finns. Då används bara den
     plus resultatfilerna, eftersom 1 och 2 räknar samma anrop.
  1. GET http://127.0.0.1:8790/api/system -> tokens_sedan_start (räknare i minnet sedan serverstart).
  2. consults.stats i serverns databas(er), öppnade skrivskyddat. Sparas per konsilium och överlever omstart.
     Konsilier som startat efter serverns start ingår redan i (1). De dras av så att inget räknas två gånger.
  3. bench/resultat/*.json: objekt med prompt_tokens/output_tokens (eller prompt_eval_count/eval_count).
     eval/resultat/**/*.json: körningarnas "tokens": {"prompt", "ut"}. Enskilda anrop och medelvärden räknas inte.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECTS = Path.home() / ".claude" / "projects"
CWDS = ("/Users/sture/konsiliet", "/Users/sture/Desktop/claude/konsiliet", "/Users/sture/Desktop/claude")
NYCKELORD = re.compile(rb"konsiliet", re.I)
# Ägarens meddelande i huvudsessionen då bygget startade ("nice du ska bygga allt"). Före det: idésökning.
BYGGSTART = "2026-11-24T15:09:50Z"
KOLUMNER = ("input", "cache_skriv", "cache_las", "output")


# ------------------------------------------------------------------------------------------- moln

def _ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _cwd_ok(cwd: str | None) -> bool:
    if not cwd:
        return False
    cwd = cwd.rstrip("/")
    return any(cwd == c or cwd.startswith(c + "/") for c in CWDS)


_SETT: set[tuple] = set()  # avduplicering över alla filer, ifall en logg återger en annans svar


def _las_logg(path: Path, fran: float, till: float = float("inf")) -> dict:
    """Summerar usage i en jsonl-logg. Returnerar summor, cwd-träff, modeller och tidsintervall."""
    sett = _SETT
    s = {k: 0 for k in KOLUMNER}
    svar = 0
    modeller: dict[str, int] = {}
    cwd_traff = False
    forsta = sista = None
    for line in path.open("rb"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if _cwd_ok(d.get("cwd")):
            cwd_traff = True
        if d.get("type") != "assistant":
            continue
        t = _ts(d.get("timestamp"))
        if t is None or t < fran or t >= till:
            continue
        m = d.get("message") or {}
        u = m.get("usage")
        if not u:
            continue
        nyckel = (m.get("id"), d.get("requestId"))
        if nyckel in sett:
            continue
        sett.add(nyckel)
        svar += 1
        s["input"] += int(u.get("input_tokens") or 0)
        s["cache_skriv"] += int(u.get("cache_creation_input_tokens") or 0)
        s["cache_las"] += int(u.get("cache_read_input_tokens") or 0)
        s["output"] += int(u.get("output_tokens") or 0)
        mod = m.get("model") or "okänd"
        modeller[mod] = modeller.get(mod, 0) + 1
        forsta = t if forsta is None else min(forsta, t)
        sista = t if sista is None else max(sista, t)
    return {"summa": s, "svar": svar, "cwd": cwd_traff, "modeller": modeller, "forsta": forsta, "sista": sista}


def _beskrivning(agentfil: Path) -> str:
    meta = agentfil.parent / (agentfil.stem + ".meta.json")
    try:
        return json.loads(meta.read_text()).get("description") or agentfil.stem
    except (OSError, json.JSONDecodeError):
        return agentfil.stem


GRANSKNING = re.compile(r"review|granskning|granska", re.I)


def moln(fran: float, byggstart: float) -> list[dict]:
    """En rad per logg (huvudsessionen delas vid byggstart). kategori: bygge, idefas eller granskning."""
    rader = []
    for sess in sorted(PROJECTS.glob("*/*.jsonl")):
        if sess.stat().st_mtime < fran:
            continue
        if not NYCKELORD.search(sess.read_bytes()):
            # sessionen själv nämner inte projektet; kanske gör en subagent det
            sub = sess.with_suffix("") / "subagents"
            if not any(NYCKELORD.search(f.read_bytes()) for f in sub.glob("*.jsonl")):
                continue
        fore = _las_logg(sess, fran, byggstart)
        efter = _las_logg(sess, max(fran, byggstart))
        if not (fore["cwd"] or efter["cwd"]):
            continue
        if fore["svar"]:
            rader.append({"fil": str(sess), "namn": f"Huvudsession {sess.stem[:8]}, idéfas före byggstart",
                          "kategori": "idefas", **fore})
        if efter["svar"]:
            rader.append({"fil": str(sess), "namn": f"Huvudsession {sess.stem[:8]}, från byggstart",
                          "kategori": "bygge", **efter})
        for agent in sorted((sess.with_suffix("") / "subagents").glob("*.jsonl")):
            ra = _las_logg(agent, fran)
            if ra["svar"]:
                besk = _beskrivning(agent)
                kat = "granskning" if GRANSKNING.search(besk) else ("idefas" if ra["sista"] and ra["sista"] < byggstart else "bygge")
                rader.append({"fil": str(agent), "namn": f"Subagent: {besk}", "kategori": kat, **ra})
    return rader


# ------------------------------------------------------------------------------------------ lokalt

def _system(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url + "/api/system", timeout=5) as r:
            return json.load(r)
    except Exception:
        return None


def _serverstart(port: int) -> float | None:
    """Starttid för processen som lyssnar på porten (lsof + ps)."""
    try:
        pid = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                             capture_output=True, text=True).stdout.split()[0]
        lstart = subprocess.run(["ps", "-o", "lstart=", "-p", pid], capture_output=True, text=True,
                                env={**os.environ, "LC_ALL": "C"}).stdout.strip()
        return time.mktime(time.strptime(lstart, "%a %b %d %H:%M:%S %Y"))
    except Exception:
        return None


def konsilier(dbs: list[str]) -> list[dict]:
    ut: dict[str, dict] = {}
    for p in dbs:
        p = os.path.expanduser(p)
        if not os.path.exists(p):
            continue
        try:
            c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            for cid, started, stats in c.execute("SELECT id, started, stats FROM consults WHERE stats IS NOT NULL"):
                st = json.loads(stats)
                ut.setdefault(cid, {"id": cid, "db": p, "started": started,
                                    "prompt": int(st.get("prompt_tokens", 0)), "output": int(st.get("output_tokens", 0)),
                                    "anrop": int(st.get("calls", 0))})
            c.close()
        except sqlite3.Error:
            continue
    return sorted(ut.values(), key=lambda r: r["started"])


def _usage_bench(obj, fil: str, ut: list):
    """bench/: objekt med prompt_tokens/output_tokens (eller Ollamas prompt_eval_count/eval_count).
    Ett objekt med summa räknas, dess barn inte."""
    if isinstance(obj, dict):
        p = obj.get("prompt_tokens", obj.get("prompt_eval_count"))
        o = obj.get("output_tokens", obj.get("eval_count"))
        if isinstance(p, (int, float)) and isinstance(o, (int, float)):
            ut.append((fil, int(p), int(o)))
            return
        summa = [k for k in obj if re.match(r"^(tot|summa)", str(k), re.I)]
        for k in summa or obj:
            _usage_bench(obj[k], fil, ut)
    elif isinstance(obj, list):
        for x in obj:
            _usage_bench(x, fil, ut)


def _usage_eval(obj, fil: str, ut: list):
    """eval/: en körning (eval/kor_ett.py) har "tokens": {"prompt", "ut", "anrop"} med summan för körningen.
    Bara de summorna räknas. Listan med enskilda anrop och poängfilernas medelvärden räknas inte."""
    if isinstance(obj, dict):
        t = obj.get("tokens")
        if isinstance(t, dict) and isinstance(t.get("prompt"), (int, float)) and isinstance(t.get("ut"), (int, float)):
            ut.append((fil, int(t["prompt"]), int(t["ut"])))
            return
        for v in obj.values():
            _usage_eval(v, fil, ut)
    elif isinstance(obj, list):
        for x in obj:
            _usage_eval(x, fil, ut)


def filresultat() -> tuple[list[tuple[str, int, int]], list[str]]:
    bench = sorted(glob.glob(str(REPO / "bench" / "resultat" / "*.json")))
    ev = sorted(glob.glob(str(REPO / "eval" / "resultat" / "**" / "*.json"), recursive=True))
    ut: list[tuple[str, int, int]] = []
    for filer, f_usage in ((bench, _usage_bench), (ev, _usage_eval)):
        for f in filer:
            try:
                f_usage(json.loads(Path(f).read_text()), os.path.relpath(f, REPO), ut)
            except (OSError, json.JSONDecodeError):
                pass
    return ut, [os.path.relpath(f, REPO) for f in bench + ev]


def llm_calls(dbs: list[str]) -> dict | None:
    """Tabellen llm_calls (ett rad per anrop till Ollama, sparas av servern) om den finns i någon databas.
    Kolumnnamnen läses ur tabellen: prompt-/input-kolumn och output-/ut-kolumn."""
    tot = {"anrop": 0, "prompt": 0, "output": 0, "per_modell": {}, "dbs": []}
    hittad = False
    for p in dbs:
        p = os.path.expanduser(p)
        if not os.path.exists(p):
            continue
        try:
            c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            cols = [r[1] for r in c.execute("PRAGMA table_info(llm_calls)")]
            if not cols:
                c.close()
                continue
            pc = next((x for x in cols if re.match(r"^(prompt|input|in)(_tokens)?$", x)), None)
            oc = next((x for x in cols if re.match(r"^(output|ut|eval)(_tokens|_count)?$", x)), None)
            mc = next((x for x in cols if x in ("model", "modell")), None)
            if not pc or not oc:
                c.close()
                continue
            hittad = True
            tot["dbs"].append(p)
            modkol = mc or "'okänd'"
            q = f"SELECT {modkol}, COUNT(*), SUM({pc}), SUM({oc}) FROM llm_calls GROUP BY 1"
            for mod, k, ps, os_ in c.execute(q):
                tot["anrop"] += k
                tot["prompt"] += int(ps or 0)
                tot["output"] += int(os_ or 0)
                m = tot["per_modell"].setdefault(mod, [0, 0, 0])
                m[0] += k
                m[1] += int(ps or 0)
                m[2] += int(os_ or 0)
            c.close()
        except sqlite3.Error:
            continue
    return tot if hittad else None


# ------------------------------------------------------------------------------------------ utskrift

def n(x: int) -> str:
    return f"{x:,}".replace(",", " ")


KATEGORIER = (("bygge", "Bygget"), ("idefas", "Idéfas före byggstart"), ("granskning", "Oberoende granskning"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fran", default="2026-11-24", help="datum (lokal tid), poster före räknas inte")
    ap.add_argument("--byggstart", default=BYGGSTART, help="ISO-tid (UTC) då bygget började i huvudsessionen")
    ap.add_argument("--server", default="http://127.0.0.1:8790")
    ap.add_argument("--db", nargs="*", default=None, help="serverdatabaser (standard ~/.konsiliet/*.db)")
    ap.add_argument("--json", action="store_true", help="skriv råa summor som JSON i stället för Markdown")
    a = ap.parse_args()
    fran = time.mktime(time.strptime(a.fran, "%Y-%m-%d"))
    byggstart = _ts(a.byggstart)
    dbs = a.db if a.db is not None else sorted(glob.glob(os.path.expanduser("~/.konsiliet/*.db")))

    rader = moln(fran, byggstart)
    per_kat = {k: {c: sum(r["summa"][c] for r in rader if r["kategori"] == k) for c in KOLUMNER} for k, _ in KATEGORIER}
    svar_kat = {k: sum(r["svar"] for r in rader if r["kategori"] == k) for k, _ in KATEGORIER}

    calls = llm_calls(dbs)
    sysinfo = _system(a.server)
    start = _serverstart(int(a.server.rsplit(":", 1)[-1])) if sysinfo else None
    ks = konsilier(dbs)
    fr, filer = filresultat()

    if a.json:
        print(json.dumps({"moln": {"rader": rader, "per_kategori": per_kat},
                          "lokalt": {"llm_calls": calls, "system": sysinfo and sysinfo.get("tokens_sedan_start"),
                                     "serverstart": start, "konsilier": ks, "filer": fr}},
                         ensure_ascii=False, indent=1, default=str))
        return

    nu = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"# Tokenredovisning\n\nGenererad {nu} av `tools/tokenredovisning.py`, poster från {a.fran}.\n")
    print("## Moln: Claude Code\n")
    print("Avgränsning: sessioner i Claude Codes loggar som arbetat i projektmapparna och nämner Konsiliet. "
          f"Huvudsessionen delas vid byggstart ({datetime.fromtimestamp(byggstart):%Y-%m-%d %H:%M} lokal tid, "
          "ägarens meddelande \"nice du ska bygga allt\"). Allt före det var idésökning för tävlingen och redovisas "
          "separat. Subagenten som gjorde en oberoende granskning redovisas också separat. Den kasserade "
          "Discord-agentens arbete (se RESAN.md) gjordes utanför Claude Code och finns inte i loggarna, så det ingår inte.\n")
    print("| Session | Del | Svar | Input | Cache-skriv | Cache-läs | Output | Utan cache |")
    print("|---|---|--:|--:|--:|--:|--:|--:|")
    namn = dict(KATEGORIER)
    for k, _ in KATEGORIER:
        for r in [r for r in rader if r["kategori"] == k]:
            s = r["summa"]
            print(f"| {r['namn']} | {namn[k]} | {n(r['svar'])} | {n(s['input'])} | {n(s['cache_skriv'])} | "
                  f"{n(s['cache_las'])} | {n(s['output'])} | {n(s['input'] + s['output'])} |")
    print()
    print("| Summa | Svar | Input | Cache-skriv | Cache-läs | Output | Utan cache | Allt |")
    print("|---|--:|--:|--:|--:|--:|--:|--:|")
    alla = {c: 0 for c in KOLUMNER}
    for k, rubrik in KATEGORIER:
        s = per_kat[k]
        for c in KOLUMNER:
            alla[c] += s[c]
        fet = "**" if k == "bygge" else ""
        print(f"| {fet}{rubrik}{fet} | {n(svar_kat[k])} | {n(s['input'])} | {n(s['cache_skriv'])} | {n(s['cache_las'])} | "
              f"{n(s['output'])} | {fet}{n(s['input'] + s['output'])}{fet} | {n(sum(s.values()))} |")
    print(f"| Alla tre | {n(sum(svar_kat.values()))} | {n(alla['input'])} | {n(alla['cache_skriv'])} | {n(alla['cache_las'])} | "
          f"{n(alla['output'])} | {n(alla['input'] + alla['output'])} | {n(sum(alla.values()))} |")
    modeller: dict[str, int] = {}
    for r in rader:
        for m, c in r["modeller"].items():
            modeller[m] = modeller.get(m, 0) + c
    print(f"\nModeller (antal svar): {', '.join(f'{m} {c}' for m, c in sorted(modeller.items()))}.")
    print("Utan cache = input + output. Allt = input + cache-skriv + cache-läs + output. Output inkluderar tänkande. "
          "Varje svar loggas en gång per innehållsblock, så svaren avdupliceras på (message.id, requestId). "
          "Claude Codes egna små hjälpanrop (rubriker, sammanfattningar) loggas inte per svar och ingår inte.")
    if rader:
        f0 = min(r["forsta"] for r in rader if r["forsta"])
        s0 = max(r["sista"] for r in rader if r["sista"])
        print(f"Första svaret {datetime.fromtimestamp(f0):%Y-%m-%d %H:%M}, senaste {datetime.fromtimestamp(s0):%Y-%m-%d %H:%M}.")
    print()

    print("## Lokalt: Ollama på Mac minin\n")
    print("| Källa | Anrop | Prompt (in) | Output (ut) | Summa |")
    print("|---|--:|--:|--:|--:|")
    lok_p = lok_o = 0
    if calls:
        for mod, (k, ps, os_) in sorted(calls["per_modell"].items()):
            print(f"| llm_calls, {mod} | {n(k)} | {n(ps)} | {n(os_)} | {n(ps + os_)} |")
        print(f"| llm_calls totalt ({', '.join(os.path.basename(d) for d in calls['dbs'])}) | {n(calls['anrop'])} | "
              f"{n(calls['prompt'])} | {n(calls['output'])} | {n(calls['prompt'] + calls['output'])} |")
        lok_p += calls["prompt"]
        lok_o += calls["output"]
        kalla = "llm_calls"
    else:
        db_p = sum(k["prompt"] for k in ks)
        db_o = sum(k["output"] for k in ks)
        print(f"| Sparade konsilier i databasen ({len(ks)} st) | {n(sum(k['anrop'] for k in ks))} | {n(db_p)} | {n(db_o)} | {n(db_p + db_o)} |")
        lok_p += db_p
        lok_o += db_o
        if sysinfo:
            u = sysinfo.get("tokens_sedan_start") or {}
            sp, so = int(u.get("prompt_tokens", 0)), int(u.get("output_tokens", 0))
            efter = [k for k in ks if start and k["started"] >= start]
            ep, eo = sum(k["prompt"] for k in efter), sum(k["output"] for k in efter)
            startstr = datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M") if start else "okänd"
            print(f"| Servern sedan start ({startstr}), alla anrop | {n(int(u.get('calls', 0)))} | {n(sp)} | {n(so)} | {n(sp + so)} |")
            if start:
                op, oo = max(0, sp - ep), max(0, so - eo)
                print(f"| varav utanför sparade konsilier (brief, frågor, pågående) | | {n(op)} | {n(oo)} | {n(op + oo)} |")
                lok_p += op
                lok_o += oo
            else:
                print("| (serverns starttid okänd, räknas inte i summan för att undvika dubbelräkning) | | | | |")
        else:
            print(f"| Servern ({a.server}) svarade inte | | | | |")
        kalla = "konsilier + serverräknare"
    fp = sum(p for _, p, _ in fr)
    fo = sum(o for _, _, o in fr)
    print(f"| bench/resultat och eval/resultat ({len(fr)} körningar med tokens i {len(filer)} filer) | | {n(fp)} | {n(fo)} | {n(fp + fo)} |")
    lok_p += fp
    lok_o += fo
    print(f"| **Lokalt totalt** | | **{n(lok_p)}** | **{n(lok_o)}** | **{n(lok_p + lok_o)}** |")
    if calls:
        print("\nServern sparar varje anrop i tabellen llm_calls; den används i stället för konsiliernas summor och "
              "serverns räknare (de skulle räkna samma anrop igen).")
    else:
        print("\nTabellen llm_calls finns inte än. Serverns räknare nollställs vid omstart, så anrop före senaste start som "
              "inte hörde till ett sparat konsilium (t.ex. testkörningar mot raderade databaser) finns inte kvar och räknas inte.")
    print("Utvärderingen (eval/) kör mot egna databaser i eval/tmp och räknas bara via sina resultatfiler.")
    if filer and not fr:
        print("Resultatfilerna innehåller inga tokenräkningar (bench mäter bara hastighet och träffsäkerhet).")
    print("\n## Till tävlingsformuläret\n")
    b = per_kat["bygge"]
    print("| | Tokens |")
    print("|---|--:|")
    print(f"| Moln (Claude Code, bygget), utan cache: input + output | {n(b['input'] + b['output'])} |")
    print(f"| Moln (bygget), cache-skrivning | {n(b['cache_skriv'])} |")
    print(f"| Moln (bygget), cache-läsning | {n(b['cache_las'])} |")
    print(f"| Lokalt (Ollama), prompt + output, källa: {kalla} och resultatfiler | {n(lok_p + lok_o)} |")


if __name__ == "__main__":
    sys.exit(main())
