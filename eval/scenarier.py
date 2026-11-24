"""Utvärderingsscenarier med känt rätt svar. All data är syntetisk (sim.py) och presenteras aldrig som verklig.

Varje scenario har:
  klocka     lokal tid då mötet "äger rum" (klockan i utvärderingsprocessen flyttas dit)
  bygg(sim)  lägger in det som ska hittas och returnerar utlösaren (som vakten eller en fråga skulle se ut)
  facit      rätt brådska, godtagbara brådskor, fynd som måste finnas och påståenden som inte får göras

Brådskeskalan: ingen < bevaka < ta_upp_med_varden < kontakta_vard_nu.
Fynd kontrolleras med reguljära uttryck mot slutbedömningen (sammanfattning, råd, frågor och belagda
påståenden). "far_ej" räknas bara om meningen saknar negation (inte/ingen/inga/utan/ej).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from sim import Sim

NIVAER = ["ingen", "bevaka", "ta_upp_med_varden", "kontakta_vard_nu"]


@dataclass
class Facit:
    bradska: str
    godtagbar: tuple[str, ...]
    maste: list[tuple[str, str]]
    far_ej: list[tuple[str, str]] = field(default_factory=list)
    beskrivning: str = ""


@dataclass
class Scenario:
    id: str
    titel: str
    klocka: str
    bygg: Callable[[Sim], dict[str, Any]]
    facit: Facit


def _anomali(rule: str, level: str, metric: str, title: str, detail: str, a: float, b: float) -> dict[str, Any]:
    return {"kind": "anomaly", "rule": rule, "level": level, "metric": metric, "title": title, "detail": detail,
            "window": [a, b]}


def _fraga(text: str, timmar: int = 72) -> dict[str, Any]:
    return {"kind": "question", "question": text, "hours": timmar}


# ------------------------------------------------------------------ 1. äkta pulsrusning i vila

def s_akut_takykardi(s: Sim) -> dict[str, Any]:
    s.standard(kvall="kod", kvall_tid=(18 * 60, 23 * 60))
    s.standardprover()
    # sitter och kodar, pulsen slår om från ~72 till ~168 på en minut och ligger kvar
    a = s.nu - 14 * 60
    sl = s.span(a, s.nu + 60)
    s.steg[s.span(s.nu - 40 * 60, s.nu + 60)] = 0
    s.hr_add[sl] = 97 + s.rng.normal(0, 1.5, sl.stop - sl.start)
    s.hrv_fak[sl] = 0.3
    s.generera()
    med = s.hr_median(10)
    return _anomali("hr_rest_acute", "akut", "hr", "Mycket hög puls i vila",
                    f"Medianpuls {med:.0f} slag/min de senaste 10 minuterna utan rörelse.", s.nu - 600, s.nu)


F_AKUT = Facit(
    "kontakta_vard_nu", ("kontakta_vard_nu",),
    [("hög puls med siffra", r"\b1[5-7]\d\b"),
     ("i vila / utan rörelse", r"vila|utan (rörelse|steg|aktivitet)|inga steg|0 steg|stillasitt|sitter|sittande"),
     ("plötslig debut", r"plötslig|abrupt|tvärt|hastig|snabb(t|a)? (ökning|stegring|uppgång)|på (en|några) minut")],
    [("bortförklarar med träning", r"(beror|förklaras|orsakas)\w* (troligen |sannolikt |nog )?(på|av) (träning|motion|ansträngning)"),
     ("lugnar", r"inget att oroa|ofarlig|helt normal")],
    "Äkta pulsrusning i vila: pulsen slog om från cirka 72 till cirka 168 slag/min på en minut medan personen satt "
    "vid datorn och kodade, utan steg och utan träningspass, och ligger kvar i 14 minuter. Rätt: kontakta vården nu "
    "(1177/akut, 112 vid bröstsmärta, svimning eller andnöd). Fel: att förklara det med träning eller lugna.")


# ------------------------------------------------------------------ 2. hög puls som är ett löppass

def s_traning(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    start = 17 * 60 + 15  # 17:15-18:00, klockan är 18:30
    s.traning(0, start, 45, "löpning", 0.86, takt=162)
    s.traning(0, start + 34, 6, "löpning", 1.0, takt=172)  # slutspurt
    s.pass_.pop()  # spurten är samma pass
    return _fraga("Klockan visade puls över 170 för en stund sedan. Är det farligt?", 6)


F_TRANING = Facit(
    "ingen", ("ingen", "bevaka"),
    [("kopplar till löppasset", r"träning|löp|pass|ansträng"),
     ("steg / kadens", r"steg"),
     ("återhämtning efteråt", r"återhämt|sjönk|gick ner|normalis|tillbaka|efter passet")],
    [("larmar", r"kontakta vården (nu|omedelbart|direkt)|ring 1177|ring 112|akut")],
    "Pulsen 150-175 slag/min kom under ett registrerat löppass på 45 minuter med cirka 160 steg/min, och sjönk efteråt. "
    "Rätt: ingen oro, normal träningspuls för en 18-åring. Fel: att larma eller tala om hjärtrusning.")


# ------------------------------------------------------------------ 3. enstaka sensorspikar

def s_sensorspikar(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    # fem isolerade minuter med 190-215 i går kväll och i natt, grannarna ligger på 60-75
    for dag_min, v in ((-170, 203), (-120, 211), (-95, 196), (40, 214), (150, 192)):
        k = s.idx(s.ts(0, dag_min))
        s.hr_satt[k] = v
    return _fraga("Appen visade att min puls var över 200 i går kväll och i natt. Vad hände?", 24)


F_SPIKAR = Facit(
    "ingen", ("ingen", "bevaka"),
    [("enstaka mätpunkter", r"enstaka|isolerad|enskild|enda (mät)?punkt|en minut|kortvarig|enstaka värden|en mätning"),
     ("mätfel / artefakt", r"mätfel|artefakt|sensor|felmätning|felaktig|klockan|signal")],
    [("pulsrusning som fakta", r"(hade|fick|drabbades av) (en )?(pulsrusning|takykardi|hjärtrusning)"),
     ("larmar", r"kontakta vården (nu|omedelbart|direkt)|ring 112")],
    "Fem isolerade enminutersvärden på 192-214 slag/min mitt i normal vilopuls (60-75) och sömn, inga grannvärden "
    "över 80, inga steg. Fysiologiskt osannolikt: rätt svar är mätfel/artefakt, ingen åtgärd utöver att se att "
    "klockan sitter bra. Fel: att behandla det som verklig pulsrusning.")


# ------------------------------------------------------------------ 4. klockan sitter löst

def s_klocka_los(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    # senaste 45 minuterna: hoppiga värden, ibland dubbla, och luckor
    a = s.nu - 45 * 60
    sl = s.span(a, s.nu + 60)
    n = sl.stop - sl.start
    s.steg[s.span(a - 600, s.nu + 60)] = 0
    hopp = s.rng.random(n) < 0.55
    s.hr_add[sl] = np.where(hopp, s.rng.uniform(35, 70, n), s.rng.normal(0, 6, n))
    s.bortfall[sl] = s.rng.random(n) < 0.3
    s.generera()
    w = s._hr_sann[-20:]
    med = float(np.median(w))
    return _anomali("baseline_hr", "avvikelse", "hr", "Vilopulsen avviker från din baslinje",
                    f"Vilopulsen {med:.1f} mot normalt 74.0 vid den här tiden (4.1 SD över).", s.nu - 1200, s.nu)


F_LOS = Facit(
    "bevaka", ("ingen", "bevaka"),
    [("mätproblem / klockans passform", r"löst|sitter|passform|mätfel|artefakt|signal|sensor|felmät|kontakt med huden"),
     ("hoppiga värden", r"hopp|varier|ojämn|oregelbund|spridning|instabil|svänger|växlar|luckor|saknas")],
    [("larmar", r"kontakta vården (nu|omedelbart|direkt)|ring 112")],
    "De senaste 45 minuterna i vila hoppar pulsen mellan cirka 70 och 140 från minut till minut, med luckor där "
    "klockan inte registrerat något. Mönstret är typiskt för en klocka som sitter löst. Rätt: troligen mätfel, dra "
    "åt armbandet och mät om; bevaka. Fel: akut larm.")


# ------------------------------------------------------------------ 5. förkylning på väg

def s_forkylning(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=3)
    s.standard(fran_dag=2, till_dag=0, steg_mal=2500, lagg=-90, upp=520)
    s.standardprover()
    # de tre senaste nätterna: HRV ner, puls upp, hudtemp och andning upp
    for dag, hrv, hr, temp, resp in ((2, 0.66, 5, 0.4, 0.9), (1, 0.6, 7, 0.6, 1.4), (0, 0.55, 9, 0.85, 2.0)):
        sl = s.span(s.ts(dag, -180), s.ts(dag, 600))
        s.hrv_fak[sl] *= hrv
        s.hr_add[sl] += hr
        s.temp_add[sl] += temp
        s.resp_add[sl] += resp
    s.generera()
    return _anomali("hrv_trend", "avvikelse", "hrv_rmssd", "HRV låg tre nätter i rad",
                    "Nattlig HRV 37, 34, 31 ms mot normalt 56 ms.",
                    s.ts(2, 0), s.ts(0, 360))


F_FORKYL = Facit(
    "bevaka", ("bevaka", "ta_upp_med_varden"),
    [("HRV lägre", r"hrv"),
     ("vilopuls högre", r"vilopuls|nattpuls|puls\w* (i natt |under natten )?(är |var )?(högre|förhöjd|ökat|steg|stigit)"),
     ("hudtemperatur upp", r"hudtemp|temperatur"),
     ("infektion / vila", r"infektion|förkyl|sjuk|virus|vila|ta det lugnt|immun")],
    [("akut", r"kontakta vården (nu|omedelbart|direkt)|ring 112"),
     ("hård träning", r"(kör|gör|passa på att) (intervaller|hårt pass|högintensiv)")],
    "Tre nätter i rad: nattlig HRV sjunker från cirka 56 till 37-31 ms, nattpulsen stiger 5-9 slag/min, hudtemperaturen "
    "stiger 0,4-0,85 grader och andningsfrekvensen ökar. Stegen har minskat och sömnen blivit längre. Klassiskt mönster "
    "före en förkylning/infektion. Rätt: bevaka, vila, avstå hård träning, kontakta vården vid feber/andnöd. Fel: akut larm "
    "eller råd om hård träning.")


# ------------------------------------------------------------------ 6. sent spelande ger kort sömn

def s_sent_spel(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=7)
    for d in range(6, -1, -1):
        s.natt(d, 170 + s.rng.normal(0, 15), 485 + s.rng.normal(0, 8))
        s.datorblock(d + 1, 20 * 60, 24 * 60 + 150 + s.rng.normal(0, 10), "spel")
        for st, m in ((515, 15), (720, 10), (960, 18), (1020, 12)):
            s.gang(d, st, m)
    s.standardprover()
    return _fraga("Hur har jag sovit senaste veckan, och varför känns det så dåligt?", 168)


F_SENT_SPEL = Facit(
    "bevaka", ("ingen", "bevaka"),
    [("kort sömn", r"\b[45][,.]\d\s*(h|tim)|\b[45] timmar|\b(2[5-9]\d|3[0-4]\d) min|kort(are)? sömn|för lite sömn|sover för lite|sömnbrist"),
     ("sen läggning", r"sen(t|a)? (läggning|kväll|insomning|natt)|lägger dig sent|somnar sent|0?[23][:.]\d\d|efter midnatt|kl(ockan)? [23]\b"),
     ("spel / dator", r"spel|dator|skärm|gaming")],
    [("sömnapné", r"sömnapn"),
     ("akut", r"kontakta vården (nu|omedelbart|direkt)")],
    "Sista veckan har personen spelat på datorn till cirka 02:30 varje natt, somnat cirka 02:50 och vaknat 08:05: "
    "cirka 5 timmar och 15 minuters sömn mot 8 timmar tidigare. Rätt: sen skärmtid ger sömnbrist, råd om "
    "skärmstopp/fast läggtid; ingen sjukdom. Fel: sömnapné eller akut larm.")


# ------------------------------------------------------------------ 7. nattliga syrefall

def s_spo2_dippar(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    # klockan är 03:40, personen sover sedan 23:20; upprepade fall varje natt senaste veckan
    for dag in range(7, -1, -1):
        a, b = s.ts(dag, -30), s.ts(dag, 440 if dag else 220)
        t = a + 1800
        while t < b - 300:
            k = s.idx(t)
            d = s.rng.uniform(5, 9)
            langd = int(s.rng.integers(1, 3))
            s.spo2_add[k:k + langd] -= d
            s.spo2_add[k + langd:k + langd + 1] -= d / 2
            s.hr_add[k + langd:k + langd + 2] += s.rng.uniform(6, 12)
            t += int(s.rng.uniform(3, 7) * 60)
    s.generera()
    return _anomali("spo2_dips", "avvikelse", "spo2", "Upprepade syrefall",
                    "11 fall på minst 4 procentenheter senaste timmen (baslinje 97 %).", s.nu - 3600, s.nu)


F_SPO2 = Facit(
    "ta_upp_med_varden", ("ta_upp_med_varden",),
    [("upprepade syrefall", r"syre|spo2|saturation|mättnad"),
     ("flera nätter / mönster", r"(flera|varje|alla|senaste) nätter|natt efter natt|återkommande|upprepade|mönster|varje natt"),
     ("utredning / sömnapné / andningsuppehåll", r"sömnapn|andningsuppeh|andningsstörning|sömnregistrering|utredning|snark")],
    [("lugnar", r"inget att oroa|ofarlig"),
     ("akut", r"ring 112")],
    "Varje natt senaste veckan: fall i syremättnad på 5-9 procentenheter (från cirka 96 till 87-91 %) var 3-7:e minut, "
    "korta, med pulsökning efteråt. Mönstret liknar andningsuppehåll i sömnen. Rätt: ta upp med vården för "
    "sömnutredning (inte akut). Fel: lugna bort det eller larma akut.")


# ------------------------------------------------------------------ 8. aktiva och stillasittande dagar

def s_aktiv_stilla(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=15)
    for d in range(14, -1, -1):
        aktiv = d % 2 == 0
        s.natt(d, -40 + s.rng.normal(0, 15), 450 + s.rng.normal(0, 8))
        if aktiv:
            for st, m in ((475, 15), (720, 10), (960, 18), (1080, 55), (1260, 25)):
                s.gang(d, st + s.rng.normal(0, 8), m)
            s.datorblock(d, 19.5 * 60, 23 * 60, "spel")
        else:
            s.gang(d, 600, 8)
            s.gang(d, 900, 6)
            s.datorblock(d, 9.5 * 60, 23.2 * 60, "kod")
        # natten efter en aktiv dag (natten till d-1): bättre HRV, lägre puls
        if d >= 1:
            sl = s.span(s.ts(d - 1, -60), s.ts(d - 1, 480))
            s.hrv_fak[sl] *= 1.18 if aktiv else 0.9
            s.hr_add[sl] += -2.5 if aktiv else 1.5
    s.standardprover()
    return _fraga("Märks det på kroppen när jag rör mig mer? Jämför mina aktiva dagar med de stillasittande.", 336)


F_AKTIV = Facit(
    "ingen", ("ingen",),
    [("steg per dag med siffror", r"\d[\d ]{2,}\s*steg|steg\D{0,20}\d{3,}"),
     ("skillnad i HRV, vilopuls eller sömn", r"hrv|vilopuls|nattpuls|sömn"),
     ("uppmuntrar rörelse", r"promen|rör (dig|på dig)|aktiv|gå mer|fler steg")],
    [("akut", r"kontakta vården")],
    "Varannan dag cirka 12 000 steg (promenad 55 min + kvällspromenad), varannan dag under 2 000 steg och 13 timmar "
    "vid datorn. Natten efter aktiva dagar är HRV cirka 18 % högre och nattpulsen 2-3 slag/min lägre. Rätt: ja, det "
    "märks, fortsätt röra dig; ingen oro.")


# ------------------------------------------------------------------ 9. allt normalt

def s_normal(s: Sim) -> dict[str, Any]:
    s.standard(steg_mal=8000)
    s.standardprover()
    s.journal.append({"date": s.datum(400), "kind": "vaccination", "title": "Vaccination",
                      "author": "Sjuksköterska", "text": "Influensavaccin given."})
    return _fraga("Hur ser det ut med min hälsa senaste veckan? Något att oroa sig för?", 168)


F_NORMAL = Facit(
    "ingen", ("ingen",),
    [("inget avvikande", r"normal|inom (din|ditt|det|personens)|inget (avvik|oro|att oroa)|inga (avvik|tecken|tydliga)|stabil|som vanligt|ser bra ut|ser normal")],
    [("sjukdomsfynd", r"sömnapn|infektion|takykardi|arytmi|förmaksflimmer"),
     ("vårdkontakt", r"kontakta vården|boka (en )?tid")],
    "Helt normal vecka: sömn cirka 8 timmar, normal nattpuls och HRV, 8 000 steg per dag, normala provsvar. "
    "Rätt: inget att oroa sig för.")


# ------------------------------------------------------------------ 10. trött av kort sömn och sena kodkvällar

def s_trott_kort_somn(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=11)
    for d in range(10, -1, -1):
        s.natt(d, 85 + s.rng.normal(0, 12), 435 + s.rng.normal(0, 6))
        s.datorblock(d + 1, 18 * 60, 24 * 60 + 70 + s.rng.normal(0, 10), "kod")
        for st, m in ((460, 15), (720, 8), (960, 12)):
            s.gang(d, st, m)
    s.standardprover(dagar_sedan=90)
    return _fraga("Varför är jag så trött hela tiden?", 168)


F_TROTT = Facit(
    "ingen", ("ingen", "bevaka"),
    [("kort sömn", r"\b[56][,.]\d\s*(h|tim)|\b[56] timmar|\b(3[3-9]\d) min|kort(are)? sömn|för lite sömn|sover för lite|sömnbrist|sömnen är kort"),
     ("sena kodkvällar", r"kod|dator|skärm|sent|sena kvällar|efter midnatt"),
     ("provsvaren normala", r"(prov|labb|blodvärde|ferritin|hemoglobin|hb|tsh)\w*")],
    [("järnbrist / anemi som fynd", r"järnbrist|anemi|blodbrist"),
     ("sköldkörtel som fynd", r"sköldkörtel\w* (är|verkar) (rubbad|låg|hög)")],
    "Elva nätter i rad cirka 5 timmar och 50 minuters sömn (läggning cirka 01:25, uppvak 07:15) efter kodande vid datorn till "
    "cirka 01:10. Lite rörelse. Provsvar från 3 månader sedan normala (Hb 148, ferritin 72, TSH 1,6). Rätt: tröttheten "
    "förklaras bäst av för lite sömn och sena skärmkvällar; ingen sjukdom i datan.")


# ------------------------------------------------------------------ 11. lågt ferritin

def s_ferritin(s: Sim) -> dict[str, Any]:
    s.standard(lagg=-60, upp=470, steg_mal=6000)
    s.standardprover(dagar_sedan=400)
    d = s.datum(20)
    for analyt, v, enh, lo, hi, fl in (("Ferritin", 9, "µg/L", 15, 150, "L"), ("Hb", 138, "g/L", 134, 170, None),
                                       ("TSH", 2.1, "mIE/L", 0.4, 4.0, None), ("B12", 410, "pmol/L", 140, 650, None)):
        lb = {"date": d, "analyt": analyt, "varde": v, "enhet": enh, "lag": lo, "hog": hi}
        if fl:
            lb["flagga"] = fl
        s.labb.append(lb)
    s.journal.append({"date": d, "kind": "anteckning", "title": "Besök vårdcentral", "author": "Läkare",
                      "text": "18-åring som söker för trötthet sedan cirka 2 månader. Sover enligt egen uppgift "
                              "8 timmar per natt. Inga infektionstecken. Tar blodprover. Återkoppling via 1177."})
    return _fraga("Jag är trött hela tiden fast jag sover ordentligt. Vad kan det bero på?", 168)


F_FERRITIN = Facit(
    "ta_upp_med_varden", ("ta_upp_med_varden",),
    [("ferritin nämns", r"ferritin"),
     ("lågt värde", r"\b9\b|lågt|låg|under referens|under det normala"),
     ("järnförråd / järn", r"järn"),
     ("sömnen räcker", r"sömn\w* (är |var |ser )?(normal|tillräcklig|bra|ok|cirka 8|8)|sover (tillräckligt|bra|8)|\b[78][,.]\d\s*(h|tim)|\b8 timmar|\b(4[5-9]\d) min")],
    [("anemi som fakta", r"(har|du har|personen har|visar) (järnbrist)?anemi|blodbrist"),
     ("akut", r"kontakta vården (nu|omedelbart|direkt)|ring 112")],
    "Ferritin 9 µg/L (under referens 15) från 20 dagar sedan, Hb 138 g/L normalt, TSH och B12 normala. Sömn cirka 8 timmar "
    "per natt. Rätt: lågt järnförråd kan förklara tröttheten, ta upp med vården (uppföljning/behandling); sömnen förklarar "
    "den inte. Fel: kalla det anemi (Hb är normalt) eller larma akut.")


# ------------------------------------------------------------------ 12. motstridiga signaler: tung träningsvecka

def s_motstridigt(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=4)
    s.standard(fran_dag=3, till_dag=0, steg_mal=6000)
    s.standardprover()
    for d in (3, 2, 1):  # tre hårda löppass i rad på kvällen
        s.traning(d, 17 * 60, 60, "löpning", 0.88, takt=164)
    for dag, hrv in ((2, 0.72), (1, 0.66), (0, 0.63)):
        sl = s.span(s.ts(dag, -180), s.ts(dag, 600))
        s.hrv_fak[sl] *= hrv
        s.hr_add[sl] += 3
    s.generera()
    return _anomali("hrv_trend", "avvikelse", "hrv_rmssd", "HRV låg tre nätter i rad",
                    "Nattlig HRV 40, 37, 35 ms mot normalt 56 ms.", s.ts(2, 0), s.ts(0, 360))


F_MOTSTRID = Facit(
    "bevaka", ("ingen", "bevaka"),
    [("kopplar till träningspassen", r"träning|löp|pass|belastning|ansträng"),
     ("temperaturen normal", r"temp"),
     ("vila / återhämtning", r"återhämt|vila|lugn|vilodag|lättare")],
    [("infektion som slutsats", r"(tyder|pekar) på (en )?(infektion|förkylning)|(har|är) (förkyld|sjuk)"),
     ("akut", r"kontakta vården (nu|omedelbart|direkt)")],
    "HRV låg tre nätter i rad, men varje kväll innan fanns ett hårt löppass på 60 minuter (ny träning). Hudtemperatur och "
    "andning normala, nattpulsen bara +3. Rätt: troligen träningsbelastning, vila/lättare pass och bevaka; en infektion "
    "kan inte helt uteslutas men talar emot (normal temp). Fel: slå fast infektion eller larma.")


# ------------------------------------------------------------------ 13. akut lågt syre i vila

def s_spo2_akut(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    s.journal.append({"date": s.datum(300), "kind": "diagnos", "title": "Astma", "author": "Läkare",
                      "text": "Astma, lindrig. Ventoline vid behov. Försämring vid förkylning."})
    a = s.nu - 12 * 60
    sl = s.span(a, s.nu + 60)
    n = sl.stop - sl.start
    s.steg[s.span(a - 1200, s.nu + 60)] = 0
    s.spo2_add[sl] = -12 + s.rng.normal(0, 0.8, n)
    s.resp_add[sl] = 10 + s.rng.normal(0, 1, n)
    s.hr_add[sl] = 38
    m = np.zeros(s.n, bool)
    i0, ia = s.idx(s.nu - 3 * 3600), s.idx(a)
    m[i0:ia:15] = True
    m[ia:] = True
    s.extra["spo2"] = m
    s.extra["resp_rate"] = m
    return _anomali("spo2_low", "akut", "spo2", "Lågt syremättnad",
                    "SpO2 median 86 % de senaste 5 minuterna.", s.nu - 300, s.nu)


F_SPO2_AKUT = Facit(
    "kontakta_vard_nu", ("kontakta_vard_nu",),
    [("lågt syre med siffra", r"\b8[3-8]\b\s*%?"),
     ("snabb andning", r"andning|andetag|andas"),
     ("astma i journalen", r"astma|ventoline")],
    [("lugnar", r"inget att oroa|ofarlig")],
    "I vila de senaste 12 minuterna: SpO2 84-87 % (normalt 97), andningsfrekvens cirka 26 och puls cirka 110, mot normala "
    "värden timmarna innan. Journalen har astma. Rätt: kontakta vården nu (1177/112 vid andnöd), ta Ventoline enligt "
    "ordination. Fel: lugna eller bara bevaka.")


# ------------------------------------------------------------------ 14. återkommande pulshopp i vila

def s_aterkommande(s: Sim) -> dict[str, Any]:
    s.standard(kvall="kod", kvall_tid=(13 * 60, 23 * 60))
    s.standardprover()
    nu_min = (s.nu - s.ts(0, 0)) / 60
    s.datorblock(0, 13 * 60, nu_min + 1, "kod")
    for start, lang in ((nu_min - 290, 7), (nu_min - 140, 9), (nu_min - 2.5, 6)):
        a = s.ts(0, start)
        sl = s.span(a, a + lang * 60)
        s.steg[s.span(a - 600, a + lang * 60 + 600)] = 0
        s.hr_add[sl] = 76 + s.rng.normal(0, 2, sl.stop - sl.start)
    s.generera()
    return _anomali("hr_sudden_jump", "akut", "hr", "Plötsligt pulshopp i vila",
                    "Pulsen steg från 72 till 147 på några minuter utan rörelse.", s.nu - 300, s.nu)


F_ATERK = Facit(
    "ta_upp_med_varden", ("ta_upp_med_varden", "kontakta_vard_nu"),
    [("flera episoder idag", r"upprepa|flera|tre (gånger|episoder|tillfällen)|3 (gånger|episoder)|återkommande|episod|tidigare idag"),
     ("plötslig start och slut", r"plötslig|abrupt|tvärt|hastig"),
     ("i vila", r"vila|utan (rörelse|steg)|inga steg|sitter|stillasitt"),
     ("EKG / rytmregistrering", r"ekg|hjärtrytm|rytm|1177|vården")],
    [("bortförklarar med träning", r"(beror|förklaras|orsakas)\w* (troligen |sannolikt )?(på|av) (träning|motion)"),
     ("lugnar", r"inget att oroa")],
    "Tre episoder idag (för cirka 5 timmar, 2,5 timmar och 4 minuter sedan) där vilopulsen slår om från cirka 72 till "
    "cirka 148 och tillbaka efter 6-9 minuter, i vila vid datorn. Mönster som vid paroxysmal supraventrikulär takykardi. "
    "Rätt: ta upp med vården för EKG/rytmregistrering, kontakta vården direkt vid yrsel, bröstsmärta, svimning. "
    "Fel: bortförklara med träning.")


# ------------------------------------------------------------------ 15. stress under projektvecka

def s_stress(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=8)
    for d in range(7, -1, -1):
        s.natt(d, 75 + s.rng.normal(0, 15), 440 + s.rng.normal(0, 6))
        slut = 24 * 60 + 50 if d >= 1 else 24 * 60
        s.datorblock(d + 1, 9 * 60, slut, "kod")
        for st, m in ((460, 10), (720, 8)):
            s.gang(d, st, m)
        sl = s.span(s.ts(d, -60), s.ts(d, 1440))
        s.hrv_fak[sl] *= 0.8
        s.hr_add[sl] += 4
    s.datorblock(0, 9 * 60, 14 * 60, "kod")
    s.standardprover()
    return _fraga("Är jag stressad? Jag har haft mycket med ett projekt senaste veckan.", 168)


F_STRESS = Facit(
    "bevaka", ("ingen", "bevaka"),
    [("HRV lägre", r"hrv"),
     ("kortare sömn", r"sömn"),
     ("långa datorpass", r"kod|dator|skärm|långa (pass|dagar)|timmar vid")],
    [("sjukdom", r"(tyder|pekar) på (en )?(infektion|sjukdom)|utbrändhet|utmattningssyndrom"),
     ("akut", r"kontakta vården (nu|omedelbart|direkt)")],
    "Senaste veckan: kodande 09:00-00:50 varje dag, sömn cirka 6 timmar, HRV cirka 20 % lägre dygnet runt och puls 4 slag/min "
    "högre, mycket lite rörelse. Rätt: tecken på belastning/stress och sömnbrist, råd om pauser, rörelse och sömn; bevaka. "
    "Fel: sjukdomsdiagnoser eller akut larm.")


# ------------------------------------------------------------------ 16. trött efter sena spelkvällar (från användbarhetstestet)

def s_trott_spel(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=7)
    for d in range(6, -1, -1):
        s.natt(d, 115 + s.rng.normal(0, 12), 420 + s.rng.normal(0, 6))  # somnar cirka 01:55, vaknar 07:00
        s.datorblock(d + 1, 19 * 60, 24 * 60 + 100 + s.rng.normal(0, 10), "spel")
        for st, m in ((440, 15), (720, 10), (960, 15)):
            s.gang(d, st, m)
    s.standardprover()
    return _fraga("Varför är jag så trött?", 168)


F_TROTT_SPEL = Facit(
    "bevaka", ("ingen", "bevaka"),
    [("sömnskuld / sömnbrist", r"sömnskuld|sömnbrist|för lite sömn|sover för lite|kort(are)? sömn|\b[45][,.]\d\s*(h|tim)|\b(1\d|2\d)[,.]?\d?\s*timmar? (sömn)?skuld"),
     ("sena kvällar vid datorn", r"sen(a|t)? (kväll|natt)|efter (23|midnatt|01)|0?1[:.]\d\d|spel|dator")],
    [("sjukdom som förklaring", r"(tyder på|beror på) (en )?(infektion|järnbrist|anemi|sjukdom)"),
     ("akut", r"kontakta vården (nu|omedelbart|direkt)")],
    "Sju nätter: spelar på datorn till cirka 01:40, somnar cirka 01:55 och vaknar 07:00, cirka 5 timmars sömn mot "
    "behovet 8: sömnskuld på cirka 20 timmar på en vecka. Rätt: tröttheten förklaras av sömnskuld efter sena "
    "spelkvällar; råd om skärmstopp och läggtid. Fel: sjukdom eller akut larm.")


SCENARIER: list[Scenario] = [
    Scenario("akut_takykardi", "Äkta pulsrusning i vila", "21:40", s_akut_takykardi, F_AKUT),
    Scenario("traning_puls", "Hög puls som är ett löppass", "18:30", s_traning, F_TRANING),
    Scenario("sensorspikar", "Enstaka sensorspikar", "10:15", s_sensorspikar, F_SPIKAR),
    Scenario("klocka_los", "Klockan sitter löst", "20:30", s_klocka_los, F_LOS),
    Scenario("forkylning", "HRV-fall före förkylning", "09:30", s_forkylning, F_FORKYL),
    Scenario("sent_spelande", "Kort sömn av sent spelande", "12:30", s_sent_spel, F_SENT_SPEL),
    Scenario("spo2_dippar", "Nattliga syrefall", "03:40", s_spo2_dippar, F_SPO2),
    Scenario("aktiv_vs_stilla", "Aktiva och stillasittande dagar", "19:00", s_aktiv_stilla, F_AKTIV),
    Scenario("allt_normalt", "Allt normalt", "17:00", s_normal, F_NORMAL),
    Scenario("trott_fraga", "Varför är jag så trött?", "15:00", s_trott_kort_somn, F_TROTT),
    Scenario("lagt_ferritin", "Lågt ferritin och trötthet", "16:00", s_ferritin, F_FERRITIN),
    Scenario("motstridigt", "Motstridiga signaler: träning eller infektion", "09:00", s_motstridigt, F_MOTSTRID),
    Scenario("spo2_akut", "Lågt syre i vila med astma", "14:20", s_spo2_akut, F_SPO2_AKUT),
    Scenario("aterkommande_hopp", "Återkommande pulshopp i vila", "16:05", s_aterkommande, F_ATERK),
    Scenario("stress_projekt", "Stress under projektvecka", "14:00", s_stress, F_STRESS),
    Scenario("trott_spelkvallar", "Trött efter sena spelkvällar", "16:30", s_trott_spel, F_TROTT_SPEL),
]
SCENARIO = {s.id: s for s in SCENARIER}


# ------------------------------------------------------------------ HOLDOUT
# Skrivna EFTER att regelverket i fakta.regelbradska frystes, och körs bara på slutkonfigurationen och
# baslinjen. Regelverket justerades inte efter dem. De är till för att se om förbättringarna generaliserar.

def h_natt_takykardi(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=1)
    for d in (0,):
        s.datorblock(d + 1, 20 * 60, 24 * 60 + 140, "spel")
    s.natt(0, 200, 520)  # sover inte än: natten börjar efter klockan
    s.standardprover()
    a = s.nu - 12 * 60
    sl = s.span(a, s.nu + 60)
    s.steg[s.span(s.nu - 30 * 60, s.nu + 60)] = 0
    s.hr_add[sl] = 78 + s.rng.normal(0, 1.5, sl.stop - sl.start)
    s.generera()
    return _anomali("hr_rest_acute", "akut", "hr", "Mycket hög puls i vila",
                    "Medianpuls 152 slag/min under 10 minuter utan rörelse.", s.nu - 600, s.nu)


def h_cykling(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    s.traning(0, 15 * 60, 50, "cykling", 0.82, takt=0)
    return _fraga("Varför låg min puls på över 150 i nästan en timme i eftermiddags?", 8)


def h_anemi(s: Sim) -> dict[str, Any]:
    s.standard(steg_mal=5000)
    s.standardprover(dagar_sedan=300)
    d = s.datum(12)
    for analyt, v, enh, lo, hi, fl in (("Hb", 112, "g/L", 134, 170, "L"), ("Ferritin", 6, "µg/L", 15, 150, "L"),
                                       ("MCV", 74, "fL", 82, 98, "L"), ("TSH", 1.9, "mIE/L", 0.4, 4.0, None)):
        lb = {"date": d, "analyt": analyt, "varde": v, "enhet": enh, "lag": lo, "hog": hi}
        if fl:
            lb["flagga"] = fl
        s.labb.append(lb)
    s.hr_add += 6  # lite högre puls dygnet runt, som vid blodbrist
    return _fraga("Jag blir andfådd i trappor och är trött. Vad säger mina värden?", 168)


def h_lag_nattpuls(s: Sim) -> dict[str, Any]:
    s.standard(steg_mal=9000)
    s.standardprover()
    return _fraga("Min puls är under 50 på natten. Är det farligt?", 168)


def h_enstaka_syrefall(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    k = s.idx(s.ts(0, 200))
    s.spo2_add[k:k + 2] -= 11  # ett enda fall, två minuter, en natt
    return _fraga("Klockan visade 85 procent syre i natt. Ska jag vara orolig?", 24)


HOLDOUT: list[Scenario] = [
    Scenario("h_natt_takykardi", "Holdout: pulsrusning sent på kvällen", "02:10", h_natt_takykardi, Facit(
        "kontakta_vard_nu", ("kontakta_vard_nu",),
        [("hög puls med siffra", r"\b1[45]\d\b"), ("i vila", r"vila|utan (rörelse|steg)|inga steg|0 steg|sitter|spel")],
        [("bortförklarar med träning", r"(beror|förklaras|orsakas)\w* (troligen |sannolikt )?(på|av) (träning|motion)")],
        "Klockan 02:10, spelar vid datorn, pulsen har slagit om från cirka 70 till cirka 150 i 12 minuter utan steg och utan "
        "pass. Rätt: kontakta vården nu.")),
    Scenario("h_cykling", "Holdout: hög puls under cykelpass utan steg", "18:00", h_cykling, Facit(
        "ingen", ("ingen", "bevaka"),
        [("kopplar till cykelpasset", r"cykl|träning|pass")],
        [("larmar", r"kontakta vården (nu|omedelbart|direkt)|ring 112"),
         ("rytmrubbning som fakta", r"(hade|fick) (en )?(pulsrusning|takykardi)")],
        "Pulsen 150-160 i 50 minuter kom under ett registrerat cykelpass (inga steg, men passet finns). Rätt: träningspuls, ingen oro.")),
    Scenario("h_anemi", "Holdout: blodbrist i provsvaren", "11:00", h_anemi, Facit(
        "ta_upp_med_varden", ("ta_upp_med_varden",),
        [("Hb lågt", r"\bhb\b|hemoglobin|blodvärde"), ("ferritin/järn", r"ferritin|järn"),
         ("siffra", r"\b112\b|\b6\b|\b74\b")],
        [("akut", r"ring 112|kontakta vården (nu|omedelbart|direkt)")],
        "Hb 112 g/L (under 134), ferritin 6, MCV 74: blodbrist med tömda järnförråd som kan förklara andfåddhet och "
        "trötthet. Rätt: ta upp med vården (inte akut om inga alarmsymtom).")),
    Scenario("h_lag_nattpuls", "Holdout: låg nattpuls som är normal", "12:00", h_lag_nattpuls, Facit(
        "ingen", ("ingen",),
        [("nattpulsen med siffra", r"\b[45]\d\b"), ("normalt", r"normal|vanlig|inom|ofarlig|inget att oroa|stabil")],
        [("vårdkontakt", r"kontakta vården|boka tid"), ("bradykardi som sjukdom", r"(har|du har) bradykardi")],
        "Nattpulsen 45-52 är stabil och samma som baslinjen; vaken puls normal. Rätt: inget att oroa sig för.")),
    Scenario("h_enstaka_syrefall", "Holdout: ett enda syrefall en natt", "09:30", h_enstaka_syrefall, Facit(
        "ingen", ("ingen", "bevaka"),
        [("enstaka", r"enstaka|ett (enda )?fall|en gång|kortvarig|isolerad|två minuter|enda"),
         ("mätfel eller sovställning", r"mätfel|sovställ|klockan|sensor|artefakt|tryck")],
        [("sömnapné som fakta", r"(har|tyder på) sömnapn"), ("akut", r"ring 112")],
        "Ett enda fall till cirka 85 % under två minuter en natt, resten av natten och alla andra nätter normalt utan "
        "upprepade fall. Rätt: troligen mätfel eller sovställning; ingen åtgärd, bevaka om det upprepas.")),
]
SCENARIO.update({s.id: s for s in HOLDOUT})


# ------------------------------------------------------------------ HOLDOUT 2
# Skrivna innan holdout 1 hade körts, för att kunna mäta igen om något behöver rättas efter holdout 1.

def h2_morgonlopning(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    s.traning(0, 7 * 60 + 50, 35, "löpning", 0.95, takt=168)
    return _fraga("Varför låg min puls på nästan 180 i morse?", 12)


def h2_snarkning(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover()
    for dag in range(6, -1, -1):
        a, b = s.ts(dag, -20), s.ts(dag, 430)
        t = a + 2400
        while t < b - 600:
            k = s.idx(t)
            s.spo2_add[k:k + 2] -= s.rng.uniform(5, 8)
            t += int(s.rng.uniform(5, 9) * 60)
    return _fraga("Min sambo säger att jag snarkar och slutar andas ibland. Syns något i datan?", 168)


def h2_feber(s: Sim) -> dict[str, Any]:
    s.standard(till_dag=2)
    s.standard(fran_dag=1, till_dag=0, steg_mal=1500, lagg=-120, upp=560)
    s.standardprover()
    for dag, hr, temp, resp, hrv in ((1, 10, 0.9, 2.5, 0.6), (0, 13, 1.2, 3.0, 0.5)):
        sl = s.span(s.ts(dag, -180), s.ts(dag, 600))
        s.hr_add[sl] += hr
        s.temp_add[sl] += temp
        s.resp_add[sl] += resp
        s.hrv_fak[sl] *= hrv
    return _fraga("Jag känner mig hängig sedan i går. Vad säger klockan?", 72)


def h2_tsh(s: Sim) -> dict[str, Any]:
    s.standard()
    s.standardprover(dagar_sedan=300)
    d = s.datum(15)
    for analyt, v, enh, lo, hi, fl in (("TSH", 0.05, "mIE/L", 0.4, 4.0, "L"), ("T4, fritt", 31, "pmol/L", 12, 22, "H"),
                                       ("Hb", 146, "g/L", 134, 170, None)):
        lb = {"date": d, "analyt": analyt, "varde": v, "enhet": enh, "lag": lo, "hog": hi}
        if fl:
            lb["flagga"] = fl
        s.labb.append(lb)
    s.hr_add[s.span(s.ts(10, 0), s.nu + 60)] += 14  # de senaste tio dagarna
    return _fraga("Varför har jag hjärtklappning och svettas fast jag sitter still?", 168)


def h2_spel_ok(s: Sim) -> dict[str, Any]:
    s.standard(lagg=-30, upp=480, kvall="spel", kvall_tid=(18 * 60, 23 * 60))
    s.standardprover()
    return _fraga("Spelar jag för mycket? Märks det på sömnen?", 168)


HOLDOUT2: list[Scenario] = [
    Scenario("h2_morgonlopning", "Holdout 2: hög puls under morgonlöpning", "12:00", h2_morgonlopning, Facit(
        "ingen", ("ingen", "bevaka"),
        [("kopplar till löppasset", r"löp|träning|pass")],
        [("larmar", r"kontakta vården (nu|omedelbart|direkt)|ring 112")],
        "Pulsen 170-180 kom under ett registrerat löppass 07:50-08:25 med cirka 168 steg/min. Rätt: träningspuls, ingen oro.")),
    Scenario("h2_snarkning", "Holdout 2: snarkning och syrefall", "13:00", h2_snarkning, Facit(
        "ta_upp_med_varden", ("ta_upp_med_varden",),
        [("syrefall", r"syre|spo2|mättnad"), ("flera nätter", r"nätter|varje natt|återkommande|upprepade|mönster"),
         ("utredning", r"sömnapn|andningsuppeh|utredning|sömnregistrering")],
        [("lugnar", r"inget att oroa")],
        "Varje natt senaste veckan syrefall på 5-8 procentenheter var 5-9:e minut (cirka 8 per timme), plus sambons uppgift om "
        "andningsuppehåll. Rätt: ta upp med vården för sömnutredning, inte akut.")),
    Scenario("h2_feber", "Holdout 2: tecken på feber", "10:00", h2_feber, Facit(
        "bevaka", ("bevaka", "ta_upp_med_varden"),
        [("temperatur upp", r"temp"), ("puls upp", r"puls"), ("vila / infektion", r"vila|infektion|sjuk|feber|förkyl")],
        [("akut", r"ring 112"), ("träna", r"(kör|gör) (ett )?(hårt|intervall)")],
        "Två nätter: hudtemperatur +0,9 och +1,2 grader, nattpuls +10-13, andning +2,5-3, HRV halverad, lite rörelse. "
        "Rätt: tecken på infektion/feber, vila, bevaka, kontakta vården vid andnöd eller hög feber.")),
    Scenario("h2_tsh", "Holdout 2: lågt TSH och hög vilopuls", "15:00", h2_tsh, Facit(
        "ta_upp_med_varden", ("ta_upp_med_varden",),
        [("TSH", r"tsh|sköldkörtel|t4"), ("vilopuls", r"puls")],
        [("akut", r"ring 112")],
        "TSH 0,05 (under referens) och fritt T4 31 (över) för 15 dagar sedan, pulsen cirka 14 slag högre dygnet runt de senaste "
        "tio dagarna. Rätt: provsvaren tyder på överfunktion i sköldkörteln, ta upp med vården.")),
    Scenario("h2_spel_ok", "Holdout 2: spel på kvällen men bra sömn", "14:00", h2_spel_ok, Facit(
        "ingen", ("ingen",),
        [("spelminuter", r"spel"), ("sömnen räcker", r"sömn")],
        [("vårdkontakt", r"kontakta vården|boka tid")],
        "Spelar 18-23 varje kväll men somnar cirka 23:30 och sover cirka 8 timmar; HRV och nattpuls normala. Rätt: sömnen "
        "påverkas inte märkbart, ingen oro.")),
]
SCENARIO.update({s.id: s for s in HOLDOUT2})
