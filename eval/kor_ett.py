"""Kör ETT scenario i en egen process: bygger den syntetiska databasen, flyttar klockan, kör konsiliet.

Anropas av kor.py. Separat process per scenario så att databasanslutning, inställningar och klocka är rena.

    python kor_ett.py <scenario-id> <ut.json> [--src server/src]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import zlib
from datetime import datetime
from pathlib import Path

HIT = Path(__file__).resolve().parent
sys.path.insert(0, str(HIT))


def flytta_klockan(klocka: str) -> float:
    """Sätter processens klocka till senaste passerade tillfälle av klockslaget (lokal tid). Tiden går som vanligt."""
    verklig = time.time
    nu = datetime.now()
    hh, mm = (int(x) for x in klocka.split(":"))
    mal = nu.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if mal.timestamp() > nu.timestamp():
        mal = datetime.fromtimestamp(mal.timestamp() - 86400)
    forskjutning = mal.timestamp() - verklig()
    time.time = lambda: verklig() + forskjutning  # type: ignore[assignment]
    return forskjutning


class FalskDT(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return datetime.fromtimestamp(time.time(), tz)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("ut")
    ap.add_argument("--src", default=str(HIT.parent / "server" / "src"))
    ap.add_argument("--variant", default="dev")
    ap.add_argument("--torr", action="store_true", help="bygg data och kör vakten, men inget möte")
    ap.add_argument("--fakta", action="store_true", help="bygg data och skriv ut faktabladet och regelbrådskan")
    a = ap.parse_args()

    from scenarier import SCENARIO
    sc = SCENARIO[a.scenario]
    tmp = HIT / "tmp"
    tmp.mkdir(exist_ok=True)
    dbfil = tmp / f"{a.variant}-{sc.id}.db"
    os.environ["KONSILIET_DB"] = str(dbfil)
    os.environ["KONSILIET_TILLAT_EMULATOR"] = "1"  # datan är märkt syntetisk och ska användas här
    assert ".konsiliet" not in str(dbfil)
    forsk = flytta_klockan(sc.klocka)

    sys.path.insert(0, a.src)
    from sim import Sim
    from konsiliet import db  # noqa: E402
    assert db.settings.db_path == str(dbfil), "fel databas"

    sim = Sim(time.time(), fro=zlib.crc32(sc.id.encode()))
    reserv = sc.bygg(sim)
    antal = sim.skriv(dbfil, db.SCHEMA)

    from konsiliet import konsiliet, llm, vakt  # noqa: E402
    for namn, mod in list(sys.modules.items()):
        if namn.startswith("konsiliet") and getattr(mod, "datetime", None) is datetime:
            mod.datetime = FalskDT  # type: ignore[attr-defined]

    anrop: list[dict] = []
    orig_chat = llm.chat

    def chat(model, messages, *args, **kw):  # type: ignore[no-untyped-def]
        r = orig_chat(model, messages, *args, **kw)
        anrop.append({"modell": model, "prompt": r.prompt_tokens, "ut": r.output_tokens, "s": round(r.seconds, 2),
                      "think": bool(kw.get("think")), "verktyg": bool(kw.get("tools") or (args[0] if args else None)),
                      "schema": bool(kw.get("fmt"))})
        return r
    llm.chat = chat  # type: ignore[assignment]

    # Utlösaren: den riktiga vakten tittar på datan (en gång, med --torr), resultatet fryses i utlosare.json
    # så att alla varianter får exakt samma utlösare. Larmar vakten inte används scenariots egen utlösare.
    fryst_fil = HIT / "utlosare.json"
    fryst = json.loads(fryst_fil.read_text()) if fryst_fil.exists() else {}
    if sc.id in fryst and not a.torr:
        trigger, fran_vakt = fryst[sc.id]["utlosare"], fryst[sc.id]["fran_vakt"]
    else:
        trigger, fran_vakt = reserv, False
        if reserv.get("kind") == "anomaly":
            try:
                fynd = vakt._evaluate(sim.nu)
            except TypeError:
                fynd = vakt._evaluate()
            for f in fynd:
                if f.rule == reserv["rule"]:
                    trigger = {"kind": "anomaly", "rule": f.rule, "level": f.level, "metric": f.metric,
                               "title": f.title, "detail": f.detail, "window": f.window}
                    fran_vakt = True
                    break
        if a.torr:
            fryst[sc.id] = {"utlosare": trigger, "fran_vakt": fran_vakt}
            fryst_fil.write_text(json.dumps(fryst, ensure_ascii=False, indent=1, default=str))
    # fönstret i utlösaren är i absoluta sekunder: flytta det till den här körningens klocka
    if trigger.get("window") and sc.id in fryst and not a.torr:
        w = trigger["window"]
        d = (fryst[sc.id].get("nu") or 0)
        if d:
            trigger = {**trigger, "window": [w[0] - d + sim.nu, w[1] - d + sim.nu]}
    if a.torr:
        fryst[sc.id]["nu"] = sim.nu
        fryst_fil.write_text(json.dumps(fryst, ensure_ascii=False, indent=1, default=str))

    if a.fakta:
        from konsiliet import fakta
        for namn, mod in list(sys.modules.items()):
            if namn.startswith("konsiliet") and getattr(mod, "datetime", None) is datetime:
                mod.datetime = FalskDT  # type: ignore[attr-defined]
        t1 = time.time()
        fa = fakta.faktaark(trigger)
        print(json.dumps({"scenario": sc.id, "regel": fakta.regelbradska(trigger, fa), "facit": sc.facit.bradska,
                          "sek": round(time.time() - t1, 2), "tecken": len(json.dumps(fa, ensure_ascii=False)),
                          "fakta": fa}, ensure_ascii=False, default=str))
        return
    if a.torr:
        print(json.dumps({"scenario": sc.id, "fran_vakt": fran_vakt, "utlosare": trigger, "antal": antal,
                          }, ensure_ascii=False, default=str))
        return
    m = konsiliet.Mote(f"eval-{sc.id}", trigger)
    t0 = time.time()
    fel = None
    try:
        konsiliet._kor(m)
    except Exception:
        fel = traceback.format_exc()
    sek = time.time() - t0

    verdict = next((e["verdict"] for e in reversed(m.transcript) if e["kind"] == "consult.verdict"), None)
    strikes = [{"agent": e.get("target"), "claim": e.get("claim"), "reason": e.get("reason")}
               for e in m.transcript if e["kind"] == "review.strike"]
    claims = [{"agent": e["agent"], **c} for e in m.transcript if e["kind"] == "agent.say" for c in e.get("claims", [])]
    sagt = [{"agent": e["agent"], "text": e.get("text", "")} for e in m.transcript if e["kind"] == "agent.say"]
    verktyg = [{"agent": e["agent"], "tool": e["tool"], "args": e.get("args")} for e in m.transcript if e["kind"] == "agent.tool"]
    medlemmar = next((e["members"] for e in reversed(m.transcript) if e["kind"] == "consult.members"), [])
    tu = llm.total_usage.as_dict()
    ut = {"scenario": sc.id, "titel": sc.titel, "klocka": sc.klocka, "forskjutning_s": round(forsk),
          "utlosare": trigger, "utlosare_fran_vakt": fran_vakt, "dataantal": antal,
          "verdict": verdict, "strykningar": strikes, "pastaenden": claims, "yttranden": sagt,
          "verktygsanrop": verktyg, "medlemmar": medlemmar, "refs": m.refs,
          "sekunder": round(sek, 1), "tokens": {"prompt": tu["prompt_tokens"], "ut": tu["output_tokens"],
                                                "anrop": tu["calls"], "per_modell": tu["per_model"]},
          "llm_anrop": anrop, "fel": fel}
    Path(a.ut).write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
