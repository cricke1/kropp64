#!/usr/bin/env python3
"""Fotograferar render/media/html/<namn>.html till docs/bidrag-media/<ut>.png i 1600x1000 (skala 1.5 för skärpa)."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
HIT = Path(__file__).resolve().parent
UT = HIT.parents[1] / "docs" / "bidrag-media"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.2)
    for par in sys.argv[1:]:
        namn, ut = par.split(":")
        pg.goto((HIT / "html" / f"{namn}.html").as_uri()); pg.wait_for_timeout(400)
        pg.screenshot(path=str(UT / ut), type="png")
        print(UT / ut)
    b.close()
