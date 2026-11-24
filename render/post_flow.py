"""Etiketter och linjer ovanpa dataflodesrenderingen.
python3 post_flow.py <render.png> <ankare.json> <ut.png>
"""
import sys, os, json, math
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(HERE, 'fonts')
SS = 2  # ritas i dubbel upplosning


def font(kind, w, size):
    return ImageFont.truetype(os.path.join(F, 'ibm-plex-%s-latin-%d-normal.woff' % (kind, w)), int(size * SS))


TXT = (0xe6, 0xe8, 0xe7, 255); TXT2 = (0x9b, 0xa4, 0xa9, 255); TXT3 = (0x6a, 0x74, 0x7a, 255)
LINE = (0x9b, 0xa4, 0xa9, 150); HR = (0x4c, 0xc3, 0x8a, 255)

src, anf, out = sys.argv[1:4]
base = Image.open(src).convert('RGBA')
W, H = base.size
k = W / 1920.0
A = {n: (v[0] * SS, v[1] * SS) for n, v in json.load(open(anf)).items()}
ov = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(ov)


def P(x, y):
    return (x * k * SS, y * k * SS)


def lw(v):
    return max(1, int(round(v * k * SS)))


def text(xy, s, f, fill, anchor='la'):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def dashed(a, b, fill, width, dash=10, gap=8):
    ax, ay = a; bx, by = b
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    t = 0.0
    while t < L:
        t1 = min(L, t + dash * k * SS)
        d.line((ax + ux * t, ay + uy * t, ax + ux * t1, ay + uy * t1), fill=fill, width=width)
        t = t1 + gap * k * SS


def arrowhead(tip, frm, fill, size=9):
    ux, uy = tip[0] - frm[0], tip[1] - frm[1]
    L = math.hypot(ux, uy); ux /= L; uy /= L
    s = size * k * SS
    p1 = (tip[0] - ux * s - uy * s * 0.5, tip[1] - uy * s + ux * s * 0.5)
    p2 = (tip[0] - ux * s + uy * s * 0.5, tip[1] - uy * s - ux * s * 0.5)
    d.polygon([tip, p1, p2], fill=fill)


def trim(a, b, ta, tb):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    return (a[0] + ux * ta * k * SS, a[1] + uy * ta * k * SS), (b[0] - ux * tb * k * SS, b[1] - uy * tb * k * SS)


def link(a, b, ta, tb, label, sub, lf=0.5):
    p0, p1 = trim(A[a], A[b], ta, tb)
    dashed(p0, p1, LINE, lw(2))
    arrowhead(p1, p0, LINE)
    # datapaket langs linjen
    for f in (0.3, 0.5, 0.7):
        x = p0[0] + (p1[0] - p0[0]) * f; y = p0[1] + (p1[1] - p0[1]) * f
        r = 3.2 * k * SS
        d.ellipse((x - r, y - r, x + r, y + r), fill=HR)
    mx, my = p0[0] + (p1[0] - p0[0]) * lf, p0[1] + (p1[1] - p0[1]) * lf
    text((mx, my - 70 * k * SS), label, font('sans', 500, 21 * k), TXT2, 'ma')
    text((mx, my - 42 * k * SS), sub, font('sans', 400, 18 * k), TXT3, 'ma')


def stage(xy, num, title, lines, anchor_pt=None, align='l'):
    x, y = xy
    fnum = font('mono', 500, 18 * k)
    ft = font('sans', 600, 28 * k)
    fl = font('sans', 400, 20 * k)
    r = 15 * k * SS
    if align == 'l':
        cx = x + r
        d.ellipse((cx - r, y + 19 * k * SS - r, cx + r, y + 19 * k * SS + r), outline=TXT2, width=lw(1.5))
        text((cx, y + 19 * k * SS), num, fnum, TXT, 'mm')
        tx = x + 2 * r + 12 * k * SS
        text((tx, y), title, ft, TXT)
        for i, s in enumerate(lines):
            text((tx, y + (46 + 28 * i) * k * SS), s, fl, TXT2)
    else:
        text((x, y), title, ft, TXT, 'ra')
        for i, s in enumerate(lines):
            text((x, y + (46 + 28 * i) * k * SS), s, fl, TXT2, 'ra')
    if anchor_pt:
        pass


# rubrik
text(P(80, 70), 'Kropp64', font('mono', 500, 20 * k), TXT3)
text(P(80, 100), 'Dataflödet', font('sans', 600, 46 * k), TXT)
text(P(80, 166), 'Från klockan till läkarteamet. Språkmodellerna körs lokalt på Mac minin.', font('sans', 400, 22 * k), TXT2)

# lankar pa golvet
link('klocka_golv', 'telefon_golv', 80, 90, 'Wearable Data Layer', 'Bluetooth, batchar med kvittens')
link('telefon_golv', 'mini_golv', 90, 175, 'HTTPS via Cloudflare Tunnel', 'kön töms när servern svarar')

# steg 1 och 2: under foremalen
wx, wy = A['klocka_golv']
stage(P(330, 945), '1', 'Pixel Watch', ['Health Services: puls, steg, träningspass', 'HRV och SpO2 via Health Connect'])
tx_, ty_ = A['telefon_golv']
stage(P(780, 945), '2', 'Android', ['Kö + uppladdning', 'sparar lokalt tills servern kvitterat'])
mx_, my_ = A['mini_golv']
stage(P(1435, 945), '3', 'Mac mini M4, 16 GB', ['API, tidsseriedatabas, live-ström'])

# lagren: etiketter till vanster om stapeln med hanvisningslinjer
plates = [('granskare', 'Granskaren (moderatorn)', 'stryker påståenden utan källa'),
          ('konsilium', 'Läkarteamet (tråden)', 'specialistagenter läser data och journal'),
          ('vakt', 'Vakten', 'letar avvikelser mot din egen baslinje'),
          ('ollama', 'Lokal AI: Ollama', 'Qwen3.5 9B + MedGemma 4B')]
lx = A['lager_ollama_vanster'][0] - 70 * k * SS
for key, t, sub in plates:
    px, py = A['lager_' + key + '_vanster']
    d.line((lx + 14 * k * SS, py, px - 8 * k * SS, py), fill=LINE, width=lw(1.5))
    r = 3.5 * k * SS
    d.ellipse((px - 8 * k * SS - r, py - r, px - 8 * k * SS + r, py + r), fill=TXT2)
    text((lx, py - 30 * k * SS), t, font('sans', 600, 24 * k), TXT, 'ra')
    text((lx, py + 2 * k * SS), sub, font('sans', 400, 19 * k), TXT2, 'ra')
# flodespil mellan vakt -> tradens -> granskare, langs hoger sida av stapeln
xs = A['lager_vakt_hoger'][0] + 40 * k * SS
for lo, hi in (('vakt', 'konsilium'), ('konsilium', 'granskare')):
    y0 = A['lager_' + lo + '_hoger'][1] - 10 * k * SS
    y1 = A['lager_' + hi + '_hoger'][1] + 10 * k * SS
    d.line((xs, y0, xs, y1 + 4 * k * SS), fill=LINE, width=lw(2))
    arrowhead((xs, y1), (xs, y0), LINE)
for lo, hi, lab in (('vakt', 'konsilium', 'larm'), ('konsilium', 'granskare', 'bedömning')):
    yy = (A['lager_' + lo + '_hoger'][1] + A['lager_' + hi + '_hoger'][1]) / 2
    text((xs + 14 * k * SS, yy), lab, font('sans', 400, 18 * k), TXT3, 'lm')

ov = ov.resize((W, H), Image.LANCZOS)
Image.alpha_composite(base, ov).convert('RGB').save(out)
print('ok', out)
