"""Konsiliet: ett läkarteam av lokala agenter som utreder en avvikelse eller en fråga.

Mötets gång:
  1. Ordföranden (allmänläkare) läser utlösaren och kallar in 2-4 specialister.
  2. Varje specialist utreder vid sitt skrivbord med verktyg (tidsserier, baslinje, sömn, journal,
     provsvar, medicinsk kunskap) och lämnar en bedömning där varje påstående har källor (ref:ar).
  3. Teamet samlas vid bordet och presenterar.
  4. Djävulens advokat letar alternativa, vardagliga förklaringar (träning, kaffe, klockan satt löst).
  5. Ordföranden sammanfattar till en gemensam bedömning.
  6. Granskaren kontrollerar varje påstående: källorna måste vara ref:ar som verkligen returnerats under
     mötet, och varje siffra i påståendet måste finnas i den källans data. Annars stryks påståendet.

Allt sänds som händelser på bussen så att kontoret i webben kan visa teamet arbeta.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from . import db, llm, verktyg
from .bus import bus
from .config import settings

log = logging.getLogger("konsiliet")


@dataclass(frozen=True)
class Lakare:
    id: str
    titel: str
    fokus: str
    verktyg: tuple[str, ...]
    plats: str  # skrivbordet i kontoret


TEAM: dict[str, Lakare] = {l.id: l for l in [
    Lakare("ordforande", "Allmänläkare, ordförande",
           "helhetsbild, prioritering och vad som bör tas upp med vården", (), "skrivbord_ordforande"),
    Lakare("kardiolog", "Kardiolog",
           "puls, vilopuls, pulsvariabilitet (HRV), plötsliga pulshopp, återhämtning efter ansträngning",
           ("hamta_serie", "jamfor_baslinje", "sok_journal", "hamta_labb", "fraga_medgemma"), "skrivbord_kardiolog"),
    Lakare("somn", "Sömnläkare",
           "sömnlängd, sömnfaser, nattlig syremättnad och andning, regelbundenhet",
           ("hamta_somn", "hamta_serie", "jamfor_baslinje", "fraga_medgemma"), "skrivbord_somn"),
    Lakare("idrott", "Idrottsläkare",
           "aktivitet, steg, träningsbelastning, återhämtning, stillasittande",
           ("hamta_serie", "jamfor_baslinje", "hamta_somn", "fraga_medgemma"), "skrivbord_idrott"),
    Lakare("stress", "Stressmedicin",
           "stressbelastning via HRV och vilopuls över dygnet, dygnsrytm, skärmtid och sena kvällar",
           ("hamta_serie", "jamfor_baslinje", "hamta_somn", "sok_journal", "fraga_medgemma"), "skrivbord_stress"),
    Lakare("labb", "Klinisk kemist",
           "provsvar och referensintervall, trender i labbvärden, koppling till symtom",
           ("hamta_labb", "sok_journal", "fraga_medgemma"), "labbet"),
    Lakare("advokat", "Djävulens advokat",
           "vardagliga och tekniska förklaringar: träning, koffein, sjukdom, mätfel, klockan satt löst",
           ("hamta_serie", "hamta_somn"), "skrivbord_advokat"),
    Lakare("granskare", "Faktagranskare", "kontrollerar att varje påstående har giltig källa", (), "granskning"),
]}

SPECIALISTER = ["kardiolog", "somn", "idrott", "stress", "labb"]
MAX_STEG = 4

GEMENSAM = (
    "Du är del av ett läkarteam som granskar EN persons egen hälsodata från en Pixel Watch och journal från 1177. "
    "Personen är 18 år, sitter mycket inne och bygger saker med AI på datorn, och vill börja träna mer. "
    "Regler: Svara på svenska. Ställ inga diagnoser. Varje påstående om personens data MÅSTE ha minst en källa "
    "i form av en ref som ett verktyg har returnerat i det här mötet, och siffror ska skrivas exakt som i verktygsdatan. "
    "Påståenden utan giltig källa stryks av granskaren. Skriv hellre färre, säkra påståenden än många osäkra. "
    "Säg tydligt när datan inte räcker."
)

BEDOMNING_TOOL = {"type": "function", "function": {
    "name": "lamna_bedomning",
    "description": "Lämna din färdiga bedömning. Anropa när du har utrett klart.",
    "parameters": {"type": "object", "properties": {
        "sammanfattning": {"type": "string", "description": "1-3 meningar"},
        "pastaenden": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
            "text": {"type": "string"},
            "kallor": {"type": "array", "items": {"type": "string"}, "description": "ref:ar från verktygen"}},
            "required": ["text", "kallor"]}},
        "osakerhet": {"type": "string", "description": "vad som är osäkert eller saknas"}},
        "required": ["sammanfattning", "pastaenden"]}}}


class Mote:
    def __init__(self, cid: str, trigger: dict[str, Any]) -> None:
        self.id = cid
        self.trigger = trigger
        self.transcript: list[dict[str, Any]] = []
        self.refs: dict[str, dict[str, Any]] = {}  # ref -> verktygsresultat
        self.usage = llm.Usage()
        self.t0 = time.time()

    def emit(self, kind: str, **payload: Any) -> None:
        payload["consult_id"] = self.id
        self.transcript.append({"t": round(time.time() - self.t0, 2), "kind": kind, **payload})
        bus.publish(kind, payload)

    def say(self, agent: str, text: str, to: str = "alla", cites: list[str] | None = None) -> None:
        self.emit("agent.say", agent=agent, to=to, text=text, cites=cites or [])

    def collect_refs(self, result: Any) -> None:
        if isinstance(result, dict):
            if "ref" in result and isinstance(result["ref"], str):
                self.refs[result["ref"]] = result
            for v in result.values():
                self.collect_refs(v)
        elif isinstance(result, list):
            for v in result:
                self.collect_refs(v)


# ---------------------------------------------------------------- specialist

def _utlosare_text(trigger: dict[str, Any]) -> str:
    if trigger.get("kind") == "question":
        return f"Personen frågar: {trigger['question']}"
    return f"Vakten larmade ({trigger.get('level')}): {trigger.get('title')}. {trigger.get('detail')}"


BEDOMNING_SCHEMA = BEDOMNING_TOOL["function"]["parameters"]


def _forhandsdata(m: Mote) -> list[dict[str, Any]]:
    """Datan runt utlösaren hämtas innan specialisterna börjar, så att de har bevis från start."""
    t = m.trigger
    out = []
    # Vaktens larmtext är också en källa: siffrorna i den är uppmätta av vakten.
    if t.get("kind") == "anomaly":
        m.refs["U:utlosare"] = {"ref": "U:utlosare", "titel": t.get("title"), "detalj": t.get("detail")}
        out.append(m.refs["U:utlosare"])
    if t.get("kind") == "anomaly" and t.get("metric"):
        res = verktyg.run("hamta_serie", {"metric": t["metric"], "timmar_bakat": 2})
        m.collect_refs(res)
        out.append(res)
        base = verktyg.run("jamfor_baslinje", {"metric": t["metric"]})
        m.collect_refs(base)
        out.append(base)
        if t["metric"] == "hr":
            steg = verktyg.run("hamta_serie", {"metric": "steps", "timmar_bakat": 2})
            m.collect_refs(steg)
            out.append(steg)
    elif t.get("kind") == "question":
        for metric in ("hr", "hrv_rmssd", "steps"):
            res = verktyg.run("hamta_serie", {"metric": metric, "timmar_bakat": t.get("hours", 72)})
            if res.get("antal"):
                m.collect_refs(res)
                out.append(res)
    return out


def _specialist(m: Mote, lid: str, uppdrag: str, forhand: list[dict[str, Any]]) -> dict[str, Any]:
    lak = TEAM[lid]
    m.emit("agent.move", agent=lid, to=lak.plats)
    msgs: list[dict[str, Any]] = [
        {"role": "system", "content": f"{GEMENSAM}\n\nDu är {lak.titel}. Ditt fokus: {lak.fokus}. "
                                      f"Du har bara dessa verktyg: {', '.join(lak.verktyg)}. Hämta inte samma sak två gånger."},
        {"role": "user", "content": f"{_utlosare_text(m.trigger)}\n\nUppdrag från ordföranden: {uppdrag}\n\n"
                                    f"Data som redan hämtats åt dig:\n{json.dumps(forhand, ensure_ascii=False)}\n\n"
                                    f"Hämta högst {MAX_STEG - 1} saker till om du behöver, och svara sedan med din bedömning."},
    ]
    tools = verktyg.schemas(list(lak.verktyg))
    sett: set[str] = set()
    for _ in range(MAX_STEG - 1):
        m.emit("agent.think", agent=lid)
        r = llm.chat(settings.model_orchestrator, msgs, tools=tools, usage=m.usage)
        msgs.append(r.message)
        if not r.tool_calls:
            break  # agenten anser sig klar
        for tc in r.tool_calls:
            nyckel = tc["name"] + json.dumps(tc["arguments"], sort_keys=True)
            if nyckel in sett:
                res: dict[str, Any] = {"obs": "Du har redan hämtat exakt detta. Använd det du har."}
            else:
                sett.add(nyckel)
                m.emit("agent.tool", agent=lid, tool=tc["name"], args=tc["arguments"])
                if tc["name"] == "sok_journal":
                    m.emit("agent.move", agent=lid, to="arkivet")
                elif tc["name"] == "hamta_labb":
                    m.emit("agent.move", agent=lid, to="labbet")
                res = verktyg.run(tc["name"], tc["arguments"])
                m.collect_refs(res)
            msgs.append({"role": "tool", "tool_name": tc["name"], "content": json.dumps(res, ensure_ascii=False)})
        m.emit("agent.move", agent=lid, to=lak.plats)
    # Slutbedömningen tvingas fram som strukturerad JSON i stället för att hoppas på ett verktygsanrop.
    m.emit("agent.think", agent=lid)
    msgs.append({"role": "user", "content": "Lämna nu din bedömning: sammanfattning max 2 meningar, högst 4 påståenden "
                                            "på max 25 ord vardera. Varje påstående ska ha källor i form av ref:ar "
                                            f"ur datan ovan. Giltiga ref:ar: {', '.join(sorted(m.refs))}"})
    r = llm.chat(settings.model_orchestrator, msgs, fmt=BEDOMNING_SCHEMA, usage=m.usage)
    try:
        return json.loads(r.content)
    except json.JSONDecodeError:
        return {"sammanfattning": r.content.strip()[:500], "pastaenden": [], "osakerhet": "ej strukturerat svar"}


# ---------------------------------------------------------------- granskaren

_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")
_KLOCKA = re.compile(r"\b\d{1,2}[:.]\d{2}\b")        # 16:10, kontrolleras separat
_DATUM = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_PERIOD = re.compile(r"\b(\d+)\s*(?:minut|min\b|timm|tim\b|h\b|dygn|natt|nätter|dag|veck|sekund|s\b)", re.I)


def _numbers(obj: Any) -> set[float]:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    s = _DATUM.sub(" ", _KLOCKA.sub(" ", s))
    out = set()
    for x in _NUM.findall(s):
        try:
            out.add(round(float(x.replace(",", ".")), 1))
        except ValueError:
            pass
    return out


def _belagd(n: float, belagda: set[float]) -> bool:
    """Ett tal är belagt om det finns i källan, eller är en enkel enhetsomräkning av ett som finns
    (minuter <-> timmar, avrundning till heltal)."""
    if n in belagda:
        return True
    for b in belagda:
        if abs(b - n) < 0.051 or round(b) == n:
            return True
        if abs(b / 60 - n) < 0.051 or abs(b * 60 - n) < 0.6:
            return True
    return False


def granska(m: Mote, agent: str, bed: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministisk kontroll. Ingen språkmodell kan prata sig förbi den."""
    godkanda = []
    for p in bed.get("pastaenden", []) or []:
        text = str(p.get("text", "")).strip()
        kallor = [k for k in (p.get("kallor") or []) if isinstance(k, str)]
        if not text:
            continue
        giltiga = [k for k in kallor if k in m.refs]
        skal = None
        if not kallor:
            skal = "saknar källa"
        elif not giltiga:
            skal = f"källan {kallor[0]} finns inte bland det teamet faktiskt hämtat"
        else:
            belagda = set().union(*(_numbers(m.refs[k]) for k in giltiga), _numbers(m.refs.get("U:utlosare", {})))
            # Perioder ("senaste 24 timmarna", "10 minuter") är frågans ramar, inte mätvärden.
            perioder = {float(x) for x in _PERIOD.findall(text)}
            pastadda = {n for n in _numbers(text) if n not in perioder}
            saknas = [n for n in pastadda if abs(n) >= 3 and not _belagd(n, belagda)]
            if saknas:
                skal = f"siffran {saknas[0]:g} finns inte i källdatan"
        if skal:
            m.emit("review.strike", agent="granskare", target=agent, claim=text, reason=skal)
        else:
            godkanda.append({"text": text, "kallor": giltiga, "av": agent})
    return godkanda


# ---------------------------------------------------------------- mötet

def _ordforande_val(m: Mote) -> list[tuple[str, str]]:
    beskr = "\n".join(f"- {i}: {TEAM[i].titel} ({TEAM[i].fokus})" for i in SPECIALISTER)
    tool = {"type": "function", "function": {
        "name": "kalla_in", "description": "Kalla in specialister med var sitt uppdrag.",
        "parameters": {"type": "object", "properties": {"specialister": {"type": "array", "items": {
            "type": "object", "properties": {"id": {"type": "string", "enum": SPECIALISTER},
                                             "uppdrag": {"type": "string"}}, "required": ["id", "uppdrag"]}}},
            "required": ["specialister"]}}}
    m.emit("agent.think", agent="ordforande")
    r = llm.chat(settings.model_orchestrator, [
        {"role": "system", "content": f"{GEMENSAM}\n\nDu är allmänläkare och ordförande. Välj 2-4 specialister "
                                      f"som är relevanta och ge var och en ett konkret uppdrag.\n\nTeamet:\n{beskr}"},
        {"role": "user", "content": _utlosare_text(m.trigger)}], tools=[tool], usage=m.usage)
    val = []
    for tc in r.tool_calls:
        for s in tc["arguments"].get("specialister", []):
            if s.get("id") in SPECIALISTER and s["id"] not in [v[0] for v in val]:
                val.append((s["id"], s.get("uppdrag", "")))
    if len(val) < 2:  # modellen svarade inte strukturerat: rimlig standard utifrån mätvärdet
        metric = m.trigger.get("metric", "")
        std = {"hr": ["kardiolog", "stress"], "hrv_rmssd": ["stress", "kardiolog", "idrott"],
               "spo2": ["somn", "kardiolog"], "resp_rate": ["somn", "kardiolog"]}.get(metric, ["kardiolog", "somn", "idrott"])
        val = [(s, "Utred utlösaren utifrån ditt område.") for s in std]
    return val[:4]


def _advokat(m: Mote, bedomningar: dict[str, dict[str, Any]]) -> str:
    m.emit("agent.think", agent="advokat")
    sammandrag = "\n".join(f"{TEAM[k].titel}: {v.get('sammanfattning', '')}" for k, v in bedomningar.items())
    r = llm.chat(settings.model_orchestrator, [
        {"role": "system", "content": f"{GEMENSAM}\n\nDu är djävulens advokat. Ifrågasätt teamet med vardagliga "
                                      "och tekniska förklaringar. Max 3 korta punkter, ingen inledning."},
        {"role": "user", "content": f"{_utlosare_text(m.trigger)}\n\nTeamets bedömningar:\n{sammandrag}"}],
        usage=m.usage)
    return r.content.strip()


SLUTSATS_SCHEMA = {"type": "object", "properties": {
    "sammanfattning": {"type": "string", "description": "max 3 meningar"},
    "bradska": {"type": "string", "enum": ["ingen", "bevaka", "ta_upp_med_varden", "kontakta_vard_nu"]},
    "rad": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
    "fragor_till_varden": {"type": "array", "maxItems": 4, "items": {"type": "string"}}},
    "required": ["sammanfattning", "bradska", "rad", "fragor_till_varden"]}


def _slutsats(m: Mote, godkanda: list[dict[str, Any]], invand: str) -> dict[str, Any]:
    m.emit("agent.move", agent="ordforande", to="tavlan")
    m.emit("agent.think", agent="ordforande")
    fakta = "\n".join(f"- {p['text']} [{', '.join(p['kallor'])}]" for p in godkanda) or "- (inga belagda påståenden)"
    r = llm.chat(settings.model_orchestrator, [
        {"role": "system", "content": f"{GEMENSAM}\n\nDu är ordförande. Bygg slutbedömningen ENBART på de "
                                      "granskade påståendena nedan. Väg in advokatens invändningar. Råden ska vara "
                                      "konkreta och korta."},
        {"role": "user", "content": f"{_utlosare_text(m.trigger)}\n\nGranskade påståenden:\n{fakta}\n\n"
                                    f"Advokatens invändningar:\n{invand}"}], fmt=SLUTSATS_SCHEMA, usage=m.usage)
    try:
        return json.loads(r.content)
    except json.JSONDecodeError:
        return {"sammanfattning": r.content.strip()[:600] or "Teamet kunde inte enas.", "bradska": "bevaka", "rad": []}


def _kor(m: Mote) -> None:
    with db.tx() as c:
        c.execute("INSERT INTO consults(id, started, trigger) VALUES (?,?,?)",
                  (m.id, m.t0, json.dumps(m.trigger, ensure_ascii=False)))
    m.emit("consult.start", trigger=m.trigger, members=list(TEAM))
    m.emit("agent.move", agent="ordforande", to="bordet")

    val = _ordforande_val(m)
    for lid, uppdrag in val:
        m.say("ordforande", f"{TEAM[lid].titel}: {uppdrag}", to=lid)

    forhand = _forhandsdata(m)
    bedomningar: dict[str, dict[str, Any]] = {}
    for lid, uppdrag in val:  # en i taget: 16 GB räcker inte för parallella modellinstanser
        bedomningar[lid] = _specialist(m, lid, uppdrag, forhand)

    godkanda: list[dict[str, Any]] = []
    for lid, bed in bedomningar.items():
        m.emit("agent.move", agent=lid, to="bordet")
        m.say(lid, bed.get("sammanfattning", ""), cites=[k for p in bed.get("pastaenden", []) or []
                                                          for k in (p.get("kallor") or [])][:6])
        m.emit("agent.handoff", agent=lid, to="granskare", item="bedömning")
        godkanda += granska(m, lid, bed)

    m.emit("agent.move", agent="advokat", to="bordet")
    invand = _advokat(m, bedomningar)
    m.say("advokat", invand)

    verdict = _slutsats(m, godkanda, invand)
    verdict["belagda_pastaenden"] = godkanda
    m.say("ordforande", verdict.get("sammanfattning", ""), cites=sorted({k for p in godkanda for k in p["kallor"]})[:8])
    m.emit("consult.verdict", verdict=verdict)

    stats = {**m.usage.as_dict(), "sekunder_totalt": round(time.time() - m.t0, 1),
             "modeller": [settings.model_orchestrator, settings.model_specialist]}
    with db.tx() as c:
        c.execute("UPDATE consults SET ended=?, transcript=?, verdict=?, stats=? WHERE id=?",
                  (time.time(), json.dumps(m.transcript, ensure_ascii=False),
                   json.dumps(verdict, ensure_ascii=False), json.dumps(stats), m.id))
    if verdict.get("bradska") in ("ta_upp_med_varden", "kontakta_vard_nu"):
        bus.publish("alert.raise", {"level": "akut" if verdict["bradska"] == "kontakta_vard_nu" else "avvikelse",
                                    "title": "Konsiliet har en bedömning", "body": verdict.get("sammanfattning", ""),
                                    "consult_id": m.id})


# ---------------------------------------------------------------- kö

_q: "queue.Queue[Mote]" = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _worker() -> None:
    while True:
        m = _q.get()
        try:
            _kor(m)
        except Exception as e:
            log.exception("konsiliet kraschade")
            m.emit("consult.verdict", verdict={"sammanfattning": f"Mötet avbröts av ett fel: {e}",
                                               "bradska": "bevaka", "rad": [], "fel": True})


def start_async(trigger: dict[str, Any]) -> str:
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            threading.Thread(target=_worker, name="konsiliet", daemon=True).start()
            _worker_started = True
    m = Mote(uuid.uuid4().hex[:12], trigger)
    _q.put(m)
    return m.id
