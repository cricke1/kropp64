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
            c.execute(
                "INSERT OR REPLACE INTO journal(id, date, unit, author, kind, title, text, fetched) VALUES (?,?,?,?,?,?,?,?)",
                (_hid(kind, datum, text[:400]), datum, p.get("enhet"), p.get("yrke"), kind,
                 p.get("rubrik", "")[:200], text, time.time()))
            n += 1
    return n


def tolka_provsvar(rader: list[dict[str, str]]) -> int:
    n = 0
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
            c.execute(
                "INSERT OR REPLACE INTO labs(id, date, analyte, value, value_raw, unit, ref_low, ref_high, flag, fetched)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (_hid(datum, analyt, varde), datum, analyt, value, varde, unit or r.get("enhet"), lo, hi, flag, time.time()))
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
        if "journalen.1177.se" in page.url or "e-tjanster.1177.se" in page.url:
            return True
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
    counts = {"sidor": 0, "anteckningar": 0, "provsvar": 0}
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
        kategorier = {a["href"]: a["text"] for a in start["nav"] if "/logout" not in a["href"].lower()}
        (outdir / "start.json").write_text(json.dumps(start, ensure_ascii=False, indent=1))

        for i, (url, namn) in enumerate(kategorier.items()):
            _status("hamtar", kategori=namn, steg=i + 1, av=len(kategorier))
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                # Expandera allt som går att expandera.
                for _ in range(20):
                    knapp = page.locator("button:has-text('Visa fler'), button:has-text('Visa mer'), "
                                         "button[aria-expanded='false']").first
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
            prov = [r for t in data["tabeller"] for r in _tabell_till_provsvar(t)]
            if prov:
                counts["provsvar"] += tolka_provsvar(prov)
            else:
                counts["anteckningar"] += tolka_anteckningar(data["poster"], namn.lower())
        await browser.close()
    _status("klar", **counts, mapp=str(outdir))
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
