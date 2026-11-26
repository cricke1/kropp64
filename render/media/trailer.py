#!/usr/bin/env python3
"""Trailern, version 2 (16:9, 55 s). Klippt bildruta för bildruta i Python mot hjärtslagen i musik.py.

Berättelsen i fem akter, i jättestor text så att den går att följa utan ljud:
  0-7 s    HOOK      Allt i datorn har en sensor. Utom jag. POST-skärmen varnar.
  7-17 s   BYGGET    Klockan, appen, 1177, tiden vid datorn. Allt på en Mac mini.
  17-31 s  TEAMET    Sex AI-läkare diskuterar min natt. Kardiologen går för långt.
  31-45 s  DROPPET   Moderatorn stryker påståendet. Sedan siffrorna, en per takt.
  45-55 s  SLUTET    Hjärtat saktar in. Rösta.

Allt rörligt (zoom, skak, blixtar, RGB-glitch) räknas fram per bildruta, och ljudeffekterna (whoosh,
nedslag, glitch, tangentklick) syntetiseras och läggs på exakt där klippen sitter.

  .venv/bin/python trailer.py [--fran S --till S --png mapp]   (utdrag för granskning)
Utdata: docs/video/kropp64-trailer-1920x1080.mp4 (ligger inte i git).
"""
import argparse, math, random, subprocess, wave
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.signal import butter, sosfilt
import retro as R
from text import REPO, font

W, H, FPS = 1920, 1080, 30
MEDIA = REPO / "render/media"
DEMO = REPO / "docs/video/kropp64-demo-1920x1080.mp4"
ANIM = REPO / "docs/render/kropp64-animation.mp4"
RIGG = REPO / "docs/video/riggen-demo-1920x1080.mp4"
SKARM = MEDIA / "skarm"
HERO = MEDIA / "ut/hero-riktig.png"
GRANS = REPO / "docs/render/kropp64-16gb-gransen.png"
MUSIK = MEDIA / "ut/musik.wav"
UT = REPO / "docs/video/kropp64-trailer-1920x1080.mp4"
LANGD = 55.0

POST = [("Kropp64 Modular BIOS v0.64, An Energy Star Ally", R.VIT), ("Copyright (C) 2026, Kropp64 Software, Inc.", R.GRA), ("", R.GRA),
        ("CPU     : Mänskligt hjärta, 1 kärna @ ?? BPM", R.GRA), ("Memory  : 16384 MB (Mac mini M4) ........ OK", R.GRA),
        ("Sensors : Pixel Watch 5 .................. Found", R.GRA), ("Journal : 1177 via BankID ................ Found", R.GRA),
        ("AI Team : qwen3.5:9b, 6 agenter .......... Local", R.GRA), ("", R.GRA),
        ("WARNING: Vilopuls ej övervakad på 18 år.", R.ROD), ("", R.GRA), ("Press DEL to enter SETUP", R.VIT)]


# ------------------------------------------------------------------ hjärtslagen (samma som musik.py)
def bpm(t):
    if t < 7: return 58
    if t < 17: return 58 + (t - 7) / 10 * 14
    if t < 31: return 72 + (t - 17) / 14 * 52
    if t < 45: return 124
    return max(52, 124 - (t - 45) / 10 * 72)


B, _t = [], 0.0
while _t < LANGD:
    B.append(_t); _t += 60 / bpm(_t)
DROP = 31.0

# ------------------------------------------------------------------ hjälpare
SVART, VIT, GUL, ROD, GRON, ORANGE = (0, 0, 0), (255, 255, 255), (255, 230, 60), (255, 70, 60), (90, 255, 120), (255, 150, 0)
LJUD: list[tuple[float, str, float]] = []  # (tid, typ, styrka) fylls när scenerna definieras


def ease(u):  # easeOutExpo
    u = min(1.0, max(0.0, u))
    return 1.0 if u >= 1 else 1 - 2 ** (-10 * u)


def easeio(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


@lru_cache(maxsize=None)
def bild(path: str) -> Image.Image:
    return Image.open(path).convert("RGB")


def kamera(src: Image.Image, cx, cy, w, nearest=False, bg=SVART) -> Image.Image:
    """Beskär en 16:9-ruta med mitt (cx, cy) och bredd w ur src och skala till 1920x1080."""
    h = w * 9 / 16
    box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    rs = Image.NEAREST if nearest else Image.BICUBIC
    if box[0] >= 0 and box[1] >= 0 and box[2] <= src.width and box[3] <= src.height:
        return src.resize((W, H), rs, box=box)
    ram = Image.new("RGB", (int(w), int(h)), bg)
    ram.paste(src, (int(-box[0]), int(-box[1])))
    return ram.resize((W, H), rs)


def kam_rorelse(src, r0, r1, u, nearest=False, e=easeio, bg=SVART):
    k = e(u)
    return kamera(src, lerp(r0[0], r1[0], k), lerp(r0[1], r1[1], k), lerp(r0[2], r1[2], k), nearest, bg)


class Video:
    """Läser bildrutor framåt ur en film (via ffmpeg) från en starttid, med valfri hastighet."""
    def __init__(self, path, start, fart=1.0):
        self.fart = fart; self.i = -1; self.ram = None
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(start), "-i", str(path), "-vf", f"fps={FPS},scale=1920:1080",
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

    def vid(self, lt):
        mal = int(lt * FPS * self.fart)
        while self.i < mal:
            b = self.p.stdout.read(W * H * 3)
            if len(b) < W * H * 3: break
            self.ram = Image.frombuffer("RGB", (W, H), b); self.i += 1
        return self.ram.copy() if self.ram else Image.new("RGB", (W, H))


@lru_cache(maxsize=None)
def textlager(s, typ="sans", vikt=600, size=120, fill=VIT, stroke=0, stroke_fill=SVART):
    f = font(typ, vikt, size)
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb = d.textbbox((0, 0), s, font=f, stroke_width=stroke)
    im = Image.new("RGBA", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - bb[0], 4 - bb[1]), s, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    return im


def lagg(im, lager, cx, cy, skala=1.0, alfa=1.0, ankare="mm"):
    if alfa <= 0.01: return im
    l = lager
    if abs(skala - 1) > 0.005:
        l = l.resize((max(1, int(l.width * skala)), max(1, int(l.height * skala))), Image.BILINEAR)
    if alfa < 0.99:
        a = l.getchannel("A").point(lambda v: int(v * alfa)); l = l.copy(); l.putalpha(a)
    x = cx - l.width // 2 if ankare[0] == "m" else cx if ankare[0] == "l" else cx - l.width
    y = cy - l.height // 2 if ankare[1] == "m" else cy if ankare[1] == "t" else cy - l.height
    im.paste(l, (int(x), int(y)), l)
    return im


def slam(lt, t_in, langd=0.14, fran=1.7):
    """Skala och alfa för text som slås in: stor och genomskinlig till rätt storlek på några bildrutor."""
    u = (lt - t_in) / langd
    if u < 0: return 0.0, 0.0
    return 1 + (fran - 1) * (1 - ease(u)) ** 1.5, min(1.0, u * 2.5)


def morka(im, k):
    return Image.blend(im, Image.new("RGB", im.size), k)


def jattetext(im, s, cy, size=230, fill=VIT, lt=0.0, t_in=0.0, stroke=10, typ="sans", vikt=600, cx=W // 2, fran=1.7):
    sk, a = slam(lt, t_in, fran=fran)
    lager = textlager(s, typ, vikt, size, fill, stroke)
    if lager.width > W - 120:  # får aldrig gå utanför bild
        sk *= (W - 120) / lager.width
    return lagg(im, lager, cx, cy, sk, a)


def osd_rad(im, etikett, varde, y, size=110, farg=VIT, lt=0.0, t_in=0.0, x=140, dim=False):
    """RivaTuner-OSD i jätteformat: etikett i orange, värde till höger."""
    sk, a = slam(lt, t_in, fran=1.35)
    if dim: a *= 0.35
    e = textlager(etikett, "mono", 500, size, ORANGE, 8); v = textlager(varde, "mono", 500, size, farg, 8)
    lagg(im, e, x, y, sk, a, "lm")
    lagg(im, v, x + int(size * 4.4), y, sk, a, "lm")
    return im


def chip(s, farg, size=44):
    """Källchip som i appen: liten färgad ruta + text."""
    t = textlager(s, "mono", 500, size, (230, 230, 230))
    im = Image.new("RGBA", (t.width + 70, t.height + 26), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), 12, fill=(30, 34, 38, 235), outline=farg + (255,), width=3)
    d.rectangle((18, im.height // 2 - 9, 36, im.height // 2 + 9), fill=farg)
    im.paste(t, (50, 13), t)
    return im


@lru_cache(maxsize=None)
def chattkort(namn, farg, text, kalla, kalla_farg, bredd=1720):
    """Ett inlägg i tråden i jätteformat: avatar, namn i agentfärg, texten, källchip."""
    f_namn, f_text = font("sans", 600, 66), font("sans", 500, 88)
    d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    rader, rad = [], ""
    for ord_ in text.split():
        prov = (rad + " " + ord_).strip()
        if d0.textbbox((0, 0), prov, font=f_text)[2] > bredd - 260: rader.append(rad); rad = ord_
        else: rad = prov
    rader.append(rad)
    hojd = 70 + 80 + len(rader) * 106 + (110 if kalla else 30)
    im = Image.new("RGBA", (bredd, hojd), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, bredd - 1, hojd - 1), 34, fill=(24, 27, 31, 246), outline=(60, 66, 72, 255), width=3)
    d.rectangle((0, 30, 12, hojd - 30), fill=farg)
    d.ellipse((50, 44, 150, 144), fill=farg)
    bok = textlager(namn[0], "sans", 600, 60, (20, 20, 20)); im.paste(bok, (100 - bok.width // 2, 94 - bok.height // 2), bok)
    d.text((190, 48), namn, font=f_namn, fill=farg)
    y = 132
    for r in rader:
        d.text((190, y), r, font=f_text, fill=(240, 240, 240)); y += 106
    if kalla:
        c = chip(kalla, kalla_farg); im.paste(c, (190, y + 18), c)
    return im


def pil(im, x0, x1, y, farg, tjock=26):
    d = ImageDraw.Draw(im)
    d.rectangle((x0, y - tjock // 2, x1 - 50, y + tjock // 2), fill=farg)
    d.polygon([(x1 - 90, y - 75), (x1, y), (x1 - 90, y + 75)], fill=farg)


# ------------------------------------------------------------------ scenerna
# Varje scen: (start, slut, funktion(t_global, t_lokal) -> RGB-bild). Effekter räknas efteråt.
SCENER = []
EFFEKT = {"punch": [], "skak": [], "blixt": [], "glitch": [], "rgb": []}


def scen(start, slut):
    def dek(fn):
        SCENER.append((start, slut, fn)); return fn
    return dek


def punch(t, amp=0.06): EFFEKT["punch"].append((t, amp))
def skak(t, amp=30, d=0.25): EFFEKT["skak"].append((t, amp, d))
def blixt(t, styrka=0.9, d=0.12, farg=VIT): EFFEKT["blixt"].append((t, styrka, d, farg))
def glitch(t, d=0.12): EFFEKT["glitch"].append((t, d))
def rgb(t0, t1, px): EFFEKT["rgb"].append((t0, t1, px))
def ljud(t, typ, s=1.0): LJUD.append((t, typ, s))


# ---- AKT 1: HOOK, 0-7 s ----------------------------------------------------------
for i in (0, 1, 2): punch(B[i], 0.035); ljud(B[i], "slam", 0.8)
glitch(B[2], 0.2); skak(B[2], 18); ljud(B[2], "glitch", 0.9)


@scen(0.0, B[3])
def hook(t, lt):
    im = Image.new("RGB", (W, H))
    osd_rad(im, "GPU", "62°C", 230, size=170, farg=GRON, lt=lt, t_in=B[0] - 0.2, dim=lt > B[2], x=200)
    if lt >= B[1]: osd_rad(im, "FLÄKT", "1450 RPM", 450, size=170, farg=VIT, lt=lt, t_in=B[1], dim=lt > B[2], x=200)
    if lt >= B[2]:
        osd_rad(im, "PULS", "???" if int(lt * 8) % 2 == 0 else "", 690, size=200, farg=ROD, lt=lt, t_in=B[2], x=200)
    under = "Allt i datorn har en sensor." if lt < B[2] else "Utom jag."
    jattetext(im, under, 940, size=96, fill=(235, 235, 235), lt=lt, t_in=-0.2 if lt < B[2] else B[2], stroke=0, fran=1.15)
    return im


# POST-skärmen: kameran följer markören, sedan hårt in på varningen
_TECKEN = sum(len(r) + 1 for r, _ in POST)
_VARN_RAD = 9
for i in (4, 5, 6): punch(B[i], 0.05)
blixt(B[5], 0.55, 0.18, (255, 0, 0)); skak(B[5], 40, 0.4); skak(B[6], 28, 0.3); ljud(B[5], "nedslag", 1.0); ljud(B[6], "nedslag", 0.6)
for k in range(28): ljud(B[3] + k * 0.075, "klick", 0.35)


@scen(B[3], B[6])
def post_skarm(t, lt):
    skriv = min(1.0, lt / (B[5] - B[3] - 0.05))
    n = int(_TECKEN * skriv)
    src = R.post(POST, n_tecken=n, size=46, cursor=True)
    # vilken rad skrivs nu?
    kvar, rad = n, 0
    for i, (s, _) in enumerate(POST):
        if kvar <= len(s): rad = i; break
        kvar -= len(s) + 1
    lh = int(46 * 1.32)
    if t < B[5]:
        y = 50 + rad * lh + 23; x = 60 + min(len(POST[rad][0]), kvar) * 27.6
        return kamera(src, max(560, min(x, 1400)), max(330, y), 1100)
    u = (t - B[5]) / 0.18
    return kam_rorelse(src, (700, 50 + _VARN_RAD * lh + 23, 1300), (640, 50 + _VARN_RAD * lh + 23, 1220), u, e=ease)


@scen(B[6], B[7])
def sa_jag(t, lt):
    im = Image.new("RGB", (W, H), (150, 0, 0)) if t - B[6] < 0.06 else Image.new("RGB", (W, H))
    jattetext(im, "SÅ JAG BYGGDE", 540, size=200, lt=t, t_in=B[6])
    return im


# ---- AKT 2: BYGGET, 7-17 s -------------------------------------------------------
blixt(B[7], 1.0, 0.25); punch(B[7], 0.09); ljud(B[7], "nedslag", 1.0); ljud(B[7] - 0.3, "whoosh", 0.8)
_anim = {}


@scen(B[7], B[9])
def titel(t, lt):
    if "v" not in _anim: _anim["v"] = Video(ANIM, 3.4, 0.9)
    src = _anim["v"].vid(t - B[7])
    im = morka(kam_rorelse(src, (1100, 560, 1920), (1150, 560, 1500), (t - B[7]) / (B[9] - B[7])), 0.35)
    jattetext(im, "KROPP64", 470, size=300, fill=VIT, lt=t, t_in=B[7], stroke=12, fran=2.2)
    sk, a = slam(t, B[8])
    lagg(im, textlager("HWiNFO för kroppen", "mono", 500, 86, GUL, 7), W // 2, 690, sk, a)
    sk, a = slam(t, B[8] + 0.45, fran=1.3)
    lagg(im, textlager("klockan + 1177  ->  AI-läkare på min Mac mini", "sans", 600, 66, VIT, 6), W // 2, 830, sk, a)
    return im


def mobil_scen(fil, r0, r1, etikett, rubrik, t0, t1, sub=None):
    """Telefonens riktiga skärm, beskuren så att den fyller hela bilden, med etikett och jätterubrik."""
    def fn(t, lt):
        src = bild(str(SKARM / fil))
        u = (t - t0) / (t1 - t0)
        im = kam_rorelse(src, r0, r1, u, e=lambda x: 1 - (1 - x) ** 3, bg=(16, 16, 18))
        # mörk gradient i överkanten så att rubriken alltid syns
        grad = Image.linear_gradient("L").resize((W, 140)).transpose(Image.FLIP_TOP_BOTTOM)
        im.paste(Image.new("RGB", (W, 300)), (0, 0)); im.paste(Image.new("RGB", (W, 140)), (0, 300), grad)
        g2 = Image.linear_gradient("L").resize((W, 260)).point(lambda v: int(v * 0.9))
        im.paste(Image.new("RGB", (W, 260)), (0, H - 260), g2)
        lagg(im, textlager(etikett, "mono", 500, 54, ORANGE, 6), 90, 70, *slam(t, t0, fran=1.3), ankare="lt")
        jattetext(im, rubrik, 190, size=150, lt=t, t_in=t0 + 0.04, stroke=9, cx=W // 2)
        if sub:
            sk, a = slam(t, t0 + (t1 - t0) * 0.45, fran=1.25)
            lagg(im, textlager(sub, "sans", 600, 64, (20, 20, 20)), W // 2, H - 110, sk, a)
        return im
    return fn


def gul_platta(im, t, t_in, text, cy=H - 100):
    sk, a = slam(t, t_in, fran=1.25)
    if a <= 0: return im
    l = textlager(text, "sans", 600, 86, (15, 15, 15))
    p = Image.new("RGBA", (l.width + 80, l.height + 40), GUL + (255,)); p.paste(l, (40, 20), l)
    return lagg(im, p, W // 2, cy, sk, a)


_STEG = [  # (fil, start-rekt, slut-rekt, etikett, rubrik, platta)
    ("mobil-sensorer.png", (540, 760, 1300), (300, 520, 760), "PIXEL WATCH 5  ->  APPEN", "PULSEN, LIVE", "puls, HRV, sömn, steg, syre"),
    ("mobil-idag.png", (540, 640, 1250), (540, 600, 1050), "VARJE MORGON", "TRÄNA ELLER VILA?", "svar direkt, reglerna står i koden"),
    ("mobil-idag.png", (540, 1900, 1250), (420, 1880, 900), "1177", "HELA JOURNALEN", "ett BankID-tryck, sparas bara hemma"),
    ("mobil-sensorer2.png", (540, 1560, 1250), (560, 1560, 1050), "MAC MINI + TELEFONEN", "TIDEN VID SKÄRMEN", "kod, spel, sociala medier, per minut"),
]
_GRANS = [B[9], B[11], B[13], B[15], B[17]]
for k in range(4):
    a, b = _GRANS[k], _GRANS[k + 1]
    f, r0, r1, et, rub, pl = _STEG[k]
    punch(a, 0.08); blixt(a, 0.5, 0.08); ljud(a - 0.25, "whoosh", 0.7); ljud(a, "slam", 0.9)
    _fn = mobil_scen(f, r0, r1, et, rub, a, b)

    def _m(t, lt, _fn=_fn, a=a, b=b, pl=pl):
        im = _fn(t, lt)
        return gul_platta(im, t, a + (b - a) * 0.2, pl)
    SCENER.append((a, b, _m))
    punch(a + (b - a) / 2, 0.035)

# Mac minin: allt körs här
blixt(B[17], 0.9, 0.15); punch(B[17], 0.1); ljud(B[17] - 0.3, "whoosh", 0.9); ljud(B[17], "nedslag", 1.0)


@scen(B[17], B[19])
def macmini(t, lt):
    if "m" not in _anim: _anim["m"] = Video(ANIM, 5.6, 0.7)
    src = _anim["m"].vid(t - B[17])
    u = (t - B[17]) / (B[19] - B[17])
    im = morka(kam_rorelse(src, (1450, 560, 1300), (1500, 520, 900), u, e=ease), 0.3)
    jattetext(im, "ALLT KÖRS HÄR.", 400, size=170, lt=t, t_in=B[17])
    sk, a = slam(t, B[18], fran=1.4)
    lagg(im, textlager("Mac mini, 16 GB.  0 byte till molnet.", "mono", 500, 70, GRON, 7), W // 2, 600, sk, a)
    return im


# ---- AKT 3: TEAMET, 17-31 s ------------------------------------------------------
_demo = {}
# kontoret ligger på (332, 172) i demofilmen, 832x574 pixlar (2x pixelkonsten)
KONTOR_BORD = (750, 330)


def kontor(t, start_demo, r0, r1, u, fart=1.0, nyckel="k"):
    if nyckel not in _demo: _demo[nyckel] = (Video(DEMO, start_demo, fart), t)
    v, t0 = _demo[nyckel]
    return kam_rorelse(v.vid(t - t0), r0, r1, u, nearest=True)


blixt(B[19], 1.0, 0.2); punch(B[19], 0.1); skak(B[19], 30); ljud(B[19], "nedslag", 1.0); ljud(B[19] - 0.35, "whoosh", 0.9)
punch(B[20], 0.06); ljud(B[20], "slam", 0.8)


@scen(B[19], B[21])
def sex_lakare(t, lt):
    u = (t - B[19]) / (B[21] - B[19])
    im = morka(kontor(t, 9.0, (750, 460, 840), (760, 350, 520), u, nyckel="intro"), 0.45)
    jattetext(im, "6 AI-LÄKARE", 430, size=250, lt=t, t_in=B[19], stroke=12, fran=2.0)
    sk, a = slam(t, B[20], fran=1.3)
    lagg(im, textlager("läser min data. Varje natt.", "sans", 600, 84, GUL, 7), W // 2, 640, sk, a)
    return im


AGENTER = [  # (beat, namn, färg, text, källa, källfärg)
    (21, "Trådstartaren", (110, 160, 255), "Vilopulsen låg klart över baslinjen i natt.", "Puls 02:14-02:31", (110, 160, 255)),
    (23, "Kardiologen", (255, 95, 95), "68 till 74 slag i minuten. Normalt 57.", "Puls baslinje 28 d", (255, 95, 95)),
    (25, "Trollet", (190, 190, 190), "Har du testat att dra åt armbandet?", "", (0, 0, 0)),
    (27, "Sömnläkaren", (170, 140, 255), "5 h 40 min sömn. Snittet är 7 h 10.", "Sömn i natt", (170, 140, 255)),
    (29, "Idrottsläkaren", (90, 220, 130), "Hårt pass 20:05 i går kväll.", "Puls 20:05-21:10", (90, 220, 130)),
    (31, "Stressläkaren", (255, 180, 70), "HRV lågt tre nätter i rad.", "HRV 23-25 nov", (255, 180, 70)),
]
for k, (b, *_r) in enumerate(AGENTER):
    punch(B[b], 0.06); ljud(B[b], "pop", 0.9); ljud(B[b] - 0.18, "whoosh", 0.45)


@scen(B[21], B[33])
def traden(t, lt):
    u = (t - B[21]) / (B[33] - B[21])
    bg = morka(kontor(t, 30.0, (560, 330, 700), (1000, 330, 700), u, nyckel="trad").filter(ImageFilter.GaussianBlur(9)), 0.7)
    im = bg
    synliga = [a for a in AGENTER if t >= B[a[0]]]
    # senaste kortet stort i mitten, äldre glider uppåt och tonar ut
    for idx, (b, namn, farg, text, kalla, kf) in enumerate(reversed(synliga)):
        kort = chattkort(namn, farg, text, kalla, kf)
        u_in = ease((t - B[b]) / 0.22)
        if idx == 0:
            y = lerp(H + 200, 640, u_in); sk = lerp(1.12, 1.0, u_in); a = 1.0
        else:
            y = 640 - kort.height // 2 - 150 - (idx - 1) * 120; sk = 0.75 - 0.06 * idx; a = max(0.0, 0.55 - 0.3 * idx)
            if idx == 1:
                f = ease((t - B[synliga[-1][0]]) / 0.22)
                y = lerp(640, y, f); sk = lerp(1.0, sk, f); a = lerp(1.0, a, f)
        im = lagg(im, kort, W // 2, int(y), sk, a)
    d = ImageDraw.Draw(im); d.rectangle((0, H - 120, W, H), fill=(0, 0, 0))
    lagg(im, textlager("TRÅDEN:", "mono", 500, 60, ORANGE), 90, H - 60, ankare="lm")
    lagg(im, textlager("varje påstående måste ha en källa", "mono", 500, 60, VIT), 420, H - 60, ankare="lm")
    return im


# Kardiologen går för långt: uppbyggnaden till droppet
_KARD = "Sammantaget tyder det på en begynnande"
_ORD = "HJÄRTMUSKEL-INFLAMMATION."
punch(B[33], 0.1); blixt(B[33], 0.4, 0.1); ljud(B[33], "nedslag", 0.8)
rgb(B[35], DROP, 0)


@scen(B[33], DROP)
def kardiologen(t, lt):
    lt = t - B[33]; u = lt / (DROP - B[33])
    src = kontor(t, 133.0, (800, 330, 520), (800, 320, 300), u, nyckel="kard")
    im = morka(src, 0.72)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 150), fill=(150, 20, 20))
    lagg(im, textlager("KARDIOLOGEN", "mono", 500, 70, VIT, 0), 90, 75, ankare="lm")
    lagg(im, textlager(_KARD, "sans", 500, 76, (235, 235, 235)), W // 2, 330)
    # ordet skrivs ut bokstav för bokstav medan risern stiger
    n = int(len(_ORD) * min(1.0, max(0.0, (lt - 0.35) / 1.9)))
    if n:
        delar = _ORD[:n].split("-")
        for i, s in enumerate(delar):
            if s: jattetext(im, s + ("-" if i == 0 and len(delar) > 1 else ""), 520 + i * 200, size=190, fill=ROD, stroke=10, lt=1, t_in=0)
    if lt > 2.4:
        blink = int(lt * 10) % 2 == 0
        c = chip("KÄLLA: ???", ROD if blink else (120, 30, 30), size=62)
        lagg(im, c, W // 2, 940)
    return im


for k in range(36, 41): skak(B[k], 6 + (k - 36) * 7, 0.2); punch(B[k], 0.02 + (k - 36) * 0.012)

# ---- DROPPET, 31 s -------------------------------------------------------------
blixt(DROP, 1.0, 0.3); skak(DROP, 70, 0.5); glitch(DROP, 0.25); punch(DROP, 0.18); rgb(DROP, DROP + 0.4, 18)
ljud(DROP, "strykning", 1.0); ljud(DROP, "glitch", 1.0)


@scen(DROP, B[43])
def strykningen(t, lt):
    lt = t - DROP
    im = Image.new("RGB", (W, H), (12, 0, 0))
    lagg(im, textlager(_KARD, "sans", 500, 76, (140, 140, 140)), W // 2, 330)
    for i, s in enumerate(["HJÄRTMUSKEL-", "INFLAMMATION."]):
        jattetext(im, s, 520 + i * 200, size=190, fill=(200, 60, 50), stroke=10, lt=1, t_in=0)
    d = ImageDraw.Draw(im)
    for i, y in enumerate((520, 720)):
        f = ease((lt - i * 0.07) / 0.16)
        if f > 0:
            x0, x1 = 120, lerp(120, W - 120, f)
            d.polygon([(x0, y - 22), (x1, y - 32), (x1, y + 6), (x0, y + 16)], fill=VIT)
    if lt > 0.3:
        sk, a = slam(t, DROP + 0.3, fran=2.0)
        p = Image.new("RGBA", (1500, 190), (255, 40, 40, 255))
        l = textlager("STRUKET AV MODERATORN", "mono", 500, 92, VIT)
        p.paste(l, ((p.width - l.width) // 2, (p.height - l.height) // 2), l)
        lagg(im, p.rotate(-4, expand=True, resample=Image.BICUBIC), W // 2, 930, sk, a)
    return im


punch(B[43], 0.12); blixt(B[43], 0.6, 0.1); ljud(B[43], "nedslag", 1.0)


@scen(B[43], B[46])
def moderatorn(t, lt):
    lt = t - B[43]
    sk = 1 + 0.25 * (1 - ease(lt / 0.2))
    src = R.bios_dialog("PÅSTÅENDE STRUKET: INGEN KÄLLA", "", size=84)
    im = kamera(src, W / 2, 560, W / sk)
    if lt > 0.48:
        jattetext(im, "Moderatorn är vanlig Python.", 760, size=96, fill=VIT, stroke=7, lt=t, t_in=B[44], fran=1.3)
    if lt > 0.96:
        jattetext(im, "Ingen AI kan prata sig förbi den.", 890, size=96, fill=GUL, stroke=7, lt=t, t_in=B[45], fran=1.3)
    return im


punch(B[44], 0.05); punch(B[45], 0.05); ljud(B[44], "slam", 0.7); ljud(B[45], "slam", 0.7)

# ---- BEVISET, siffrorna en per takt ----------------------------------------------
SIFFROR = [  # (beat, stort, under, färg, bakgrund)
    (46, "36/36", "rätt brådska i fall den aldrig sett", GRON, "rigg"),
    (49, "4->0", "missade akuta fall", VIT, "kontor"),
    (52, "118 s", "per fall, lokalt på Mac minin", VIT, "anim"),
    (55, "56 s", "samma fall på ett RTX 5050", (100, 230, 255), "rigg2"),
]
_bg_vid = {}


def bakgrund(namn, t, t0):
    lt = t - t0
    if namn in ("rigg", "rigg2"):
        if namn not in _bg_vid: _bg_vid[namn] = Video(RIGG, 9.0 if namn == "rigg" else 3.0)
        return kam_rorelse(_bg_vid[namn].vid(lt), (960, 560, 1200), (960, 540, 1000), lt / 1.0)
    if namn == "kontor":
        if namn not in _bg_vid: _bg_vid[namn] = Video(DEMO, 60.0)
        return kam_rorelse(_bg_vid[namn].vid(lt), (750, 450, 700), (750, 450, 560), lt / 1.0, nearest=True)
    if namn == "anim":
        if namn not in _bg_vid: _bg_vid[namn] = Video(ANIM, 6.0)
        return kam_rorelse(_bg_vid[namn].vid(lt), (960, 540, 1700), (1000, 540, 1400), lt / 1.0)
    if namn == "grans":
        return kam_rorelse(bild(str(GRANS)), (650, 520, 1300), (650, 560, 1000), lt / 1.0)
    return kam_rorelse(bild(str(HERO)), (1200, 560, 1600), (1350, 540, 1100), lt / 1.0)


for k, (b, *_r) in enumerate(SIFFROR):
    punch(B[b], 0.12); glitch(B[b], 0.08); blixt(B[b], 0.35, 0.07); ljud(B[b], "nedslag", 0.85); ljud(B[b] - 0.12, "whoosh", 0.5)
    punch(B[b + 1], 0.05); ljud(B[b + 1], "tick", 0.6); punch(B[b + 2], 0.04)


@scen(B[46], B[58])
def siffror(t, lt):
    akt = [s for s in SIFFROR if t >= B[s[0]]][-1]
    b, stort, under, farg, bg = akt
    im = morka(bakgrund(bg, t, B[b]), 0.62)
    if "->" in stort:
        v, h = stort.split("->"); sk, a = slam(t, B[b], fran=2.2)
        lag = Image.new("RGBA", (1300, 420), (0, 0, 0, 0))
        lv, lh = textlager(v, "mono", 500, 330, ROD, 14), textlager(h, "mono", 500, 330, GRON, 14)
        lag.paste(lv, (40, 0), lv); lag.paste(lh, (1300 - lh.width - 40, 0), lh)
        pil(lag, 330, 960, 200, VIT, 40)
        lagg(im, lag, W // 2, 470, sk, a)
    else:
        jattetext(im, stort, 470, size=330, fill=farg, stroke=14, lt=t, t_in=B[b], fran=2.2, typ="mono", vikt=500)
    sk, a = slam(t, B[b] + 0.15, fran=1.3)
    lagg(im, textlager(under, "sans", 600, 96, VIT, 8), W // 2, 760, sk, a)
    nr = SIFFROR.index(akt)
    lagg(im, textlager(f"BENCHMARK {nr + 1}/4", "mono", 500, 60, ORANGE, 6), 90, 70, ankare="lt")
    return im


# snabba klipp: allt material, ett slag var
SNABB = [  # (beat, källa, start, rekt, etikett)
    (58, "demo", 140.0, (760, 300, 640), "MODERATORN"),
    (59, "demo", 141.0, (1560, 900, 600), "STRUKET I TRÅDEN"),
    (60, "rigg", 6.0, (980, 560, 900), "RIGGEN"),
    (61, "skarm", "mobil-idag.png", (540, 1380, 1080), "HEADROOM, PASS, SÖMN"),
    (62, "demo", 100.0, (750, 450, 840), "KONTORET"),
    (63, "anim", 6.5, (700, 820, 700), "KLOCKAN"),
]
for b, *_r in SNABB:
    punch(B[b], 0.1); blixt(B[b], 0.3, 0.05); glitch(B[b], 0.06); ljud(B[b], "slam", 0.7)


@scen(B[58], B[64])
def snabbklipp(t, lt):
    akt = [s for s in SNABB if t >= B[s[0]]][-1]
    b, typ, start, r, et = akt
    lt = t - B[b]
    if typ == "skarm":
        im = kam_rorelse(bild(str(SKARM / start)), r, (r[0], r[1] - 60, r[2] * 0.85), lt / 0.5, bg=(16, 16, 18))
    else:
        nyckel = f"s{b}"
        if nyckel not in _bg_vid: _bg_vid[nyckel] = Video({"demo": DEMO, "rigg": RIGG, "anim": ANIM}[typ], start)
        im = kam_rorelse(_bg_vid[nyckel].vid(lt), r, (r[0], r[1], r[2] * 0.8), lt / 0.5, nearest=typ == "demo" and r[0] < 1300)
    ImageDraw.Draw(im).rectangle((0, 0, W, 150), fill=(0, 0, 0))
    im = R.osd(im, [(et, "", None)], x=70, y=40, size=80)
    return im


# riggen: kroppen som PC-chassi
punch(B[64], 0.12); blixt(B[64], 0.7, 0.12); ljud(B[64], "nedslag", 1.0)


@scen(B[64], B[69])
def riggen(t, lt):
    if "rigg_slut" not in _bg_vid: _bg_vid["rigg_slut"] = Video(RIGG, 8.0)
    u = (t - B[64]) / (B[69] - B[64])
    im = morka(kam_rorelse(_bg_vid["rigg_slut"].vid(t - B[64]), (960, 600, 1300), (990, 560, 760), u), 0.3)
    jattetext(im, "KROPPEN SOM PC-CHASSI", 200, size=128, lt=t, t_in=B[64], stroke=9)
    sk, a = slam(t, B[66], fran=1.3)
    lagg(im, textlager("Fläktarna går upp när pulsen stiger i vila.", "sans", 600, 64, GUL, 6), W // 2, H - 120, sk, a)
    return im


punch(B[66], 0.06); ljud(B[66], "slam", 0.7)

# ---- AKT 5: SLUTET, hjärtat saktar in --------------------------------------------
blixt(B[69], 1.0, 0.6); ljud(B[69], "nedslag", 1.0)
for k in range(70, 79): punch(B[k], 0.025)


@scen(B[69], B[78])
def slut(t, lt):
    u = (t - B[69]) / (B[78] - B[69])
    im = morka(kam_rorelse(bild(str(HERO)), (1000, 600, 1920), (1000, 620, 1500), u, e=lambda x: x), 0.4)
    jattetext(im, "KROPP64", 400, size=300, lt=t, t_in=B[70], stroke=12, fran=1.5)
    sk, a = slam(t, B[72], fran=1.2)
    lagg(im, textlager("HWiNFO för kroppen", "mono", 500, 86, GUL, 7), W // 2, 600, sk, a)
    sk, a = slam(t, B[74], fran=1.2)
    lagg(im, textlager("Pixel Watch  ·  1177  ·  ett AI-läkarteam som körs hemma", "sans", 500, 58, VIT, 5), W // 2, 730, sk, a)
    return im


blixt(B[78], 0.8, 0.15); ljud(B[78], "nedslag", 0.8); punch(B[80], 0.08); ljud(B[80], "slam", 0.9)
for k in range(81, 85): punch(B[k], 0.03)


@scen(B[78], LANGD + 0.1)
def rosta(t, lt):
    lt = t - B[78]
    svar = "Y" if t >= B[80] else ("_" if int(lt * 4) % 2 == 0 else " ")
    src = R.bios_dialog("RÖSTA PÅ KROPP64 (Y/N)?", svar, size=104)
    sk = 1 + 0.2 * (1 - ease(lt / 0.3))
    im = kamera(src, W / 2, 540, W / sk)
    jattetext(im, "1-13 december", 790, size=84, fill=VIT, stroke=0, lt=t, t_in=B[79], typ="mono", vikt=500, fran=1.3)
    jattetext(im, "projekt.sweclockers.com/asus", 900, size=72, fill=GUL, stroke=0, lt=t, t_in=B[81], typ="mono", vikt=500, fran=1.3)
    return im


# ------------------------------------------------------------------ efterbehandling
def efter(im: Image.Image, t: float) -> Image.Image:
    rnd = random.Random(int(t * FPS))
    z = 1.0
    for t0, amp in EFFEKT["punch"]:
        if 0 <= t - t0 < 0.5: z += amp * math.exp(-(t - t0) / 0.09)
    dx = dy = 0.0
    for t0, amp, d in EFFEKT["skak"]:
        if 0 <= t - t0 < d:
            k = amp * (1 - (t - t0) / d) ** 2; dx += rnd.uniform(-k, k); dy += rnd.uniform(-k, k)
    if z > 1.001 or dx or dy:
        z = max(z, 1 + (abs(dx) + abs(dy)) * 2.2 / W)
        w = W / z
        im = kamera(im, W / 2 + dx, H / 2 + dy, w)
    a = np.asarray(im).copy()
    px = 0
    for t0, t1, p in EFFEKT["rgb"]:
        if t0 <= t < t1:
            px = max(px, p if p else int(2 + 14 * (t - t0) / (t1 - t0)))
    for t0, d in EFFEKT["glitch"]:
        if 0 <= t - t0 < d:
            px = max(px, 14)
            for _ in range(7):
                y0 = rnd.randrange(0, H - 40); hh = rnd.randrange(10, 90); s = rnd.randrange(-160, 160)
                a[y0:y0 + hh] = np.roll(a[y0:y0 + hh], s, axis=1)
    if px:
        a[:, :, 0] = np.roll(a[:, :, 0], px, axis=1); a[:, :, 2] = np.roll(a[:, :, 2], -px, axis=1)
    f = a.astype(np.float32)
    for t0, s, d, farg in EFFEKT["blixt"]:
        if 0 <= t - t0 < d:
            k = s * (1 - (t - t0) / d) ** 2
            f = f * (1 - k) + np.array(farg, np.float32) * k
    f *= SCANLINJER
    return Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))


_sl = np.ones((H, 1, 1), np.float32); _sl[::3] = 0.9
_yy, _xx = np.mgrid[0:H, 0:W]
_vig = 1 - 0.35 * (((_xx - W / 2) / (W / 2)) ** 2 + ((_yy - H / 2) / (H / 2)) ** 2) ** 1.4
SCANLINJER = (_sl * np.clip(_vig, 0.55, 1)[:, :, None]).astype(np.float32)


# ------------------------------------------------------------------ ljudeffekter
SR = 48000


def _lp(x, f): return sosfilt(butter(2, f, "low", fs=SR, output="sos"), x)
def _hp(x, f): return sosfilt(butter(2, f, "high", fs=SR, output="sos"), x)


def sfx(typ, s, rng):
    if typ == "whoosh":
        n = int(0.35 * SR); tt = np.arange(n) / SR; x = rng.standard_normal(n)
        sw = np.zeros(n); seg = 2400
        for i in range(0, n, seg):
            f = 400 + 6000 * (i / n) ** 2; sw[i:i + seg] = sosfilt(butter(2, [f, f * 1.6], "band", fs=SR, output="sos"), x[i:i + seg])
        return sw * (tt / 0.35) ** 2.5 * 0.9 * s
    if typ == "nedslag":
        n = int(1.2 * SR); tt = np.arange(n) / SR
        boom = np.sin(2 * np.pi * np.cumsum(38 + 80 * np.exp(-tt * 14)) / SR) * np.exp(-tt * 3.2)
        knack = _hp(rng.standard_normal(n), 1500) * np.exp(-tt * 40) * 0.5
        return np.tanh((boom + knack) * 1.6) * 0.95 * s
    if typ == "slam":
        n = int(0.35 * SR); tt = np.arange(n) / SR
        return (np.sin(2 * np.pi * np.cumsum(70 + 120 * np.exp(-tt * 30)) / SR) * np.exp(-tt * 12) * 0.7
                + _hp(rng.standard_normal(n), 2500) * np.exp(-tt * 55) * 0.4) * s
    if typ == "glitch":
        n = int(0.3 * SR); x = rng.standard_normal(n)
        x = np.repeat(x[::40], 40)[:n]  # bitkrossat
        x = np.sign(x) * (np.abs(x) > 0.6) * 0.5
        grind = np.repeat(rng.random(n // 1200 + 1) > 0.4, 1200)[:n]
        return _hp(x * grind, 600) * 0.55 * s
    if typ == "klick":
        n = int(0.03 * SR); tt = np.arange(n) / SR
        return _hp(rng.standard_normal(n), 3000) * np.exp(-tt * 400) * 0.5 * s
    if typ == "pop":
        n = int(0.18 * SR); tt = np.arange(n) / SR
        return np.sin(2 * np.pi * np.cumsum(900 - 500 * tt / 0.18) / SR) * np.exp(-tt * 30) * 0.45 * s
    if typ == "tick":
        n = int(0.08 * SR); tt = np.arange(n) / SR
        return np.sin(2 * np.pi * 2400 * tt) * np.exp(-tt * 90) * 0.3 * s
    if typ == "strykning":
        n = int(0.6 * SR); tt = np.arange(n) / SR; x = rng.standard_normal(n)
        swish = sosfilt(butter(2, [3000, 9000], "band", fs=SR, output="sos"), x) * np.exp(-tt * 9)
        return swish * 1.2 * s
    raise ValueError(typ)


def ljudspar(langd):
    rng = np.random.default_rng(7)
    n = int(langd * SR); L = np.zeros(n); Rr = np.zeros(n)
    for t, typ, s in LJUD:
        if t < 0: continue
        x = sfx(typ, s, rng); i = int(t * SR); m = min(len(x), n - i)
        if m <= 0: continue
        pan = {"whoosh": 0.3, "klick": 0.2, "pop": 0.15}.get(typ, 0.0) * rng.choice([-1, 1])
        L[i:i + m] += x[:m] * (1 - pan); Rr[i:i + m] += x[:m] * (1 + pan)
    return np.stack([L, Rr])


# ------------------------------------------------------------------ rendering
def scen_vid(t):
    for a, b, fn in SCENER:
        if a <= t < b: return fn
    return SCENER[-1][2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fran", type=float, default=0.0); ap.add_argument("--till", type=float, default=LANGD)
    ap.add_argument("--png", help="spara bildrutor som PNG i den här mappen i stället för film")
    ap.add_argument("--steg", type=int, default=1)
    arg = ap.parse_args()
    SCENER.sort(key=lambda s: s[0])
    f0, f1 = int(arg.fran * FPS), int(arg.till * FPS)
    tmp = REPO / "render/media/ut/trailer-bild.mp4"
    if arg.png:
        Path(arg.png).mkdir(parents=True, exist_ok=True); enc = None
    else:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                                "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    for f in range(f0, f1):
        t = f / FPS
        fn = scen_vid(t)
        if arg.png and (f - f0) % arg.steg:
            fn(t, t); continue  # videoläsarna måste ändå stega fram
        im = efter(fn(t, t).convert("RGB"), t)
        if arg.png: im.save(Path(arg.png) / f"{f:05d}.png")
        else: enc.stdin.write(im.tobytes())
        if f % 150 == 0: print(f"{t:5.1f} s", flush=True)
    if arg.png: return
    enc.stdin.close(); enc.wait()
    langd = (f1 - f0) / FPS
    s = ljudspar(LANGD)[:, f0 * SR // FPS: f1 * SR // FPS]
    with wave.open(str(REPO / "render/media/ut/sfx.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(s.T / max(1.0, np.abs(s).max()) * 0.95, -1, 1) * 32767).astype("<i2").tobytes())
    sfx_gain = max(1.0, float(np.abs(s).max()))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-ss", str(arg.fran), "-t", str(langd), "-i", str(MUSIK),
                    "-i", str(REPO / "render/media/ut/sfx.wav"), "-filter_complex",
                    f"[1:a]volume=0.85[m];[2:a]volume={0.75 * sfx_gain / max(1.0, sfx_gain):.3f}[s];[m][s]amix=inputs=2:normalize=0,"
                    f"afade=out:st={langd - 1.0}:d=1.0,loudnorm=I=-13:TP=-1.0[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(UT)], check=True)
    print(UT, round(langd, 1), "s")


if __name__ == "__main__":
    main()
