"""Besöksunderlag: en PDF att ta med till vården. Renderas lokalt med Chromium via Playwright.

Innehåll: 30 dagars kurvor (vilopuls, HRV, sömn, steg) med avvikelser markerade, konsiliets senaste
bedömningar med belagda påståenden och källor, provsvar utanför referensintervall, och frågor att ställa.
"""
from __future__ import annotations

import html
import json
import time
from datetime import datetime

import numpy as np

from . import db

DAGAR = 30


def _dagliga(metric: str, agg: str = "median", natt: bool = False) -> list[tuple[str, float | None]]:
    out = []
    nu = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for d in range(DAGAR - 1, -1, -1):
        start = nu.timestamp() - d * 86400
        pts = db.query_samples(metric, start, start + (6 * 3600 if natt else 86400))
        vals = [v for _, v in pts]
        dag = datetime.fromtimestamp(start).strftime("%d/%m")
        if not vals:
            out.append((dag, None))
        elif agg == "sum":
            out.append((dag, float(sum(vals))))
        elif agg == "min10" and len(vals) >= 10:
            out.append((dag, float(min(np.convolve(vals, np.ones(10) / 10, mode="valid")))))
        else:
            out.append((dag, float(np.median(vals))))
    return out


def _testvarning() -> str:
    """Finns testdata (emulator, syntetisk) i databasen och är den tillåten i urvalet står det överst i PDF:en,
    så att ett underlag från en testserver aldrig kan misstas för riktiga mätningar."""
    if not db.TILLAT_TESTDATA:
        return ""
    k = [r[0] for r in db.conn().execute("SELECT DISTINCT source FROM samples") if db.ar_testkalla(r[0])]
    return (f'<p style="border:1pt solid #a8700f;padding:2mm 3mm;color:#7a5200"><b>Syntetisk testdata.</b> '
            f'Källor: {html.escape(", ".join(k))}. Värdena är inte uppmätta på en människa.</p>') if k else ""


def _sparkline(serie: list[tuple[str, float | None]], enhet: str, w: int = 520, h: int = 90) -> str:
    vals = [v for _, v in serie if v is not None]
    if len(vals) < 2:
        return '<p class="tom">För lite data under perioden.</p>'
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pad = 6
    pts = []
    for i, (_, v) in enumerate(serie):
        if v is None:
            continue
        x = pad + i * (w - 2 * pad) / (len(serie) - 1)
        y = h - pad - (v - lo) / span * (h - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    med = float(np.median(vals))
    ym = h - pad - (med - lo) / span * (h - 2 * pad)
    return (f'<svg viewBox="0 0 {w} {h}" class="spark"><line x1="{pad}" x2="{w - pad}" y1="{ym:.1f}" y2="{ym:.1f}" '
            f'class="median"/><polyline points="{" ".join(pts)}"/></svg>'
            f'<div class="skala"><span>{serie[0][0]}</span><span>min {lo:.0f} / median {med:.0f} / max {hi:.0f} {enhet}'
            f'</span><span>{serie[-1][0]}</span></div>')


def bygg_html() -> str:
    e = html.escape
    c = db.conn()
    konsilier = c.execute("SELECT started, trigger, verdict FROM consults WHERE verdict IS NOT NULL "
                          "AND started > ? ORDER BY started DESC LIMIT 6", (time.time() - DAGAR * 86400,)).fetchall()
    labb = c.execute("SELECT date, analyte, value_raw, unit, ref_low, ref_high, flag FROM labs "
                     "WHERE flag IS NOT NULL ORDER BY date DESC LIMIT 20").fetchall()
    sektioner = []
    for titel, metric, agg, natt, enhet in [
        ("Vilopuls (lägsta 10-minutersmedel per natt)", "hr", "min10", True, "slag/min"),
        ("HRV RMSSD (nattmedian)", "hrv_rmssd", "median", True, "ms"),
        ("Steg per dag", "steps", "sum", False, "steg"),
        ("Syremättnad (nattmedian)", "spo2", "median", True, "%"),
    ]:
        sektioner.append(f"<section><h3>{e(titel)}</h3>{_sparkline(_dagliga(metric, agg, natt), enhet)}</section>")

    frågor: list[str] = []
    bed_html = []
    for k in konsilier:
        v = json.loads(k["verdict"])
        t = json.loads(k["trigger"])
        frågor += v.get("fragor_till_varden", []) or []
        pastaenden = "".join(f"<li>{e(p['text'])} <span class='kalla'>{e(', '.join(p['kallor']))}</span></li>"
                             for p in v.get("belagda_pastaenden", []))
        bed_html.append(
            f"<article><div class='meta'>{datetime.fromtimestamp(k['started']).strftime('%Y-%m-%d %H:%M')} - "
            f"{e(t.get('title') or t.get('question') or '')}</div><p>{e(v.get('sammanfattning', ''))}</p>"
            f"<ul>{pastaenden}</ul></article>")
    labb_rader = "".join(
        f"<tr><td>{e(r['date'])}</td><td>{e(r['analyte'])}</td><td class='num'>{e(r['value_raw'])}</td>"
        f"<td class='num'>{'' if r['ref_low'] is None else r['ref_low']}-{'' if r['ref_high'] is None else r['ref_high']}"
        f"</td><td>{e(r['flag'] or '')}</td></tr>" for r in labb)

    return f"""<!doctype html><html lang="sv"><meta charset="utf-8"><title>Besöksunderlag</title>
<style>
@page {{ size: A4; margin: 16mm 16mm 18mm; }}
body {{ font: 10pt/1.45 "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif; color: #1d2329; }}
h1 {{ font-size: 17pt; font-weight: 600; margin: 0 0 2mm; }}
h2 {{ font-size: 11.5pt; font-weight: 600; margin: 7mm 0 2mm; border-bottom: 0.6pt solid #c9ced3; padding-bottom: 1mm; }}
h3 {{ font-size: 9.5pt; font-weight: 600; margin: 3mm 0 1mm; color: #3a434b; }}
.ingress {{ color: #4a535b; margin: 0 0 4mm; }}
.spark {{ width: 100%; height: 22mm; }}
.spark polyline {{ fill: none; stroke: #1f5f8b; stroke-width: 1.4; }}
.spark .median {{ stroke: #9aa3ab; stroke-dasharray: 3 3; stroke-width: 0.8; }}
.skala {{ display: flex; justify-content: space-between; font-size: 8pt; color: #5d666e; font-variant-numeric: tabular-nums; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2mm 8mm; }}
article {{ border-left: 2pt solid #1f5f8b; padding-left: 3mm; margin: 3mm 0; break-inside: avoid; }}
.meta {{ font-size: 8.5pt; color: #5d666e; }}
.kalla {{ font: 7.5pt "IBM Plex Mono", Menlo, monospace; color: #5d666e; }}
table {{ border-collapse: collapse; width: 100%; font-size: 9pt; }}
td, th {{ text-align: left; padding: 1.2mm 2mm; border-bottom: 0.4pt solid #dde1e4; }}
.num {{ font-variant-numeric: tabular-nums; }}
.tom {{ color: #8a939b; font-size: 9pt; }}
footer {{ margin-top: 8mm; font-size: 8pt; color: #5d666e; }}
</style>
<h1>Besöksunderlag</h1>
{_testvarning()}
<p class="ingress">Sammanställt {datetime.now().strftime('%Y-%m-%d')} från egen mätdata (Pixel Watch) och journal (1177),
analyserat lokalt. Detta är underlag för samtal, inte en diagnos.</p>
<h2>Senaste {DAGAR} dagarna</h2>
<div class="grid">{''.join(sektioner)}</div>
<h2>Konsiliets bedömningar</h2>
{''.join(bed_html) or '<p class="tom">Inga bedömningar under perioden.</p>'}
<h2>Provsvar utanför referensintervall</h2>
{f'<table><tr><th>Datum</th><th>Analys</th><th>Värde</th><th>Referens</th><th></th></tr>{labb_rader}</table>' if labb_rader else '<p class="tom">Inga.</p>'}
<h2>Frågor att ta upp</h2>
{'<ol>' + ''.join(f'<li>{e(f)}</li>' for f in dict.fromkeys(frågor)) + '</ol>' if frågor else '<p class="tom">Inga särskilda frågor.</p>'}
<footer>Varje påstående i bedömningarna har källhänvisningar (S = mätserie, B = baslinje, N = sömnpass, J = journal,
L = provsvar) och har kontrollerats automatiskt mot källdatan. Genererat av Konsiliet.</footer>
</html>"""


def pdf() -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page()
        p.set_content(bygg_html(), wait_until="load")
        data = p.pdf(format="A4", print_background=True)
        b.close()
    return data
