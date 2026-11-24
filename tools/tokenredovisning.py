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
  Subagenter till en medräknad session räknas alltid med (de startades av sessionen för projektet).
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
  1. GET http://127.0.0.1:8790/api/system -> tokens_sedan_start (räknare i minnet sedan serverstart).
  2. consults.stats i serverns databas(er), öppnade skrivskyddat. Sparas per konsilium och överlever omstart.
     Konsilier som startat efter serverns start ingår redan i (1). De dras av så att inget räknas två gånger.
  3. bench/resultat/*.json och eval/**/*.json: alla objekt med prompt_tokens/output_tokens
     (eller prompt_eval_count/eval_count). Ett objekt med en summa räknas, dess underobjekt inte.
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


def _las_logg(path: Path, fran: float) -> dict:
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
        if t is None or t < fran:
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


def moln(fran: float) -> list[dict]:
    rader = []
    for sess in sorted(PROJECTS.glob("*/*.jsonl")):
        if sess.stat().st_mtime < fran:
            continue
        if not NYCKELORD.search(sess.read_bytes()):
            # sessionen själv nämner inte projektet; kanske gör en subagent det
            sub = sess.with_suffix("") / "subagents"
            if not any(NYCKELORD.search(f.read_bytes()) for f in sub.glob("*.jsonl")):
                continue
        r = _las_logg(sess, fran)
        if not r["cwd"]:
            continue
        rader.append({"fil": str(sess), "namn": f"Huvudsession {sess.stem[:8]}", **r})
        for agent in sorted((sess.with_suffix("") / "subagents").glob("*.jsonl")):
            ra = _las_logg(agent, fran)
            if ra["svar"]:
                rader.append({"fil": str(agent), "namn": f"Subagent: {_beskrivning(agent)}", **ra})
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


def _usage_i(obj, fil: str, ut: list):
    """Hittar usage-objekt i godtycklig JSON. Ett objekt med summa räknas, dess barn inte."""
    if isinstance(obj, dict):
        p = obj.get("prompt_tokens", obj.get("prompt_eval_count"))
        o = obj.get("output_tokens", obj.get("eval_count"))
        if isinstance(p, (int, float)) and isinstance(o, (int, float)):
            ut.append((fil, int(p), int(o)))
            return
        summa = [k for k in obj if re.match(r"^(tot|summa)", str(k), re.I)]
        for k in summa or obj:
            _usage_i(obj[k], fil, ut)
    elif isinstance(obj, list):
        for x in obj:
            _usage_i(x, fil, ut)


def filresultat() -> tuple[list[tuple[str, int, int]], list[str]]:
    filer = sorted(glob.glob(str(REPO / "bench" / "resultat" / "*.json")) +
                   glob.glob(str(REPO / "eval" / "**" / "*.json"), recursive=True))
    ut: list[tuple[str, int, int]] = []
    for f in filer:
        try:
            _usage_i(json.loads(Path(f).read_text()), os.path.relpath(f, REPO), ut)
        except (OSError, json.JSONDecodeError):
            pass
    return ut, [os.path.relpath(f, REPO) for f in filer]


# ------------------------------------------------------------------------------------------ utskrift

def n(x: int) -> str:
    return f"{x:,}".replace(",", " ")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fran", default="2026-11-24", help="datum (lokal tid), poster före räknas inte")
    ap.add_argument("--server", default="http://127.0.0.1:8790")
    ap.add_argument("--db", nargs="*", default=None, help="serverdatabaser (standard ~/.konsiliet/*.db)")
    ap.add_argument("--json", action="store_true", help="skriv råa summor som JSON i stället för Markdown")
    a = ap.parse_args()
    fran = time.mktime(time.strptime(a.fran, "%Y-%m-%d"))
    dbs = a.db if a.db is not None else sorted(glob.glob(os.path.expanduser("~/.konsiliet/*.db")))

    rader = moln(fran)
    tot = {k: sum(r["summa"][k] for r in rader) for k in KOLUMNER}
    svar = sum(r["svar"] for r in rader)

    sysinfo = _system(a.server)
    start = _serverstart(int(a.server.rsplit(":", 1)[-1])) if sysinfo else None
    ks = konsilier(dbs)
    fr, filer = filresultat()

    if a.json:
        print(json.dumps({"moln": {"rader": rader, "totalt": tot, "svar": svar},
                          "lokalt": {"system": sysinfo and sysinfo.get("tokens_sedan_start"), "serverstart": start,
                                     "konsilier": ks, "filer": fr}}, ensure_ascii=False, indent=1, default=str))
        return

    nu = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"# Tokenredovisning\n\nGenererad {nu} av `tools/tokenredovisning.py`, poster från {a.fran}.\n")
    print("## Moln: Claude Code\n")
    print("| Session | Svar | Input | Cache-skriv | Cache-läs | Output | Utan cache | Allt |")
    print("|---|--:|--:|--:|--:|--:|--:|--:|")
    for r in rader:
        s = r["summa"]
        print(f"| {r['namn']} | {n(r['svar'])} | {n(s['input'])} | {n(s['cache_skriv'])} | {n(s['cache_las'])} | "
              f"{n(s['output'])} | {n(s['input'] + s['output'])} | {n(sum(s.values()))} |")
    print(f"| **Totalt** | **{n(svar)}** | **{n(tot['input'])}** | **{n(tot['cache_skriv'])}** | **{n(tot['cache_las'])}** | "
          f"**{n(tot['output'])}** | **{n(tot['input'] + tot['output'])}** | **{n(sum(tot.values()))}** |")
    modeller: dict[str, int] = {}
    for r in rader:
        for m, c in r["modeller"].items():
            modeller[m] = modeller.get(m, 0) + c
    print(f"\nModeller (antal svar): {', '.join(f'{m} {c}' for m, c in sorted(modeller.items()))}.")
    print("Utan cache = input + output. Allt = input + cache-skriv + cache-läs + output. "
          "Svar avduplicerade på (message.id, requestId).")
    if rader:
        f0 = min(r["forsta"] for r in rader if r["forsta"])
        s0 = max(r["sista"] for r in rader if r["sista"])
        print(f"Första svaret {datetime.fromtimestamp(f0):%Y-%m-%d %H:%M}, senaste {datetime.fromtimestamp(s0):%Y-%m-%d %H:%M}. "
              "Huvudsessionen innehåller också idéfasen före bygget. Claude Codes egna små hjälpanrop "
              "(t.ex. rubriker och sammanfattningar) loggas inte per svar och ingår inte.\n")
    else:
        print()

    print("## Lokalt: Ollama på Mac minin\n")
    print("| Källa | Anrop | Prompt (in) | Output (ut) | Summa |")
    print("|---|--:|--:|--:|--:|")
    lok_p = lok_o = 0
    db_p = sum(k["prompt"] for k in ks)
    db_o = sum(k["output"] for k in ks)
    print(f"| Sparade konsilier i databasen ({len(ks)} st) | {n(sum(k['anrop'] for k in ks))} | {n(db_p)} | {n(db_o)} | {n(db_p + db_o)} |")
    lok_p += db_p
    lok_o += db_o
    if sysinfo:
        u = sysinfo.get("tokens_sedan_start") or {}
        sp, so = int(u.get("prompt_tokens", 0)), int(u.get("output_tokens", 0))
        efter = [k for k in ks if start and k["started"] >= start] if start else []
        ep, eo = sum(k["prompt"] for k in efter), sum(k["output"] for k in efter)
        startstr = datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M") if start else "okänd"
        print(f"| Servern sedan start ({startstr}), alla anrop | {n(int(u.get('calls', 0)))} | {n(sp)} | {n(so)} | {n(sp + so)} |")
        if start:
            op, oo = max(0, sp - ep), max(0, so - eo)
            print(f"| varav utanför sparade konsilier (brief, frågor, pågående) | | {n(op)} | {n(oo)} | {n(op + oo)} |")
            lok_p += op
            lok_o += oo
        else:
            print("| (serverns starttid okänd, räknas inte in i summan för att undvika dubbelräkning) | | | | |")
    else:
        print(f"| Servern ({a.server}) svarade inte | | | | |")
    fp = sum(p for _, p, _ in fr)
    fo = sum(o for _, _, o in fr)
    print(f"| bench/ och eval/ ({len(fr)} poster med tokens i {len(filer)} filer) | | {n(fp)} | {n(fo)} | {n(fp + fo)} |")
    lok_p += fp
    lok_o += fo
    print(f"| **Lokalt totalt** | | **{n(lok_p)}** | **{n(lok_o)}** | **{n(lok_p + lok_o)}** |")
    print("\nServerns räknare nollställs vid omstart. Anrop som gjordes före senaste start och inte hörde till ett "
          "sparat konsilium (t.ex. testkörningar mot databaser som sedan raderats) finns inte kvar och räknas inte.")
    if filer and not fr:
        print("Filerna i bench/ och eval/ innehåller inga tokenräkningar (bara hastighet och träffsäkerhet).")
    print("\n## Sammanfattning\n")
    print("| | Tokens |")
    print("|---|--:|")
    print(f"| Moln, utan cache (input + output) | {n(tot['input'] + tot['output'])} |")
    print(f"| Moln, cache-skrivning | {n(tot['cache_skriv'])} |")
    print(f"| Moln, cache-läsning | {n(tot['cache_las'])} |")
    print(f"| Lokalt (prompt + output) | {n(lok_p + lok_o)} |")


if __name__ == "__main__":
    sys.exit(main())
