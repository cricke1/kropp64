"""Konsiliet: ett läkarteam av lokala agenter som utreder en avvikelse eller en fråga.

Mötets gång:
  0. Faktabladet räknas fram deterministiskt (fakta.py): observerat mot baslinje, kvalitetskontroller,
     nätter, dygn, provsvar, journal. Varje del har en ref. Regelverket föreslår en brådska.
  1. Ordföranden (allmänläkare) läser utlösaren och faktabladet och kallar in 2-4 specialister.
  2. Varje specialist lämnar en bedömning där varje påstående har källor (ref:ar). Källorna är låsta till
     ref:ar som verkligen finns i mötet (JSON-schema), och kan kompletteras med egna verktygsuppslag.
  3. Teamet samlas vid bordet och presenterar. Granskaren kontrollerar varje påstående.
  4. Djävulens advokat letar vardagliga och tekniska förklaringar, med källor. Teamet bemöter dem.
  5. Ordföranden skriver slutbedömningen. Brådskan styrs av regelverket (se LAGE), och spärras: bara en
     akut vaktregel kan leda till "kontakta_vard_nu".
  6. Granskaren kontrollerar även slutbedömningens egen text. Allt sparas med bevisen (m.refs).

Allt sänds som händelser på bussen så att kontoret i webben kan visa teamet arbeta.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from . import db, fakta, llm, matning, verktyg
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
    tumregler: str = ""


TEAM: dict[str, Lakare] = {l.id: l for l in [
    Lakare("ordforande", "Allmänläkare, ordförande",
           "helhetsbild, prioritering och vad som bör tas upp med vården", (), "skrivbord_ordforande"),
    Lakare("kardiolog", "Kardiolog",
           "puls, vilopuls, pulsvariabilitet (HRV), plötsliga pulshopp, återhämtning efter ansträngning",
           ("hamta_serie", "jamfor_baslinje", "sok_journal", "hamta_labb"), "skrivbord_kardiolog",
           "Hög puls under träningspass eller med många steg är träningspuls, inte sjukdom. Isolerade enstaka "
           "spikar (ett värde över 130 med grannar under 100) är mätfel. Många hopp över 25 slag mellan minuter "
           "och saknade minuter betyder att klockan sitter löst. Puls som slår om plötsligt (stor ökning på 2 "
           "minuter) till över 140 i vila och sedan slutar tvärt kan vara en rytmrubbning: EKG under episod "
           "behövs. Stigande nattpuls och fallande HRV flera nätter tyder på belastning eller begynnande infektion."),
    Lakare("somn", "Sömnläkare",
           "sömnlängd, insomningstid, nattlig syremättnad och andning, regelbundenhet",
           ("hamta_somn", "hamta_serie", "jamfor_baslinje"), "skrivbord_somn",
           "En 18-åring behöver 7-9 timmar sömn. Sen skärmtid (datorminuter efter 23) skjuter insomningen. "
           "Minst 5 syrefall per timme flera nätter är ett mönster som vid andningsuppehåll i sömnen och bör "
           "utredas av vården (inte akut). Enstaka fall en natt kan vara mätfel eller sovställning."),
    Lakare("idrott", "Idrottsläkare",
           "aktivitet, steg, träningsbelastning, återhämtning, stillasittande",
           ("hamta_serie", "jamfor_baslinje", "hamta_somn"), "skrivbord_idrott",
           "Hårda pass sänker HRV en till två nätter efteråt; det är normal belastning om temperatur och andning "
           "är normala. Jämför steg mot personens baslinje. Ge konkreta, små råd (promenad, vilodag, lätt pass)."),
    Lakare("stress", "Stressmedicin",
           "stressbelastning via HRV och vilopuls över dygnet, dygnsrytm, skärmtid och sena kvällar",
           ("hamta_serie", "jamfor_baslinje", "hamta_somn", "sok_journal"), "skrivbord_stress",
           "Låg HRV och högre puls dygnet runt tillsammans med långa datorpass och kort sömn tyder på belastning. "
           "Ställ inga psykiatriska diagnoser. Råd: pauser, rörelse, fast läggtid."),
    Lakare("labb", "Klinisk kemist",
           "provsvar och referensintervall, trender i labbvärden, koppling till symtom",
           ("hamta_labb", "sok_journal"), "labbet",
           "Utgå från fältet bedomning_mot_referens. Ferritin under referens betyder tömda järnförråd och kan ge "
           "trötthet även när Hb är normalt; det är inte anemi om Hb ligger inom referens. Provsvar utanför "
           "referens ska tas upp med vården."),
    Lakare("advokat", "Djävulens advokat",
           "vardagliga och tekniska förklaringar: träning, koffein, sjukdom, mätfel, klockan satt löst", (),
           "skrivbord_advokat"),
    Lakare("granskare", "Faktagranskare", "kontrollerar att varje påstående har giltig källa", (), "granskning"),
]}

SPECIALISTER = ["kardiolog", "somn", "idrott", "stress", "labb"]
NIVAER = fakta.NIVAER
# Verktyg som visas i kontoret när faktabladets delar läses (de är förhämtade av systemet, forhamtat=True)
DEL_TILL_VERKTYG = {"F:larm": ("hamta_serie", "metric"), "F:puls": ("hamta_serie", "hr"), "F:natter": ("hamta_somn", None),
                    "F:dagar": ("hamta_serie", "steps"), "F:prover": ("hamta_labb", None),
                    "F:journal": ("sok_journal", None), "F:aktivitet": ("jamfor_baslinje", "steps")}


def lage() -> dict[str, Any]:
    """Mötets inställningar. Standardvärdena är de som vann utvärderingen (eval/RESULTAT.md)."""
    e = os.environ.get
    return {
        "bradska": e("KONSILIET_LAGE_BRADSKA", "hybrid"),     # regel | hybrid | fri
        "verktygsrundor": int(e("KONSILIET_LAGE_VERKTYGSRUNDOR", "0")),
        "diskussion": e("KONSILIET_LAGE_DISKUSSION", "1") == "1",
        "think": e("KONSILIET_LAGE_THINK", "0") == "1",       # tänkande för slutbedömningen
        "medgemma": e("KONSILIET_LAGE_MEDGEMMA", "0") == "1",
        "temperatur": float(e("KONSILIET_LAGE_TEMP", "0.2")),
        "max_specialister": int(e("KONSILIET_LAGE_MAX_SPEC", "3")),
        "tolkning": e("KONSILIET_LAGE_TOLKNING", "1") == "1",  # regelverkets tolkning som källa F:tolkning
    }


def _gemensam() -> str:
    return (
        "Du är del av ett läkarteam som granskar EN persons egen hälsodata från en Pixel Watch och journal från 1177. "
        f"Om personen: {settings.profil}. "
        "Regler: Svara på svenska. Ställ inga diagnoser, beskriv mönster och vad de kan tyda på. Varje påstående om "
        "personens data MÅSTE ha minst en källa i form av en ref ur faktabladet eller ett verktygssvar i mötet. "
        "Skriv siffror exakt som i källan och säg vilket fält de kommer från. Fält som börjar med observerat_ är det "
        "som mättes nu; fält med baslinje_ är personens normala nivå; skillnad_ är differensen. Kalla ALDRIG ett "
        "observerat värde för baslinje. Ange som källa den ref där siffran faktiskt står (raden i faktabladet). "
        "F:tolkning är regelverkets deterministiska tolkning (t.ex. mätfel eller träning) och väger tungt. "
        "Räkna inte om siffror själv (inga egna procent eller medelvärden), använd "
        "de färdiga skillnad-fälten. Påståenden utan giltig källa eller med siffror som inte finns i källan stryks "
        "av granskaren. Skriv hellre färre, säkra påståenden än många osäkra. Säg tydligt när datan inte räcker."
    )


def _faktatext(fa: dict[str, dict[str, Any]]) -> str:
    return "\n".join(json.dumps(v, ensure_ascii=False, separators=(",", ":")) for v in fa.values())


class Mote:
    def __init__(self, cid: str, trigger: dict[str, Any]) -> None:
        self.id = cid
        self.trigger = trigger
        self.transcript: list[dict[str, Any]] = []
        self.refs: dict[str, dict[str, Any]] = {}  # ref -> verktygsresultat
        self.usage = llm.Usage()
        self.t0 = time.time()
        self.fakta: dict[str, dict[str, Any]] = {}
        self.lage = lage()
        self.regel: tuple[str, list[str]] = ("bevaka", [])

    def emit(self, kind: str, **payload: Any) -> None:
        payload["consult_id"] = self.id
        self.transcript.append({"t": round(time.time() - self.t0, 2), "kind": kind, **payload})
        bus.publish(kind, payload)

    def say(self, agent: str, text: str, to: str = "alla", cites: list[str] | None = None, **extra: Any) -> None:
        self.emit("agent.say", agent=agent, to=to, text=text, cites=cites or [], **extra)

    def collect_refs(self, result: Any) -> None:
        if isinstance(result, dict):
            if "ref" in result and isinstance(result["ref"], str):
                self.refs[result["ref"]] = result
            for v in result.values():
                self.collect_refs(v)
        elif isinstance(result, list):
            for v in result:
                self.collect_refs(v)

    def system(self) -> str:
        """Samma systemprompt för alla anrop i mötet, så att Ollama kan återanvända den inlästa prefixen."""
        return f"{_gemensam()}\n\nUTLÖSARE: {_utlosare_text(self.trigger)}\n\nFAKTABLAD (en källa per rad):\n{_faktatext(self.fakta)}"

    def chat(self, messages: list[dict[str, Any]], **kw: Any) -> llm.Reply:
        kw.setdefault("temperature", self.lage["temperatur"])
        return llm.chat(settings.model_orchestrator, [{"role": "system", "content": self.system()}, *messages],
                        usage=self.usage, **kw)


def _utlosare_text(trigger: dict[str, Any]) -> str:
    if trigger.get("kind") == "question":
        return f"Personen frågar: {trigger['question']}"
    return f"Vakten larmade ({trigger.get('level')}): {trigger.get('title')}. {trigger.get('detail')}"


def _json(r: llm.Reply, reserv: dict[str, Any]) -> dict[str, Any]:
    try:
        d = json.loads(r.content)
        return d if isinstance(d, dict) else reserv
    except json.JSONDecodeError:
        return reserv


def _kallschema(m: Mote, max_items: int = 4) -> dict[str, Any]:
    return {"type": "array", "maxItems": max_items, "items": {"type": "object", "properties": {
        "text": {"type": "string"},
        "kallor": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": sorted(m.refs)}}},
        "required": ["text", "kallor"]}}


# ---------------------------------------------------------------- förberedelse

def _forbered(m: Mote) -> None:
    with matning.tid("Faktablad"):
        m.fakta = fakta.faktaark(m.trigger)
    if m.trigger.get("kind") == "anomaly":
        m.refs["U:utlosare"] = {"ref": "U:utlosare", "metric": m.trigger.get("metric"), "titel": m.trigger.get("title"),
                                "detalj": m.trigger.get("detail")}
    m.regel = fakta.regelbradska(m.trigger, m.fakta)
    # Regelverkets tolkning blir en egen källa, så att teamet kan peka på den (t.ex. "ser ut som mätfel").
    if m.lage["tolkning"]:
        m.fakta["F:tolkning"] = {"ref": "F:tolkning", "beskrivning": "deterministiska regler, inte en språkmodell",
                                 "brådska_enligt_regler": m.regel[0], "skal": m.regel[1] or ["inga regler slog till"]}
    m.collect_refs(m.fakta)
    if m.lage["medgemma"]:
        # Bakgrundskunskap från den medicinska modellen, en gång per möte. Ingen ref: kunskap, inte data.
        m.emit("agent.tool", agent="ordforande", tool="fraga_medgemma", args={"fraga": _utlosare_text(m.trigger)})
        res = verktyg.run("fraga_medgemma", {"fraga": f"{_utlosare_text(m.trigger)} Vilka vanliga och vilka allvarliga "
                                             "orsaker finns hos en ung vuxen, och vilka varningstecken kräver vård?"})
        m.fakta["K:medgemma"] = {"ref": "K:medgemma", "kalla": res.get("kalla"), "bakgrund": res.get("svar", "")}


# ---------------------------------------------------------------- specialist

BEDOMNING_TOOL = {"type": "function", "function": {
    "name": "lamna_bedomning", "description": "Lämna din färdiga bedömning.",
    "parameters": {"type": "object", "properties": {
        "sammanfattning": {"type": "string"}, "pastaenden": {"type": "array"}, "osakerhet": {"type": "string"}},
        "required": ["sammanfattning", "pastaenden"]}}}


def _bedomningsschema(m: Mote) -> dict[str, Any]:
    return {"type": "object", "properties": {
        "sammanfattning": {"type": "string", "description": "1-2 meningar"},
        "pastaenden": _kallschema(m, 3),
        "bradska_forslag": {"type": "string", "enum": NIVAER},
        "osakerhet": {"type": "string"}},
        "required": ["sammanfattning", "pastaenden", "bradska_forslag", "osakerhet"]}


def _visa_uppslag(m: Mote, lid: str) -> None:
    """Kontoret visar läkaren slå upp de delar av faktabladet som rör hens område."""
    lak = TEAM[lid]
    for ref, (tool, arg) in DEL_TILL_VERKTYG.items():
        if ref in m.fakta and tool in lak.verktyg:
            args: dict[str, Any] = {}
            if arg == "metric":
                args["metric"] = m.trigger.get("metric")
            elif arg:
                args["metric"] = arg
            m.emit("agent.tool", agent=lid, tool=tool, args=args, forhamtat=True, ref=ref)
            if tool == "sok_journal":
                m.emit("agent.move", agent=lid, to="arkivet")
            elif tool == "hamta_labb":
                m.emit("agent.move", agent=lid, to="labbet")
    m.emit("agent.move", agent=lid, to=lak.plats)


def _specialist(m: Mote, lid: str, uppdrag: str) -> dict[str, Any]:
    lak = TEAM[lid]
    m.emit("agent.move", agent=lid, to=lak.plats)
    _visa_uppslag(m, lid)
    msgs: list[dict[str, Any]] = [{"role": "user", "content":
        f"Du är {lak.titel}. Ditt fokus: {lak.fokus}.\nTumregler: {lak.tumregler}\n\nUppdrag från ordföranden: {uppdrag}"}]
    rundor = m.lage["verktygsrundor"]
    if rundor:
        msgs[0]["content"] += (f"\n\nFaktabladet räcker oftast. Behöver du något mer kan du använda verktygen "
                               f"({', '.join(lak.verktyg)}) högst {rundor} gång(er); annars svara direkt utan verktyg.")
        tools = verktyg.schemas([t for t in lak.verktyg if t != "fraga_medgemma" or m.lage["medgemma"]])
        sett: set[str] = set()
        for _ in range(rundor):
            m.emit("agent.think", agent=lid)
            with matning.tid("Specialist, per modellanrop"):
                r = m.chat(msgs, tools=tools, max_tokens=300)
            msgs.append(r.message)
            if not r.tool_calls:
                break
            for tc in r.tool_calls[:2]:
                nyckel = tc["name"] + json.dumps(tc["arguments"], sort_keys=True)
                if nyckel in sett:
                    res: dict[str, Any] = {"obs": "Redan hämtat."}
                else:
                    sett.add(nyckel)
                    m.emit("agent.tool", agent=lid, tool=tc["name"], args=tc["arguments"])
                    res = verktyg.run(tc["name"], tc["arguments"])
                    m.collect_refs(res)
                msgs.append({"role": "tool", "tool_name": tc["name"], "content": json.dumps(res, ensure_ascii=False)})
            m.emit("agent.move", agent=lid, to=lak.plats)
    m.emit("agent.think", agent=lid)
    msgs.append({"role": "user", "content": "Lämna nu din bedömning som JSON: sammanfattning EN mening, högst 3 "
                 "påståenden på max 20 ord vardera, varje påstående med källor (ref:ar), osäkerhet max 15 ord. Föreslå brådska: ingen, bevaka, "
                 "ta_upp_med_varden eller kontakta_vard_nu (bara vid akut fara nu)."})
    with matning.tid("Specialist, per modellanrop"):
        r = m.chat(msgs, fmt=_bedomningsschema(m), max_tokens=700)
    return _json(r, {"sammanfattning": r.content.strip()[:500], "pastaenden": [], "osakerhet": "ej strukturerat svar"})


# ---------------------------------------------------------------- granskaren

_NUM = re.compile(r"(?<![A-Za-zÅÄÖåäöµ\d])-?\d+(?:[.,]\d+)?")
_TUSEN = re.compile(r"(?<=\d)[ \u00a0](?=\d{3}\b)")  # 13 148 -> 13148
_KLOCKA = re.compile(r"\b\d{1,2}[:.]\d{2}\b")
_DATUM = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_REF = re.compile(r"\b[SBNJLUFK]:[\w:.\-]+")
_PERIOD = re.compile(r"(?<![\d.,])(\d+)\s*(?:minut|min\b|timm|tim\b|h\b|dygn|natt|nätter|dag|veck|sekund|s\b|gång|episod|"
                     r"tillfäll|år\b|månad|påstående)", re.I)
_UNDANTAG = {112.0, 1177.0}

FAMILJ_NYCKEL = [("hrv", ("hrv",)), ("spo2", ("spo2", "syre")), ("andning", ("andning", "resp")),
                 ("temp", ("temp",)), ("steg", ("steg", "steps")), ("somn", ("somn",)),
                 ("puls", ("puls", "hr", "slag")), ("tid", ("minut", "_min", "timmar", "tim_"))]
METRIC_FAMILJ = {"hr": "puls", "resting_hr": "puls", "hrv_rmssd": "hrv", "spo2": "spo2", "resp_rate": "andning",
                 "skin_temp": "temp", "steps": "steg"}
ENHET_FAMILJ = [(re.compile(r"^\s*(slag|bpm)", re.I), "puls"), (re.compile(r"^\s*(ms\b|millisek)", re.I), "hrv"),
                (re.compile(r"^\s*steg", re.I), "steg"), (re.compile(r"^\s*(°|grader)", re.I), "temp"),
                (re.compile(r"^\s*andetag", re.I), "andning"), (re.compile(r"^\s*procentenhet", re.I), "spo2"),
                (re.compile(r"^\s*(minut|min\b|timm|tim\b|h\b)", re.I), "tid")]
# Medicinska slutsatser kräver en källa av rätt typ, även utan siffror.
SLUTSATSER = [
    (re.compile(r"infektion|förkyl|virus|feber", re.I), {"temp", "hrv", "puls", "andning", "journal"}),
    (re.compile(r"sömnapn|andningsuppeh|andningsstörning", re.I), {"spo2", "andning"}),
    (re.compile(r"järnbrist|järnförråd|anemi|blodbrist|ferritin", re.I), {"labb"}),
    (re.compile(r"arytmi|takykardi|hjärtrusning|förmaksflimmer|rytmrubbning|\bsvt\b", re.I), {"puls"}),
    (re.compile(r"mätfel|artefakt|sitter löst|sensorfel|felmätning", re.I), {"puls", "spo2"}),
    (re.compile(r"astma", re.I), {"journal"}),
    (re.compile(r"sömnbrist|för lite sömn|kort sömn|sover för lite", re.I), {"somn"}),
]


# En period ("senaste 3 nätterna", "10 minuter") är frågans ram, inte ett mätvärde, men bara om den är
# rimligt liten: "4525 minuter vid datorn" på ett dygn är ett påstående som ska kontrolleras.
PERIOD_MAX = [(re.compile(r"^(sekund|s$|min)", re.I), 60), (re.compile(r"^(timm|tim$|h$)", re.I), 72),
              (re.compile(r"^(dygn|natt|nätter|dag)", re.I), 31), (re.compile(r"^(veck|månad)", re.I), 12),
              (re.compile(r"^år", re.I), 120)]
_PERIOD_ORD = re.compile(r"(?<![\d.,])(\d+)\s*(minut\w*|min\b|timm\w*|tim\b|h\b|dygn\w*|natt\w*|nätter\w*|dag\w*|"
                         r"veck\w*|sekund\w*|s\b|gång\w*|episod\w*|tillfäll\w*|år\b|månad\w*|påstående\w*)", re.I)


def _perioder(text: str) -> set[float]:
    out = set()
    for tal, ord_ in _PERIOD_ORD.findall(text):
        n = float(tal)
        grans = next((g for rx, g in PERIOD_MAX if rx.match(ord_)), 20)
        if n <= grans:
            out.add(n)
    return out


def _familj_nyckel(k: str) -> str | None:
    k = k.lower()
    for fam, toks in FAMILJ_NYCKEL:
        if any(t in k for t in toks):
            return fam
    return None


def _tal_text(s: str) -> list[float]:
    s = _TUSEN.sub("", _REF.sub(" ", s))
    s = _DATUM.sub(" ", _KLOCKA.sub(" ", s))
    out = []
    for x in _NUM.findall(s):
        try:
            out.append(round(float(x.replace(",", ".")), 1))
        except ValueError:
            pass
    return out


TID_ORD = ("minut", "_min", "timmar", "tim_", "total_min")


def _samla(obj: Any, fam: str | None, ut: dict[str, set[float]], bas: set[float], i_bas: bool = False,
           i_tid: bool = False) -> None:
    """Alla tal i en källa, grupperade per mätvärdesfamilj. Ref-strängar och tidsstämplar räknas inte.
    Tal under fältnamn som anger tid (minuter, timmar) hamnar dessutom i familjen "tid"."""
    def lagg(v: float, f: str | None) -> None:
        ut.setdefault(f or "okand", set()).add(v)
        ut.setdefault("alla", set()).add(v)
        if i_tid:
            ut.setdefault("tid", set()).add(v)

    if isinstance(obj, dict):
        egen = METRIC_FAMILJ.get(str(obj.get("metric") or obj.get("matvarde") or "")) or fam
        for k, v in obj.items():
            if k == "ref":
                continue
            kb = i_bas or "baslinje" in k or "normalt" in k
            kt = i_tid or any(t in k.lower() for t in TID_ORD)
            fk = _familj_nyckel(k)
            kf = fk if fk not in (None, "tid") else (egen or fk)
            _samla(v, kf, ut, bas, kb, kt)
            for tal in _tal_text(k.replace("_", " ")):  # gränser i fältnamnet, t.ex. minuter_over_140
                ut.setdefault(kf or "okand", set()).add(tal)
                ut.setdefault("alla", set()).add(tal)
    elif isinstance(obj, list):
        for v in obj:
            _samla(v, fam, ut, bas, i_bas, i_tid)
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        if abs(obj) >= 1e8:  # unix-tidsstämpel
            return
        v = round(float(obj), 1)
        lagg(v, fam)
        if i_bas:
            bas.add(v)
    elif isinstance(obj, str):
        tal = _tal_text(obj)
        for v in tal:
            lagg(v, fam)
        if i_bas:
            bas.update(tal)
        for mt in re.finditer(r"normalt\s+(-?\d+(?:[.,]\d+)?)", obj):
            bas.add(round(float(mt.group(1).replace(",", ".")), 1))


def _kallinfo(ref: str, data: dict[str, Any]) -> tuple[dict[str, set[float]], set[float], set[str]]:
    """Tal per familj, baslinjetal och vilka familjer källan handlar om."""
    typ, _, rest = ref.partition(":")
    fam0 = METRIC_FAMILJ.get(rest.split(":")[0]) if typ in ("S", "B") else (_familj_nyckel(rest) if typ == "F" else None)
    ut: dict[str, set[float]] = {}
    bas: set[float] = set()
    if typ == "B":
        _samla({k: v for k, v in data.items() if k in ("median", "p10", "p90", "sd")}, fam0, {}, bas, True)
    _samla(data, fam0, ut, bas)
    fam = {f for f in ut if f not in ("alla", "okand")}
    if fam0:
        fam.add(fam0)
    if typ == "N":
        fam.add("somn")
    if typ == "L" or "L:" in json.dumps(data, ensure_ascii=False):
        fam.add("labb")
    if typ == "J" or "J:" in json.dumps(data, ensure_ascii=False):
        fam.add("journal")
    if typ in ("F",) and ref == "F:natter":
        fam.add("somn")
    return ut, bas, fam


_NER = re.compile(r"(sjunk\w*|minsk\w*|gått ner|fallit|föll|lägre|sänk\w*)\s+(med\s+)?(cirka\s+|ca\s+)?$", re.I)
_UPP = re.compile(r"(ök\w*|stig\w*|steg|höj\w*|högre)\s+(med\s+)?(cirka\s+|ca\s+)?$", re.I)
_NER_EFTER = re.compile(r"^\s*(%|[\w/°]+)?\s*(lägre|mindre|färre|under baslinjen|under det normala)", re.I)
_UPP_EFTER = re.compile(r"^\s*(%|[\w/°]+)?\s*(högre|mer|fler|över baslinjen|över det normala)", re.I)


def _riktning(ren: str, start: int, slut: int) -> int:
    """-1 om talet beskrivs som en minskning ("sjunkit med 4", "4 ms lägre"), +1 för ökning, annars 0."""
    fore, efter = ren[max(0, start - 30):start], ren[slut:slut + 30]
    if _NER.search(fore) or _NER_EFTER.match(efter):
        return -1
    if _UPP.search(fore) or _UPP_EFTER.match(efter):
        return 1
    return 0


def _belagd(n: float, belagda: set[float]) -> bool:
    """Belagt om talet finns i källan, eller är en enkel omräkning (avrundning, minuter <-> timmar, tecken)."""
    for b in belagda:
        for x in (b, abs(b)):
            if abs(x - n) < 0.051 or round(x) == n or round(x, 0) == round(n, 0) and abs(x - n) < 0.5:
                return True
            if abs(x / 60 - n) < 0.051 or abs(x * 60 - n) < 0.6:
                return True
    return False


def kontrollera(text: str, kallor: list[str], refs: dict[str, dict[str, Any]], trigger_metric: str | None = None) -> str | None:
    """Returnerar skälet att stryka, eller None om påståendet håller."""
    if not kallor:
        return "saknar källa"
    giltiga = [k for k in kallor if k in refs]
    if not giltiga:
        return f"källan {kallor[0]} finns inte bland det teamet faktiskt hämtat"
    per_fam: dict[str, set[float]] = {}
    bas: set[float] = set()
    familjer: set[str] = set()
    for k in giltiga:
        ut, b, fam = _kallinfo(k, refs[k])
        if k == "U:utlosare" and trigger_metric in METRIC_FAMILJ:
            fam.add(METRIC_FAMILJ[trigger_metric])
            ut.setdefault(METRIC_FAMILJ[trigger_metric], set()).update(ut.get("alla", set()))
        for f, s in ut.items():
            per_fam.setdefault(f, set()).update(s)
        bas |= b
        familjer |= fam
    alla = per_fam.get("alla", set())
    ren = _TUSEN.sub("", _REF.sub(" ", text))
    ren = _DATUM.sub(" ", _KLOCKA.sub(" ", ren))
    ren = re.sub(r"\b\d+[-–]åring\w*", " ", ren)  # ålder ur profilen
    ren = re.sub(r"\bden \d{1,2}(:e|e)?\b", " ", ren)  # "den 22:e"
    ren = ren.replace("_", " ")  # citerade fältnamn som skillnad_senaste_3_natter
    perioder = _perioder(ren)
    spo2_text = re.search(r"spo2|syre|mättnad", ren, re.I) is not None
    for mt in _NUM.finditer(ren):
        try:
            n = round(float(mt.group().replace(",", ".")), 1)
        except ValueError:
            continue
        if n in perioder or n in _UNDANTAG or n in (0.0, 1.0):
            continue
        efter = ren[mt.end():mt.end() + 14]
        fam = next((f for rx, f in ENHET_FAMILJ if rx.search(efter)), None)
        if fam is None and spo2_text and efter.lstrip().startswith("%"):
            fam = "spo2"
        if fam:
            if not _belagd(n, per_fam.get(fam, set())):
                return f"siffran {n:g} finns inte bland källans {fam}-värden"
        elif not _belagd(n, alla):
            return f"siffran {n:g} finns inte i källdatan"
        # En skillnad med fel tecken: källan säger +4,3 men påståendet "sjunkit med 4,3".
        r = _riktning(ren, mt.start(), mt.end())
        if r:
            mangd = per_fam.get(fam, set()) if fam else alla
            negativa = any(b < 0 and abs(-b - n) < 0.051 for b in mangd)
            positiva = any(b > 0 and abs(b - n) < 0.051 for b in mangd)
            if r < 0 and positiva and not negativa and not re.search(r"\btill\s*$", ren[max(0, mt.start() - 8):mt.start()]):
                if any(k.startswith("F:") for k in giltiga) and _har_skillnad(giltiga, refs, n, +1):
                    return f"{n:g} beskrivs som en minskning men källan visar en ökning"
            if r > 0 and negativa and not positiva:
                return f"{n:g} beskrivs som en ökning men källan visar en minskning"
    # "baslinje(n) ... X": talet direkt efter ordet baslinje måste vara ett baslinjevärde
    for mt in re.finditer(r"baslinje\w*", ren, re.I):
        seg = re.split(r"[;(]|,(?!\d)|\boch\b|\.(?!\d)", ren[mt.end():mt.end() + 30])[0]
        tal = [n for n in _tal_text(seg) if n not in perioder]
        if tal and not _belagd(tal[0], bas):
            return f"{tal[0]:g} kallas baslinje men är inget baslinjevärde i källan"
    kalltext = json.dumps([refs[k] for k in giltiga], ensure_ascii=False).lower()
    for rx, behov in SLUTSATSER:
        # en källa som själv nämner slutsatsen (t.ex. F:tolkning: "ser ut som mätfel") räcker också
        if rx.search(ren) and not (familjer & behov) and not rx.search(kalltext):
            return f"slutsatsen '{rx.search(ren).group()}' saknar källa av rätt typ"
    return None


def _har_skillnad(giltiga: list[str], refs: dict[str, dict[str, Any]], n: float, tecken: int) -> bool:
    """Sant om talet finns som ett skillnad-fält med givet tecken i någon av källorna."""
    def leta(o: Any, i_skillnad: bool) -> bool:
        if isinstance(o, dict):
            return any(leta(v, i_skillnad or "skillnad" in k) for k, v in o.items() if k != "ref")
        if isinstance(o, list):
            return any(leta(v, i_skillnad) for v in o)
        if isinstance(o, (int, float)) and not isinstance(o, bool) and i_skillnad:
            return abs(o - tecken * n) < 0.051
        return False
    return any(leta(refs[k], False) for k in giltiga)


def granska(m: Mote, agent: str, bed: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministisk kontroll. Ingen språkmodell kan prata sig förbi den."""
    godkanda = []
    for p in bed.get("pastaenden", []) or []:
        if not isinstance(p, dict):
            continue
        text = str(p.get("text", "")).strip()
        kallor = [k for k in (p.get("kallor") or []) if isinstance(k, str)]
        if not text:
            continue
        skal = kontrollera(text, kallor, m.refs, m.trigger.get("metric"))
        if skal:
            m.emit("review.strike", agent="granskare", target=agent, claim=text, reason=skal,
                   say_id=f"{agent}-bedomning")
        else:
            godkanda.append({"text": text, "kallor": [k for k in kallor if k in m.refs], "av": agent})
    return godkanda


def _meningar(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def granska_slutsats(m: Mote, verdict: dict[str, Any], godkanda: list[dict[str, Any]]) -> dict[str, Any]:
    """Slutbedömningens egen text: siffror måste finnas i de godkända påståendenas källor (eller larmet)."""
    bas_kallor = {k for p in godkanda for k in p["kallor"]} | ({"U:utlosare"} & set(m.refs))

    def ok(t: str) -> bool:
        if not _tal_text(_REF.sub(" ", t)):
            return True
        # källor som meningen själv anger ("källa: F:puls") räknas också, om de finns i mötet
        kallor = sorted(bas_kallor | {k for k in _REF.findall(t) if k in m.refs})
        skal = kontrollera(t, kallor, m.refs, m.trigger.get("metric")) if kallor else "inga godkända källor"
        if skal and skal.startswith("slutsatsen"):
            return True  # slutsatser utan siffror prövas i påståendena, inte i sammanfattningen
        if skal:
            m.emit("review.strike", agent="granskare", target="ordforande", claim=t, reason=skal,
                   say_id="ordforande-slutsats")
            return False
        return True

    v = dict(verdict)
    menings = [s for s in _meningar(str(v.get("sammanfattning", ""))) if ok(s)]
    v["sammanfattning"] = " ".join(menings) or (godkanda[0]["text"] if godkanda else "Teamet kunde inte belägga något i datan.")
    for falt in ("rad", "fragor_till_varden"):
        v[falt] = [x for x in (v.get(falt) or []) if isinstance(x, str) and ok(x)]
    return v


# ---------------------------------------------------------------- mötet

def _ordforande_val(m: Mote) -> list[tuple[str, str]]:
    beskr = "\n".join(f"- {i}: {TEAM[i].titel} ({TEAM[i].fokus})" for i in SPECIALISTER)
    mx = m.lage["max_specialister"]
    schema = {"type": "object", "properties": {"specialister": {"type": "array", "minItems": 2, "maxItems": mx, "items": {
        "type": "object", "properties": {"id": {"type": "string", "enum": SPECIALISTER}, "uppdrag": {"type": "string"}},
        "required": ["id", "uppdrag"]}}}, "required": ["specialister"]}
    m.emit("agent.think", agent="ordforande")
    r = m.chat([{"role": "user", "content": f"Du är allmänläkare och ordförande. Välj de specialister som behövs för just "
                 f"den här utlösaren och faktabladet: helst 2, högst {mx}. Ge var och en ett uppdrag på högst 20 ord som "
                 f"pekar på vilka fält de ska titta på.\n\nTeamet:\n{beskr}"}], fmt=schema, max_tokens=300)
    val = []
    for s in _json(r, {}).get("specialister", []):
        if isinstance(s, dict) and s.get("id") in SPECIALISTER and s["id"] not in [v[0] for v in val]:
            val.append((s["id"], s.get("uppdrag", "")))
    if len(val) < 2:  # modellen svarade inte strukturerat: rimlig standard utifrån mätvärdet
        metric = m.trigger.get("metric", "")
        std = {"hr": ["kardiolog", "stress"], "hrv_rmssd": ["stress", "kardiolog", "idrott"],
               "spo2": ["somn", "kardiolog"], "resp_rate": ["somn", "kardiolog"]}.get(metric, ["kardiolog", "somn", "idrott"])
        val = [(s, "Utred utlösaren utifrån ditt område.") for s in std]
    if "F:prover" in m.fakta and any(p["bedomning_mot_referens"] != "inom" for p in m.fakta["F:prover"]["prover"]) \
            and "labb" not in [v[0] for v in val]:
        val.append(("labb", "Bedöm provsvaren som ligger utanför referensintervallet."))
    return val[:max(mx, 2) + 1]


def _advokat(m: Mote, godkanda: list[dict[str, Any]]) -> dict[str, Any]:
    m.emit("agent.think", agent="advokat")
    fakta_ = "\n".join(f"{i + 1}. {p['text']} [{', '.join(p['kallor'])}] ({TEAM[p['av']].titel})" for i, p in enumerate(godkanda))
    schema = {"type": "object", "properties": {"invandningar": _kallschema(m, 3)}, "required": ["invandningar"]}
    r = m.chat([{"role": "user", "content": "Du är djävulens advokat. Ifrågasätt teamets slutsatser med vardagliga och "
                 "tekniska förklaringar (träning, mätfel, klockan satt löst, sömnbrist, koffein, stress, sjukdom) men "
                 "BARA sådana som faktabladet stöder eller inte kan utesluta. Varje invändning måste ha källa. Om "
                 "faktabladet motsäger en vardaglig förklaring (t.ex. inga steg och inget pass), använd den inte. "
                 f"Max 3 korta invändningar.\n\nTeamets granskade påståenden:\n{fakta_ or '(inga)'}"}],
               fmt=schema, max_tokens=400)
    return _json(r, {"invandningar": []})


def _replik(m: Mote, lid: str, invand: list[dict[str, Any]], godkanda: list[dict[str, Any]]) -> list[dict[str, Any]]:
    m.emit("agent.think", agent=lid)
    lista = "\n".join(f"{i + 1}. {p['text']}" for i, p in enumerate(invand))
    mina = "\n".join(f"- {p['text']}" for p in godkanda)
    schema = {"type": "object", "properties": {"svar": {"type": "array", "maxItems": len(invand), "items": {
        "type": "object", "properties": {"nr": {"type": "integer"}, "haller_med": {"type": "boolean"},
                                         "text": {"type": "string"},
                                         "kallor": {"type": "array", "items": {"type": "string", "enum": sorted(m.refs)}}},
        "required": ["nr", "haller_med", "text", "kallor"]}}}, "required": ["svar"]}
    r = m.chat([{"role": "user", "content": f"Du är {TEAM[lid].titel} och för teamets talan. Bemöt advokatens "
                 f"invändningar en i taget, max 25 ord per svar. Håll med när datan stöder invändningen, annars säg "
                 f"vilket fält som motsäger den.\n\nTeamets påståenden:\n{mina}\n\nAdvokatens invändningar:\n{lista}"}],
               fmt=schema, max_tokens=400)
    return [s for s in _json(r, {"svar": []}).get("svar", []) if isinstance(s, dict)]


SLUTSATS_SCHEMA = {"type": "object", "properties": {
    "sammanfattning": {"type": "string", "description": "max 3 meningar"},
    "bradska": {"type": "string", "enum": NIVAER},
    "bradska_motivering": {"type": "string"},
    "rad": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
    "fragor_till_varden": {"type": "array", "maxItems": 4, "items": {"type": "string"}}},
    "required": ["sammanfattning", "bradska", "bradska_motivering", "rad", "fragor_till_varden"]}

BRADSKA_TEXT = ("ingen = inget att göra; bevaka = håll koll, egenvård; ta_upp_med_varden = boka tid/ta upp vid nästa "
                "kontakt (inte akut); kontakta_vard_nu = ring 1177 eller 112 nu, bara vid akut fara.")


def _slutsats(m: Mote, godkanda: list[dict[str, Any]], debatt: str) -> dict[str, Any]:
    m.emit("agent.move", agent="ordforande", to="tavlan")
    m.emit("agent.think", agent="ordforande")
    fakta_ = "\n".join(f"- {p['text']} [{', '.join(p['kallor'])}]" for p in godkanda) or "- (inga belagda påståenden)"
    regel, skal = m.regel
    if m.lage["bradska"] == "fri":
        regeltext = ""
    else:
        regeltext = (f"\n\nRegelverkets brådska: {regel}. Skäl: {'; '.join(skal) or 'inga avvikelser'}. "
                     "Följ regelverket om inte de granskade påståendena tydligt visar något annat.")
    r = m.chat([{"role": "user", "content": "Du är ordförande. Skriv slutbedömningen ENBART utifrån de granskade "
                 "påståendena och diskussionen nedan. Sammanfattningen ska svara direkt på utlösaren eller frågan och "
                 "nämna det viktigaste fyndet med dess siffra. Råden (rad) ska vara konkreta HANDLINGAR för personen "
                 "(vad hen ska göra), inte en upprepning av fynden. Brådska: "
                 f"{BRADSKA_TEXT}{regeltext}\n\nGranskade påståenden:\n{fakta_}\n\nDiskussionen:\n{debatt or '(ingen)'}"}],
               fmt=SLUTSATS_SCHEMA, think=m.lage["think"], max_tokens=2500 if m.lage["think"] else 700)
    v = _json(r, {"sammanfattning": r.content.strip()[:600] or "Teamet kunde inte enas.", "bradska": "bevaka",
                  "rad": [], "fragor_till_varden": []})
    if v.get("bradska") not in NIVAER:
        v["bradska"] = "bevaka"
    return v


def bestam_bradska(m: Mote, llm_niva: str, godkanda: list[dict[str, Any]]) -> tuple[str, str]:
    """Slutlig brådska med spärrar. Returnerar nivå och hur den bestämdes."""
    regel = m.regel[0]
    lage_ = m.lage["bradska"]
    i_llm, i_regel = NIVAER.index(llm_niva), NIVAER.index(regel)
    if lage_ == "regel":
        niva, hur = regel, "regelverket"
    elif lage_ == "hybrid":
        # teamet får justera ett steg, men aldrig sänka det regelverket bedömt som vårdfall
        lo = i_regel if i_regel >= 2 else max(0, i_regel - 1)
        i = min(max(i_llm, lo), min(3, i_regel + 1))
        niva, hur = NIVAER[i], "teamet inom regelverkets ram" if i == i_llm else "regelverkets ram"
    else:
        niva, hur = llm_niva, "teamet"
    if not godkanda and NIVAER.index(niva) < max(1, i_regel if lage_ != "fri" else 1):
        niva, hur = NIVAER[max(1, i_regel if lage_ != "fri" else 1)], "inga belagda påståenden"
    if niva == "kontakta_vard_nu" and m.trigger.get("level") != "akut":
        niva, hur = "ta_upp_med_varden", "larmspärr: bara en akut vaktregel kan ge kontakta_vard_nu"
    return niva, hur


def _spara_bevis_kolumn() -> None:
    try:
        db.conn().execute("ALTER TABLE consults ADD COLUMN evidence TEXT")
        db.conn().commit()
    except Exception:
        pass  # finns redan


def _kor(m: Mote) -> None:
    _spara_bevis_kolumn()
    with db.tx() as c:
        c.execute("INSERT INTO consults(id, started, trigger) VALUES (?,?,?)",
                  (m.id, m.t0, json.dumps(m.trigger, ensure_ascii=False)))
    llm.kontext.consult_id = m.id
    m.emit("consult.start", trigger=m.trigger, members=["ordforande", "advokat", "granskare"])
    m.emit("agent.move", agent="ordforande", to="bordet")
    _forbered(m)

    val = _ordforande_val(m)
    m.emit("consult.members", members=["ordforande", *[v[0] for v in val], "advokat", "granskare"])
    for lid, _ in val:
        m.emit("agent.move", agent=lid, to="bordet")
    for lid, uppdrag in val:
        m.say("ordforande", f"{TEAM[lid].titel}: {uppdrag}", to=lid)

    bedomningar: dict[str, dict[str, Any]] = {}
    for lid, uppdrag in val:  # en i taget: 16 GB räcker inte för parallella modellinstanser
        bedomningar[lid] = _specialist(m, lid, uppdrag)

    godkanda: list[dict[str, Any]] = []
    for lid, bed in bedomningar.items():
        m.emit("agent.move", agent=lid, to="bordet")
        claims = [{"text": p.get("text", ""), "kallor": p.get("kallor") or []}
                  for p in bed.get("pastaenden", []) or [] if isinstance(p, dict)]
        m.emit("agent.say", agent=lid, to="alla", text=bed.get("sammanfattning", ""), claims=claims,
               cites=[k for c in claims for k in c["kallor"]][:6], say_id=f"{lid}-bedomning",
               bradska_forslag=bed.get("bradska_forslag"))
        m.emit("agent.handoff", agent=lid, to="granskare", item="bedömning")
        with matning.tid("Granskning"):
            godkanda += granska(m, lid, bed)

    m.emit("agent.move", agent="advokat", to="bordet")
    adv = _advokat(m, godkanda)
    invand = []
    for p in adv.get("invandningar", []) or []:
        if isinstance(p, dict) and str(p.get("text", "")).strip():
            skal = kontrollera(str(p["text"]), [k for k in p.get("kallor") or [] if isinstance(k, str)], m.refs,
                               m.trigger.get("metric"))
            if skal:
                m.emit("review.strike", agent="granskare", target="advokat", claim=p["text"], reason=skal,
                       say_id="advokat-invandning")
            else:
                invand.append(p)
    m.say("advokat", "\n".join(f"- {p['text']}" for p in invand) or "Jag hittar ingen vardaglig förklaring som datan stöder.",
          cites=sorted({k for p in invand for k in p.get("kallor", [])})[:6], say_id="advokat-invandning",
          claims=[{"text": p["text"], "kallor": p.get("kallor", [])} for p in invand])
    debatt = "\n".join(f"Advokaten: {p['text']}" for p in invand)
    if invand and m.lage["diskussion"]:
        lid = val[0][0]
        for s in _replik(m, lid, invand, [p for p in godkanda if p["av"] == lid] or godkanda):
            text = str(s.get("text", "")).strip()
            if not text:
                continue
            kallor = [k for k in s.get("kallor") or [] if isinstance(k, str)]
            skal = kontrollera(text, kallor, m.refs, m.trigger.get("metric")) if _tal_text(text) else None
            if skal:
                m.emit("review.strike", agent="granskare", target=lid, claim=text, reason=skal, say_id=f"{lid}-replik")
                continue
            m.say(lid, text, to="advokat", cites=kallor, say_id=f"{lid}-replik", haller_med=bool(s.get("haller_med")))
            debatt += f"\n{TEAM[lid].titel} svarar på {s.get('nr')}: {'håller med' if s.get('haller_med') else 'invänder'}: {text}"

    verdict = _slutsats(m, godkanda, debatt)
    llm_niva = verdict["bradska"]
    verdict["bradska"], verdict["bradska_bestamd_av"] = bestam_bradska(m, llm_niva, godkanda)
    verdict["bradska_team"] = llm_niva
    verdict["bradska_regel"], verdict["bradska_regel_skal"] = m.regel
    verdict = granska_slutsats(m, verdict, godkanda)
    verdict["belagda_pastaenden"] = godkanda
    m.say("ordforande", verdict.get("sammanfattning", ""), cites=sorted({k for p in godkanda for k in p["kallor"]})[:8],
          say_id="ordforande-slutsats")
    m.emit("consult.verdict", verdict=verdict)
    _avsluta(m, verdict)
    if verdict["bradska"] in ("ta_upp_med_varden", "kontakta_vard_nu"):
        bus.publish("alert.raise", {"level": "akut" if verdict["bradska"] == "kontakta_vard_nu" else "avvikelse",
                                    "title": "Konsiliet har en bedömning", "body": verdict.get("sammanfattning", ""),
                                    "consult_id": m.id})


def _avsluta(m: Mote, verdict: dict[str, Any]) -> None:
    stats = {**m.usage.as_dict(), "sekunder_totalt": round(time.time() - m.t0, 1),
             "modeller": sorted(m.usage.per_model), "lage": m.lage}
    with db.tx() as c:
        c.execute("UPDATE consults SET ended=?, transcript=?, verdict=?, stats=?, evidence=? WHERE id=?",
                  (time.time(), json.dumps(m.transcript, ensure_ascii=False), json.dumps(verdict, ensure_ascii=False),
                   json.dumps(stats), json.dumps(m.refs, ensure_ascii=False, default=str), m.id))


# ---------------------------------------------------------------- kö

_q: "queue.Queue[Mote]" = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _worker() -> None:
    while True:
        m = _q.get()
        try:
            with matning.tid("Hela konsiliet"):
                _kor(m)
        except Exception as e:
            log.exception("konsiliet kraschade")
            verdict = {"sammanfattning": f"Mötet avbröts av ett fel: {e}", "bradska": "bevaka", "rad": [], "fel": True}
            m.emit("consult.verdict", verdict=verdict)
            try:
                _avsluta(m, verdict)
            except Exception:
                log.exception("kunde inte spara det avbrutna mötet")
        finally:
            llm.kontext.consult_id = None
            try:
                for namn in llm.lasta_ur_om_for_stor():
                    log.info("laddade ur %s: minnet hade vuxit över %.0f GiB", namn, llm.MAX_MINNE_GIB)
            except Exception:
                pass


def start_async(trigger: dict[str, Any]) -> str:
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            threading.Thread(target=_worker, name="konsiliet", daemon=True).start()
            _worker_started = True
    m = Mote(uuid.uuid4().hex[:12], trigger)
    _q.put(m)
    return m.id
