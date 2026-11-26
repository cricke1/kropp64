#!/usr/bin/env python3
"""01: kortbilden. 3D-renderingen med de riktiga appskärmarna (render/hero.py med TEX_MOBIL/TEX_KLOCKA) och
en RivaTuner-OSD som titel, stor nog att läsas när kortet visas litet i listan."""
from PIL import Image
import retro as R
from text import REPO

im = Image.open(REPO / "render/media/ut/hero-riktig.png").convert("RGB").resize((1600, 1000), Image.LANCZOS)
im = R.osd(im, [("KROPP64", "HWiNFO för kroppen", R.OSD_GUL)], x=56, y=44, size=78)
im = R.osd(im, [("AI-LÄKARTEAM", "lokalt, 16 GB", R.GRON), ("MOLNET", "0 byte hälsodata", R.GRON)], x=56, y=150, size=46)
im = R.osd(im, [("PULS", "74 BPM", None)], x=470, y=895, size=40)
im.save(REPO / "docs/bidrag-media/01-kropp64.jpg", quality=93)
print("01-kropp64.jpg")
