#!/usr/bin/env python3
"""Lägger en etikett under en skärmbild, så att det syns i själva bilden vad den visar (syntetiskt, demo, riktigt).

    cd server && uv run python ../tools/etikett.py in.png ut.png "Syntetisk testdata." "Detalj om källan."

Bilden täcks inte över: en remsa läggs till under den. Ritas med Chromium (Playwright), så ingen ffmpeg-
drawtext eller Pillow behövs. --bredd skalar om hela resultatet (t.ex. 1920 för tävlingsbilderna).
"""
from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("in_fil")
    ap.add_argument("ut_fil")
    ap.add_argument("rubrik")
    ap.add_argument("detalj", nargs="?", default="")
    a = ap.parse_args()
    src = Path(a.in_fil)
    data = base64.b64encode(src.read_bytes()).decode()
    mime = mimetypes.guess_type(src.name)[0] or "image/png"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(device_scale_factor=1)
        pg.set_content(f"<img id=i src='data:{mime};base64,{data}'>")
        w, h = pg.eval_on_selector("#i", "i => [i.naturalWidth, i.naturalHeight]")
        fs = max(15, round(w / 72)) if w > 1100 else max(15, round(w / 36))
        doc = f"""<!doctype html><meta charset=utf-8><style>
          html,body{{margin:0;background:#1f1b12;width:{w}px}}
          img{{display:block;width:{w}px;height:{h}px}}
          .e{{border-top:2px solid #d9a03f;padding:{round(fs*.75)}px {fs}px;font:{fs}px/1.35 'IBM Plex Sans',
             'Helvetica Neue',Arial,sans-serif;color:#d6d3cc}}
          .e b{{color:#d9a03f;font-weight:700;margin-right:.45em}}
        </style><img src='data:{mime};base64,{data}'><div class=e><b>{html.escape(a.rubrik)}</b>{html.escape(a.detalj)}</div>"""
        pg.set_viewport_size({"width": w, "height": h + 400})
        pg.set_content(doc)
        hh = pg.evaluate("document.body.scrollHeight")
        pg.set_viewport_size({"width": w, "height": hh})
        pg.screenshot(path=a.ut_fil, full_page=True)
        b.close()


if __name__ == "__main__":
    sys.exit(main())
