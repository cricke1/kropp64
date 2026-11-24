"""Automatisk poängsättning av ett konsilium mot scenariots facit. Deterministisk, ingen språkmodell."""
from __future__ import annotations

import json
import re
from typing import Any

from scenarier import NIVAER, SCENARIO

NEG = re.compile(r"\b(inte|ingen|inget|inga|utan|ej|knappast|osannolik\w*|uteslut\w*|varken|snarare än)\b", re.I)
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")
_BORT = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\b\d{4}-\d{2}-\d{2}\b|[SBNJLUF]:[\w:.\-]+")


def _meningar(text: str) -> list[str]:
    return [m.strip() for m in re.split(r"(?<=[.!?])\s+|\n|;", text) if m.strip()]


def korpus(v: dict[str, Any] | None) -> str:
    if not v:
        return ""
    delar = [v.get("sammanfattning", "")]
    delar += [str(x) for x in v.get("rad", []) or []]
    delar += [str(x) for x in v.get("fragor_till_varden", []) or []]
    delar += [p.get("text", "") for p in v.get("belagda_pastaenden", []) or []]
    return "\n".join(delar)


def _tal(obj: Any) -> set[float]:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    s = _BORT.sub(" ", s)
    out = set()
    for x in _NUM.findall(s):
        try:
            out.add(round(float(x.replace(",", ".")), 1))
        except ValueError:
            pass
    return out


def _belagt(n: float, mangd: set[float]) -> bool:
    for b in mangd:
        if abs(b - n) < 0.051 or round(b) == n or abs(b / 60 - n) < 0.051 or abs(b * 60 - n) < 0.6:
            return True
    return False


_PERIOD = re.compile(r"\b(\d+)\s*(?:minut|min\b|timm|tim\b|h\b|dygn|natt|nätter|dag|veck|sekund|s\b|gång|episod)", re.I)


def overifierade_siffror(v: dict[str, Any] | None, refs: dict[str, Any], utlosare: dict[str, Any]) -> list[float]:
    """Siffror i slutbedömningens egen text (sammanfattning, råd, frågor) som inte finns i någon hämtad källa."""
    if not v:
        return []
    mangd = _tal(list(refs.values())) | _tal(utlosare.get("detail", ""))
    text = "\n".join([v.get("sammanfattning", ""), *map(str, v.get("rad", []) or []),
                      *map(str, v.get("fragor_till_varden", []) or [])])
    text = _BORT.sub(" ", text)
    perioder = {float(x) for x in _PERIOD.findall(text)}
    return sorted(n for n in _tal(text) if abs(n) >= 2 and n not in perioder and not _belagt(n, mangd)
                  and n not in (112, 1177))


def baslinjefel(texter: list[str], refs: dict[str, Any]) -> list[str]:
    """Meningar som kallar en siffra 'baslinje' fast siffran inte är ett baslinjevärde i någon källa."""
    bas: set[float] = set()
    for k, r in refs.items():
        if not isinstance(r, dict):
            continue
        if k.startswith("B:"):
            bas |= _tal({x: r.get(x) for x in ("median", "p10", "p90")})
        for nyckel, val in r.items():
            if "baslinje" in nyckel or "normalt" in nyckel:
                bas |= _tal(val)
    fel = []
    for t in texter:
        for men in _meningar(t):
            if not re.search(r"baslinje", men, re.I):
                continue
            tal = [n for n in _tal(men) if abs(n) >= 3 and n not in {float(x) for x in _PERIOD.findall(men)}]
            if tal and not any(_belagt(n, bas) for n in tal):
                fel.append(men)
    return fel


def poang(res: dict[str, Any]) -> dict[str, Any]:
    f = SCENARIO[res["scenario"]].facit
    v = res.get("verdict") or {}
    br = v.get("bradska")
    text = korpus(v)
    lag = text.lower()
    maste = {namn: bool(re.search(rx, lag, re.I)) for namn, rx in f.maste}
    forbjudna = []
    for namn, rx in f.far_ej:
        for men in _meningar(text):
            if re.search(rx, men, re.I) and not NEG.search(men):
                forbjudna.append({"namn": namn, "mening": men})
                break
    idx = NIVAER.index(br) if br in NIVAER else None
    godt = [NIVAER.index(x) for x in f.godtagbar]
    riktning = 0 if idx is None or idx in godt else (1 if idx > max(godt) else -1)
    n_claims = len(res.get("pastaenden", []))
    n_strikes = len(res.get("strykningar", []))
    alla_texter = [c.get("text", "") for c in res.get("pastaenden", [])] + [text]
    return {
        "bradska": br, "facit": f.bradska, "exakt": br == f.bradska, "godtagbar": br in f.godtagbar,
        "overtriage": riktning > 0, "undertriage": riktning < 0,
        "tackning": round(sum(maste.values()) / len(maste), 3), "maste": maste,
        "forbjudna": forbjudna, "pastaenden": n_claims, "strykningar": n_strikes,
        "strykandel": round(n_strikes / n_claims, 3) if n_claims else None,
        "belagda": len(v.get("belagda_pastaenden", []) or []),
        "overifierade_siffror": overifierade_siffror(v, res.get("refs", {}), res.get("utlosare", {})),
        "baslinjefel": baslinjefel(alla_texter, res.get("refs", {})),
        "sekunder": res.get("sekunder"), "prompt_tokens": res["tokens"]["prompt"], "ut_tokens": res["tokens"]["ut"],
        "anrop": res["tokens"]["anrop"],
        "medgemma_anrop": sum(1 for a in res.get("llm_anrop", []) if "medgemma" in a["modell"]),
        "fel": bool(res.get("fel")),
    }


def sammanstall(rader: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rader)
    sek = sorted(r["sekunder"] or 0 for r in rader)
    claims = sum(r["pastaenden"] for r in rader)
    out = {
        "n": n,
        "bradska_godtagbar": round(sum(r["godtagbar"] for r in rader) / n, 3),
        "bradska_exakt": round(sum(r["exakt"] for r in rader) / n, 3),
        "overtriage": sum(r["overtriage"] for r in rader), "undertriage": sum(r["undertriage"] for r in rader),
        "tackning": round(sum(r["tackning"] for r in rader) / n, 3),
        "forbjudna": sum(len(r["forbjudna"]) for r in rader),
        "strykandel": round(sum(r["strykningar"] for r in rader) / claims, 3) if claims else None,
        "belagda_medel": round(sum(r["belagda"] for r in rader) / n, 1),
        "overifierade_siffror": sum(len(r["overifierade_siffror"]) for r in rader),
        "baslinjefel": sum(len(r["baslinjefel"]) for r in rader),
        "sek_median": sek[n // 2], "sek_max": sek[-1], "sek_medel": round(sum(sek) / n, 1),
        "prompt_tokens_medel": round(sum(r["prompt_tokens"] for r in rader) / n),
        "ut_tokens_medel": round(sum(r["ut_tokens"] for r in rader) / n),
        "fel": sum(r["fel"] for r in rader),
    }
    dom = [r["domare"]["poang"] for r in rader if isinstance(r.get("domare"), dict) and r["domare"].get("poang")]
    if dom:
        out["domare_medel"] = round(sum(dom) / len(dom), 2)
    return out
