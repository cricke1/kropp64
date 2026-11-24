"""Mäter lokala modeller på Mac minin för just konsiliets jobb.

För varje modell:
  - genereringshastighet (tokens/s) och prompthastighet
  - minne som modellen tar (ollama ps)
  - verktygsanrop: väljer modellen rätt verktyg med giltiga argument? (fasta testfall)
  - källdisciplin: hur stor andel av påståendena i en bedömning klarar granskaren?

Kör:  cd server && uv run python ../bench/bench.py qwen3.5:9b gemma4:12b gemma4:e4b
Resultat skrivs till bench/resultat/<modell>.json och sammanfattas i bench/RESULTAT.md.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

OLLAMA = "http://127.0.0.1:11434"
UT = Path(__file__).parent / "resultat"
UT.mkdir(exist_ok=True)
c = httpx.Client(base_url=OLLAMA, timeout=900)

TOOLS = [
    {"type": "function", "function": {"name": "hamta_serie", "description": "Hämta tidsserie från klockan",
     "parameters": {"type": "object", "properties": {
         "metric": {"type": "string", "enum": ["hr", "hrv_rmssd", "spo2", "steps", "resp_rate", "skin_temp"]},
         "timmar_bakat": {"type": "number"}}, "required": ["metric"]}}},
    {"type": "function", "function": {"name": "hamta_somn", "description": "Sömnpass med faser",
     "parameters": {"type": "object", "properties": {"natter": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "hamta_labb", "description": "Provsvar från 1177",
     "parameters": {"type": "object", "properties": {"analyt": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "sok_journal", "description": "Sök i journalanteckningar",
     "parameters": {"type": "object", "properties": {"sokord": {"type": "string"}}}}},
]

# (fråga, förväntat verktyg, kontroll av argument)
FALL = [
    ("Hur har min puls varit det senaste dygnet?", "hamta_serie", lambda a: a.get("metric") == "hr"),
    ("Har min HRV sjunkit den här veckan?", "hamta_serie", lambda a: a.get("metric") == "hrv_rmssd"),
    ("Hur sov jag i natt?", "hamta_somn", lambda a: True),
    ("Vad var mitt ferritin senast?", "hamta_labb", lambda a: "ferritin" in str(a.get("analyt", "")).lower()),
    ("Står det något om astma i min journal?", "sok_journal", lambda a: "astma" in str(a.get("sokord", "")).lower()),
    ("Hur låg var min syremättnad i natt?", "hamta_serie", lambda a: a.get("metric") == "spo2"),
    ("Hur många steg har jag gått senaste tre dagarna?", "hamta_serie",
     lambda a: a.get("metric") == "steps" and float(a.get("timmar_bakat", 0) or 0) >= 48),
    ("Andas jag snabbare än vanligt?", "hamta_serie", lambda a: a.get("metric") == "resp_rate"),
    ("Mitt TSH-värde, vad var det?", "hamta_labb", lambda a: "tsh" in str(a.get("analyt", "")).lower()),
    ("Hur mycket djupsömn fick jag förra veckan?", "hamta_somn", lambda a: int(a.get("natter", 7) or 7) >= 5),
]

SYS = "Du är en läkaragent. Använd ett verktyg för att hämta data innan du svarar. Svara på svenska."


def hastighet(model: str) -> dict:
    prompt = "Förklara kort på svenska vad pulsvariabilitet (HRV) är och varför den sjunker vid stress. " * 8
    r = c.post("/api/generate", json={"model": model, "prompt": prompt, "stream": False, "think": False,
                                       "options": {"num_predict": 256, "temperature": 0}}).json()
    ps = c.get("/api/ps").json().get("models", [])
    mem = next((m for m in ps if m.get("name", "").startswith(model.split(":")[0])), {})
    return {
        "gen_tok_s": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1),
        "prompt_tok_s": round(r["prompt_eval_count"] / (r["prompt_eval_duration"] / 1e9), 1),
        "laddning_s": round(r.get("load_duration", 0) / 1e9, 1),
        "minne_gb": round(mem.get("size", 0) / 2**30, 2),
    }


def verktygsanrop(model: str) -> dict:
    ratt, giltig, tider = 0, 0, []
    detaljer = []
    for fraga, forvantat, ok in FALL:
        t0 = time.time()
        r = c.post("/api/chat", json={"model": model, "stream": False, "think": False, "tools": TOOLS,
                                      "messages": [{"role": "system", "content": SYS},
                                                   {"role": "user", "content": fraga}],
                                      "options": {"temperature": 0}}).json()
        tider.append(time.time() - t0)
        calls = r.get("message", {}).get("tool_calls") or []
        namn = calls[0]["function"]["name"] if calls else None
        args = calls[0]["function"].get("arguments", {}) if calls else {}
        r_ok = namn == forvantat
        a_ok = r_ok and ok(args if isinstance(args, dict) else {})
        ratt += r_ok
        giltig += a_ok
        detaljer.append({"fraga": fraga, "valde": namn, "args": args, "ratt_verktyg": r_ok, "ratt_argument": a_ok})
    return {"ratt_verktyg": f"{ratt}/{len(FALL)}", "ratt_argument": f"{giltig}/{len(FALL)}",
            "median_s": round(sorted(tider)[len(tider) // 2], 2), "detaljer": detaljer}


def main(models: list[str]) -> None:
    for m in models:
        print(f"== {m}", flush=True)
        res = {"modell": m, "tid": time.strftime("%Y-%m-%d %H:%M"), "maskin": "Mac mini M4 16 GB"}
        res["hastighet"] = hastighet(m)
        print(" hastighet", res["hastighet"], flush=True)
        res["verktyg"] = verktygsanrop(m)
        print(" verktyg", {k: v for k, v in res["verktyg"].items() if k != "detaljer"}, flush=True)
        (UT / f"{m.replace(':', '_').replace('/', '_')}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        c.post("/api/generate", json={"model": m, "keep_alive": 0})  # lasta ur innan nästa


if __name__ == "__main__":
    main(sys.argv[1:])
