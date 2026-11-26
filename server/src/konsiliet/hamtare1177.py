"""Hämtar journal och provsvar från 1177 Journalen.

Inloggning sker med BankID. Det går inte och ska inte gå att automatisera bort: personen godkänner
varje hämtning själv. Hämtaren gör resten.

Flöde:
  1. Headless Chromium öppnar journalen.1177.se och väljer BankID.
  2. Svaret från idp:ns /bank-id/Citizen/order fångas. Innehåller det en autostarttoken skickas en
     bankid:///-länk till mobilen ("BankID på denna enhet" fast på telefonen).
  3. Samtidigt byts till QR-läget och QR-bilden strömmas varje sekund som sync.1177-händelser,
     så att den kan skannas från webben på en annan skärm.
  4. När inloggningen är klar besöks varje journalkategori. Allt sparas rått lokalt
     (~/.konsiliet/1177/<tidsstämpel>/) och tolkas sedan till journal- och labbtabellerna.

Första hämtningen sparar rå HTML för varje sida, så att tolkningen kan finjusteras mot hur
just den här journalen ser ut utan att behöva logga in igen.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import db
from .bus import bus

log = logging.getLogger("1177")

START = "https://journalen.1177.se/"
RAW_DIR = Path("~/.konsiliet/1177").expanduser()
LOGIN_TIMEOUT = 180
_running = threading.Lock()
# Nya rader i den pågående hämtningen (återställs vid start). Visas i appen: "3 nya anteckningar".
NYA = {"anteckningar": 0, "provsvar": 0}


def _sidhash(namn: str, text: str) -> tuple[str, bool]:
    """Sidans hash och om den ser exakt likadan ut som vid förra lyckade tolkningen. Oförändrade sidor
    tolkas inte igen, så en hämtning utan nytt i journalen går på sekunder i stället för minuter med den
    lokala modellen. Hashen sparas först när tolkningen lyckats (_spara_sidhash)."""
    h = hashlib.sha256(text.encode()).hexdigest()
    with db.tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS sync1177_sida (namn TEXT PRIMARY KEY, hash TEXT, ts REAL)")
        r = c.execute("SELECT hash FROM sync1177_sida WHERE namn = ?", (namn,)).fetchone()
    return h, r is not None and r[0] == h


def _spara_sidhash(namn: str, h: str) -> None:
    with db.tx() as c:
        c.execute("INSERT OR REPLACE INTO sync1177_sida VALUES (?,?,?)", (namn, h, time.time()))


def status() -> dict[str, Any]:
    """För appen: när journalen senast hämtades, hur mycket som finns och om en hämtning pågår."""
    with db.tx() as c:
        klar = c.execute("SELECT ts, payload FROM events WHERE kind = 'sync.1177' AND payload LIKE '%\"klar\"%' "
                         "ORDER BY id DESC LIMIT 1").fetchone()
        senaste = c.execute("SELECT ts, payload FROM events WHERE kind = 'sync.1177' ORDER BY id DESC LIMIT 1").fetchone()
        n_j = c.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        n_l = c.execute("SELECT COUNT(*) FROM labs").fetchone()[0]
    return {"senast_klar": klar[0] if klar else None, "senast_klar_info": json.loads(klar[1]) if klar else None,
            "anteckningar": n_j, "provsvar": n_l, "pagar": _running.locked(),
            "senaste_status": json.loads(senaste[1]).get("status") if senaste else None}


def _status(status: str, **extra: Any) -> None:
    bus.publish("sync.1177", {"status": status, **extra}, persist=status not in ("qr",))


# ---------------------------------------------------------------- tolkning

DATE = re.compile(r"\b(20\d{2}|19\d{2})-(\d{2})-(\d{2})\b")
NUMVAL = re.compile(r"^\s*([<>]?\s*-?\d+(?:[.,]\d+)?)\s*([^\s\d].*)?$")
REFINT = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*[-–]\s*(-?\d+(?:[.,]\d+)?)")


def _hid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _f(x: str) -> float | None:
    try:
        return float(x.replace(",", ".").replace("<", "").replace(">", "").strip())
    except ValueError:
        return None


def tolka_anteckningar(poster: list[dict[str, str]], kind: str) -> int:
    n = 0
    with db.tx() as c:
        for p in poster:
            text = p.get("text", "").strip()
            if len(text) < 15:
                continue
            m = DATE.search(p.get("rubrik", "") + " " + text)
            datum = "-".join(m.groups()) if m else ""
            jid = _hid(datum, re.sub(r"\W+", "", text)[:600])
            ny = c.execute("SELECT 1 FROM journal WHERE id = ?", (jid,)).fetchone() is None
            c.execute(
                "INSERT OR REPLACE INTO journal(id, date, unit, author, kind, title, text, fetched) VALUES (?,?,?,?,?,?,?,?)",
                (jid, datum, p.get("enhet"), p.get("yrke"), kind, p.get("rubrik", "")[:200], text, time.time()))
            n += 1
            NYA["anteckningar"] += ny
    return n


def tolka_provsvar(rader: list[dict[str, str]]) -> int:
    n = 0
    sedda: dict[str, int] = {}
    with db.tx() as c:
        for r in rader:
            analyt, varde = r.get("analys", "").strip(), r.get("varde", "").strip()
            if not analyt or not varde:
                continue
            m = NUMVAL.match(varde)
            value = _f(m.group(1)) if m else None
            unit = (m.group(2) or "").strip() if m else r.get("enhet")
            lo = hi = None
            ri = REFINT.search(r.get("referens", ""))
            if ri:
                lo, hi = _f(ri.group(1)), _f(ri.group(2))
            flag = None
            if value is not None and lo is not None and value < lo:
                flag = "L"
            if value is not None and hi is not None and value > hi:
                flag = "H"
            datum = r.get("datum", "")
            lid = _hid(datum, analyt, varde, str(sedda.setdefault(f"{datum}|{analyt}|{varde}", 0)))
            NYA["provsvar"] += c.execute("SELECT 1 FROM labs WHERE id = ?", (lid,)).fetchone() is None
            c.execute(
                "INSERT OR REPLACE INTO labs(id, date, analyte, value, value_raw, unit, ref_low, ref_high, flag, fetched)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (lid, datum, analyt, value, varde, unit or r.get("enhet"), lo, hi, flag, time.time()))
            sedda[f"{datum}|{analyt}|{varde}"] = sedda.get(f"{datum}|{analyt}|{varde}", 0) + 1
            n += 1
    return n


# Körs i sidan: generisk extraktion som klarar både listor med expanderbara poster och tabeller.
EXTRACT_JS = r"""
() => {
  const txt = e => (e?.innerText || '').replace(/\s+\n/g, '\n').trim();
  const poster = [];
  const kandidater = document.querySelectorAll('article, li[class*="item" i], div[class*="card" i], div[class*="entry" i], section');
  for (const k of kandidater) {
    const t = txt(k);
    if (t.length < 15 || t.length > 20000) continue;
    if (k.querySelector('article, li[class*="item" i]')) continue; // bara innersta nivån
    const rubrik = txt(k.querySelector('h1,h2,h3,h4,[class*="title" i],[class*="heading" i]'));
    poster.push({rubrik, text: t});
  }
  const tabeller = [];
  for (const tb of document.querySelectorAll('table')) {
    const head = [...tb.querySelectorAll('thead th, tr:first-child th')].map(txt);
    const rows = [...tb.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('td,th')].map(txt));
    tabeller.push({head, rows, caption: txt(tb.querySelector('caption'))});
  }
  const nav = [...document.querySelectorAll('a[href]')]
    .map(a => ({text: txt(a), href: a.href}))
    .filter(a => a.href.includes('journalen.1177.se') && a.text.length > 1 && a.text.length < 60);
  return {url: location.href, title: document.title, poster, tabeller, nav};
}
"""

PROV_KOLUMNER = {"analys": ("analys", "undersökning", "prov"), "varde": ("resultat", "värde", "svar"),
                 "referens": ("referens",), "datum": ("datum", "provtagning"), "enhet": ("enhet",)}


def _tabell_till_provsvar(t: dict[str, Any]) -> list[dict[str, str]]:
    head = [h.lower() for h in t.get("head", [])]
    idx: dict[str, int] = {}
    for key, ord_ in PROV_KOLUMNER.items():
        for i, h in enumerate(head):
            if any(o in h for o in ord_) and key not in idx:
                idx[key] = i
    if "analys" not in idx or "varde" not in idx:
        return []
    datum_fallback = ""
    m = DATE.search(t.get("caption", ""))
    if m:
        datum_fallback = "-".join(m.groups())
    out = []
    for row in t.get("rows", []):
        r = {k: (row[i] if i < len(row) else "") for k, i in idx.items()}
        if not r.get("datum"):
            r["datum"] = datum_fallback
        out.append(r)
    return out


# ---------------------------------------------------------------- reserv: lokal modell tolkar sidtexten

LLM_SCHEMA = {"type": "object", "properties": {
    "anteckningar": {"type": "array", "items": {"type": "object", "properties": {
        "datum": {"type": "string", "description": "YYYY-MM-DD"}, "enhet": {"type": "string"},
        "yrke": {"type": "string"}, "rubrik": {"type": "string"}, "text": {"type": "string"}},
        "required": ["datum", "text"]}},
    "provsvar": {"type": "array", "items": {"type": "object", "properties": {
        "datum": {"type": "string"}, "analys": {"type": "string"}, "varde": {"type": "string"},
        "referens": {"type": "string"}}, "required": ["analys", "varde"]}}},
    "required": ["anteckningar", "provsvar"]}


def _llm_tolka(sidtext: str, kategori: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Används bara när heuristiken inte hittar något. Allt som modellen returnerar kontrolleras mot
    sidtexten: ett provvärde eller datum som inte står ordagrant i texten kastas."""
    from . import llm
    from .config import settings

    anteckningar: list[dict[str, str]] = []
    prov: list[dict[str, str]] = []
    if len(sidtext) > 200000:
        _status("varning", detalj=f"Sidan är {len(sidtext)} tecken, bara de första 200 000 tolkas")
    for i in range(0, min(len(sidtext), 200000), 6000):
        bit = sidtext[i:i + 6500]
        r = llm.chat(settings.model_orchestrator, [
            {"role": "system", "content": "Du tolkar text från en svensk patientjournal (1177) till strukturerad data. "
             "Skriv av exakt, sammanfatta inte och hitta inte på något. Tomma listor om inget finns."},
            {"role": "user", "content": f"Kategori: {kategori}\n\n{bit}"}], fmt=LLM_SCHEMA, temperature=0,
            max_tokens=3000)
        try:
            d = json.loads(r.content)
        except json.JSONDecodeError:
            continue
        normal = re.sub(r"\s+", " ", sidtext)
        rader = [re.sub(r"\s+", " ", r) for r in sidtext.splitlines()]
        for a in d.get("anteckningar", []):
            datum, text = a.get("datum", "").strip(), re.sub(r"\s+", " ", a.get("text", "")).strip()
            # Datumet måste stå i sidan, och anteckningstexten måste vara avskriven, inte sammanfattad:
            # minst 80 % av dess ord ska finnas i sidtexten.
            ord_ = text.split()
            tackning = sum(1 for o in ord_ if o in normal) / max(1, len(ord_))
            if DATE.fullmatch(datum) and datum in normal and len(text) > 15 and tackning >= 0.8:
                anteckningar.append(a)
        for p in d.get("provsvar", []):
            analys, varde = str(p.get("analys", "")).strip(), str(p.get("varde", "")).strip()
            if not analys or not varde:
                continue
            # Analys och värde måste stå på samma rad, i den ordningen, med värdet som ett helt tal
            # (så att 14 inte matchar 141 och ett värde inte kan paras med fel analys).
            monster = re.compile(re.escape(analys) + r".*?(?<![\d,.])" + re.escape(varde.split()[0]) + r"(?![\d,.])")
            ok = any(monster.search(r) for r in rader)
            if ok:
                prov.append(p)
    return anteckningar, prov


# ---------------------------------------------------------------- webbläsaren

async def _login(page: Any) -> bool:
    autostart: dict[str, str] = {}

    async def on_response(resp: Any) -> None:
        if "/bank-id/" in resp.url and "/order" in resp.url:
            try:
                body = await resp.text()
                m = re.search(r'"auto[_]?start[_]?token"\s*:\s*"([^"]+)"', body, re.I)
                if m:
                    autostart["token"] = m.group(1)
            except Exception:
                pass

    page.on("response", on_response)
    await page.goto(START, wait_until="domcontentloaded")
    await page.get_by_text("BankID", exact=True).first.click()
    await page.wait_for_timeout(2500)
    if autostart.get("token"):
        _status("bankid_lank", url=f"bankid:///?autostarttoken={autostart['token']}&redirect=null")
    try:
        await page.get_by_text(re.compile("Klicka här för att logga in", re.I)).first.click(timeout=5000)
    except Exception:
        pass
    t0 = time.time()
    while time.time() - t0 < LOGIN_TIMEOUT:
        # URL:en räcker inte (journalen.1177.se syns redan före inloggning). Kräv en utloggningsknapp.
        if "idp." not in page.url and ("1177.se" in page.url):
            try:
                if await page.get_by_text(re.compile(r"^\s*Logga ut\s*$", re.I)).count():
                    return True
            except Exception:
                pass
        img = page.locator('img[alt*="QR-kod"]').first
        try:
            if await img.count():
                png = await img.screenshot(timeout=2000)
                _status("qr", png=base64.b64encode(png).decode(), kvar=int(LOGIN_TIMEOUT - (time.time() - t0)))
        except Exception:
            pass
        await page.wait_for_timeout(1000)
    return False


async def _hamta() -> dict[str, int]:
    from playwright.async_api import async_playwright

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = RAW_DIR / stamp
    outdir.mkdir(parents=True, exist_ok=True)
    counts = {"sidor": 0, "anteckningar": 0, "provsvar": 0, "oforandrade": 0}
    NYA["anteckningar"] = NYA["provsvar"] = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(locale="sv-SE", viewport={"width": 1280, "height": 1800})
        page = await ctx.new_page()
        _status("loggar_in")
        if not await _login(page):
            _status("misslyckades", detail="BankID godkändes inte inom tidsgränsen")
            await browser.close()
            return counts
        _status("inloggad")
        await page.goto(START, wait_until="networkidle")
        start = await page.evaluate(EXTRACT_JS)
        UNDVIK = re.compile(r"logout|logga|lang|sprak|språk|installning|inställning|kontakt|hjalp|hjälp|om-|cookie|#", re.I)
        kategorier = {a["href"]: a["text"] for a in start["nav"]
                      if not UNDVIK.search(a["href"]) and not UNDVIK.search(a["text"])}
        (outdir / "start.json").write_text(json.dumps(start, ensure_ascii=False, indent=1))

        for i, (url, namn) in enumerate(kategorier.items()):
            _status("hamtar", kategori=namn, steg=i + 1, av=len(kategorier))
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                # Expandera allt som går att expandera.
                for _ in range(40):
                    knapp = page.locator("main button:has-text('Visa fler'), main button:has-text('Visa mer'), "
                                         "main button:has-text('Visa hela'), main [role='region'] "
                                         "button[aria-expanded='false'], main article button[aria-expanded='false']").first
                    if not await knapp.count():
                        break
                    await knapp.click(timeout=3000)
                    await page.wait_for_timeout(400)
                data = await page.evaluate(EXTRACT_JS)
            except Exception as e:
                log.warning("kategori %s: %s", namn, e)
                continue
            counts["sidor"] += 1
            safe = re.sub(r"[^\w-]+", "_", namn)[:40]
            (outdir / f"{i:02d}_{safe}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
            (outdir / f"{i:02d}_{safe}.html").write_text(await page.content())
            sidhash, oforandrad = _sidhash(url, json.dumps(data, ensure_ascii=False, sort_keys=True))
            if oforandrad:
                counts["oforandrade"] += 1
                continue
            prov = [r for t in data["tabeller"] for r in _tabell_till_provsvar(t)]
            if prov:
                counts["provsvar"] += tolka_provsvar(prov)
            else:
                n = tolka_anteckningar(data["poster"], namn.lower())
                counts["anteckningar"] += n
                if n == 0:
                    sidtext = await page.evaluate("() => document.body.innerText")
                    if len(sidtext) > 200:
                        _status("tolkar", kategori=namn, metod="lokal modell")
                        ant, pv = await asyncio.to_thread(_llm_tolka, sidtext, namn)
                        counts["anteckningar"] += tolka_anteckningar(
                            [{"rubrik": a.get("rubrik", "") + " " + a.get("datum", ""), "text": a["text"],
                              "enhet": a.get("enhet"), "yrke": a.get("yrke")} for a in ant], namn.lower())
                        counts["provsvar"] += tolka_provsvar(pv)
            _spara_sidhash(url, sidhash)
        await browser.close()
    _status("klar", **counts, nya_anteckningar=NYA["anteckningar"], nya_provsvar=NYA["provsvar"], mapp=str(outdir))
    return counts


def start_async() -> bool:
    if not _running.acquire(blocking=False):
        return False

    def run() -> None:
        try:
            asyncio.run(_hamta())
        except Exception as e:
            log.exception("1177-hämtning kraschade")
            _status("misslyckades", detail=str(e))
        finally:
            _running.release()

    threading.Thread(target=run, name="1177", daemon=True).start()
    return True
