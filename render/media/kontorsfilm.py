#!/usr/bin/env python3
"""Spelar in kontorets trailerscen (web/src/office/film.ts) bildruta för bildruta i 4x upplösning.

Kräver att Vite kör: cd web && npx vite --port 5199
Körs med serverns venv (där Playwright finns):
  ../../server/.venv/bin/python kontorsfilm.py [--till S] [--prov 0.3,2.4,...]
Utdata: render/media/ut/kontor/00000.jpg ... (30 fps, scentid = bildnummer / 30)
"""
import argparse, asyncio
from pathlib import Path
from playwright.async_api import async_playwright

UT = Path(__file__).resolve().parent / "ut/kontor"
URL = "http://localhost:5199/film.html"
FPS = 30


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--till", type=float, default=26.0)
    ap.add_argument("--prov", help="spara bara de här tiderna (kommaseparerade sekunder), som PNG i ut/kontor-prov")
    ap.add_argument("--dpr", type=float, default=4)
    a = ap.parse_args()
    prov = sorted(float(x) for x in a.prov.split(",")) if a.prov else None
    ut = UT.parent / "kontor-prov" if prov else UT
    ut.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 860, "height": 640}, device_scale_factor=a.dpr)
        await pg.goto(URL)
        await pg.wait_for_function("window.filmReady === true")
        await pg.evaluate("document.fonts.ready")
        el = await pg.query_selector("#stage .office")
        n = int(a.till * FPS)
        for i in range(n):
            await pg.evaluate(f"filmStep({1 / FPS})")
            t = (i + 1) / FPS
            if prov:
                if any(abs(t - x) < 0.5 / FPS for x in prov):
                    await el.screenshot(path=str(ut / f"{t:05.2f}.png"))
            else:
                await el.screenshot(path=str(ut / f"{i:05d}.jpg"), type="jpeg", quality=93)
            if i % 60 == 0: print(f"{t:.1f} s", flush=True)
        await b.close()


asyncio.run(main())
