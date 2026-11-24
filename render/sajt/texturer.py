"""Ritar texturerna till sajtens kretskortsbild (kors pa Macen, kraver Pillow och fontTools).

  python3 render/sajt/texturer.py <utmapp>
Ger pcb.png (R = koppar under lodmasken, G = oppet guld, B = silkscreen) och etch.png (lasergravyren pa
processorns lock). Typsnitten tas ur render/fonts och site/fonts sa att bilden har samma typsnitt som sajten.
"""
import io, math, os, random, sys
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from pcb_layout import *  # noqa

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'ut')
os.makedirs(OUT, exist_ok=True)


def ttf(path, wght=None):
    f = TTFont(path)
    if wght is not None and 'fvar' in f:
        from fontTools.varLib import instancer
        f = instancer.instantiateVariableFont(f, {'wght': wght})
    f.flavor = None
    b = io.BytesIO()
    f.save(b)
    b.seek(0)
    return b


MONO = ttf(os.path.join(REPO, 'render/fonts/ibm-plex-mono-latin-500-normal.woff'))
GROT = os.path.join(REPO, 'site/fonts/familjen-grotesk.woff2')

W, D, T = BOARD
P = PX_PER_MM
IW, IH = int(W * P), int(D * P)


def px(x, y):
    return ((x + W / 2) * P, (D / 2 - y) * P)


def pcb():
    im = Image.new('RGB', (IW, IH), (0, 0, 0))
    r = Image.new('L', (IW, IH), 0)
    g = Image.new('L', (IW, IH), 0)
    b = Image.new('L', (IW, IH), 0)
    dr, dg, db = ImageDraw.Draw(r), ImageDraw.Draw(g), ImageDraw.Draw(b)
    rnd = random.Random(7)
    cx, cy = CPU
    hs = SUBSTRATE / 2

    def line(d, pts, w_mm, fill=255):
        d.line([px(*p) for p in pts], fill=fill, width=max(1, int(w_mm * P)), joint='curve')

    def rect(d, x0, y0, x1, y1, fill=255, outline=None, w=0):
        a, b_ = px(x0, y1), px(x1, y0)
        if outline is not None:
            d.rectangle([a, b_], outline=outline, width=max(1, int(w * P)))
        else:
            d.rectangle([a, b_], fill=fill)

    def circ(d, x, y, rad, fill=255, outline=None, w=0):
        a, b_ = px(x - rad, y + rad), px(x + rad, y - rad)
        if outline is not None:
            d.ellipse([a, b_], outline=outline, width=max(1, int(w * P)))
        else:
            d.ellipse([a, b_], fill=fill)

    # kopparytor (jordplan) under masken: svagt ljusare falt
    for (x0, y0, x1, y1) in ((cx - 42, cy + 18, cx + 44, cy + 56), (-108, -73, -60, -40), (40, -73, 108, -20)):
        rect(dr, x0, y0, x1, y1, fill=70)
    # bussar ut fran processorn, 45-gradersbojar som riktiga ledningsdragningar
    def bus(n, start, d1, len1, d2, len2, pitch=0.55, wid=0.16):
        sx, sy = start
        nx, ny = -d1[1], d1[0]
        for i in range(n):
            o = (i - n / 2) * pitch
            p0 = (sx + nx * o, sy + ny * o)
            p1 = (p0[0] + d1[0] * (len1 + i * pitch * 0.4), p0[1] + d1[1] * (len1 + i * pitch * 0.4))
            p2 = (p1[0] + d2[0] * len2, p1[1] + d2[1] * len2)
            line(dr, [p0, p1, p2], wid, 255)
            circ(dg, p2[0], p2[1], 0.22)
    s2 = math.sqrt(0.5)
    bus(16, (cx, cy - hs), (0, -1), 8, (s2, -s2), 70)
    bus(12, (cx + hs, cy - 4), (1, 0), 10, (s2, -s2), 70)
    bus(10, (cx + hs, cy + 10), (1, 0), 22, (s2, s2), 30)
    bus(14, (cx - hs, cy - 12), (-1, 0), 6, (-s2, -s2), 60)
    bus(8, (cx - 6, cy + hs), (0, 1), 6, (-s2, s2), 50)
    # strodda signalledare
    for _ in range(46):
        x0, y0 = rnd.uniform(-105, 105), rnd.uniform(-72, 72)
        if abs(x0 - cx) < hs + 2 and abs(y0 - cy) < hs + 2:
            continue
        if x0 < 0 and cy - 14 < y0 < cy + 20:
            continue
        dx = rnd.choice([1, -1]) * rnd.uniform(5, 30)
        dy = rnd.choice([1, -1]) * rnd.uniform(3, 15)
        if x0 < 20:
            dy = abs(dy) if y0 > cy else -abs(dy)
            dx = -abs(dx) if x0 + dx > -5 and abs(y0 - cy) < 26 else dx
        line(dr, [(x0, y0), (x0 + dx, y0), (x0 + dx + dy, y0 + dy)], 0.2)
        for (vx, vy) in ((x0, y0), (x0 + dx + dy, y0 + dy)):
            circ(dg, vx, vy, 0.3)
    # vior i rutnat runt processorn (stromforsorjning)
    for i in range(-9, 10):
        for j in (-1, 1):
            circ(dg, cx + i * 1.9, cy + j * (hs + 3.2), 0.28)
            circ(dg, cx + j * (hs + 3.2), cy + i * 1.9, 0.28)

    # EKG-bussen: oppen guldledare
    pts = ecg_path()
    line(dg, pts, 0.75)
    circ(dg, pts[0][0] + 1.5, pts[0][1], 1.4)
    for (x, y) in pts:
        if abs(y - cy) > 10:
            circ(dg, x, y, 0.9)   # testpunkt pa toppen av varje QRS-spik
    # silkscreen kring bussen: tidsmarkeringar som pa EKG-papper
    for k in range(0, 21):
        x = -104 + k * 4.4
        line(db, [(x, cy - 3.2), (x, cy - 3.2 - (1.2 if k % 5 == 0 else 0.6))], 0.13)

    # lodytor och silkscreenramar per komponent
    for typ, x, y, rot, lab in components():
        hor = rot == 0
        if typ in ('c0402', 'c0603', 'r0603', 'led'):
            L = {'c0402': 0.5, 'c0603': 0.8, 'r0603': 0.8, 'led': 0.8}[typ]
            pw = {'c0402': 0.28, 'c0603': 0.45, 'r0603': 0.45, 'led': 0.45}[typ]
            ph = {'c0402': 0.3, 'c0603': 0.5, 'r0603': 0.5, 'led': 0.45}[typ]
            for s in (-1, 1):
                ox, oy = (s * L, 0) if hor else (0, s * L)
                ww, hh = (pw, ph) if hor else (ph, pw)
                rect(dg, x + ox - ww, y + oy - hh, x + ox + ww, y + oy + hh)
            if typ == 'led':
                rect(db, x - 1.6, y - 0.9, x + 1.6, y + 0.9, outline=255, w=0.12)
                dB = db
                a = [px(x - 2.3, y + 0.6), px(x - 2.3, y - 0.6), px(x - 1.8, y)]
                dB.polygon(a, fill=255)
        elif typ == 'choke':
            rect(db, x - 4.6, y - 4.6, x + 4.6, y + 4.6, outline=255, w=0.15)
            rect(dg, x - 4.2, y - 4.9, x + 4.2, y - 3.9)
        elif typ == 'mosfet':
            for k in range(4):
                rect(dg, x - 2.1 + k * 1.27 - 0.3, y - 3.4, x - 2.1 + k * 1.27 + 0.3, y - 2.6)
            rect(db, x - 3.1, y - 3.8, x + 3.1, y + 3.2, outline=255, w=0.12)
        elif typ == 'polycap':
            circ(db, x, y, 4.4, outline=255, w=0.15)
            line(db, [(x - 5.6, y + 3.2), (x - 4.4, y + 3.2)], 0.15)
            line(db, [(x - 5.0, y + 2.6), (x - 5.0, y + 3.8)], 0.15)
        elif typ == 'fan':
            rect(db, x - 5.6, y - 3.0, x + 5.6, y + 3.4, outline=255, w=0.15)
            for k in range(4):
                circ(dg, x - 3.81 + k * 2.54, y, 0.75)
    # processorn: hornmarkeringar och pinne-1-triangel
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            X, Y = cx + sx_ * (hs + 1.2), cy + sy_ * (hs + 1.2)
            line(db, [(X - sx_ * 4, Y), (X, Y), (X, Y - sy_ * 4)], 0.18)
    db.polygon([px(cx - hs - 2.6, cy + hs + 0.6), px(cx - hs - 0.6, cy + hs + 0.6), px(cx - hs - 2.6, cy + hs - 1.4)], fill=255)
    # monteringshal med guldring
    for (x, y) in ((-100, 65), (100, 65), (-100, -65), (100, -65), (60, 50)):
        circ(dg, x, y, 3.6)
        circ(dg, x, y, 1.6, fill=0)
    # text
    for text, x, y, size, rot in SILK:
        MONO.seek(0)
        f = ImageFont.truetype(MONO, int(size * P))
        db.text(px(x, y), text, font=f, fill=255, anchor='ls')
    im = Image.merge('RGB', (r, g, b))
    im.save(os.path.join(OUT, 'pcb.png'), optimize=True)
    print('pcb.png', im.size)


def etch():
    S = 2048
    im = Image.new('L', (S, S), 0)
    d = ImageDraw.Draw(im)
    k = S / IHS  # px per mm
    g6 = ttf(GROT, 640)
    g4 = ttf(GROT, 480)
    big = ImageFont.truetype(g6, int(6.2 * k))
    g4.seek(0)
    sm = ImageFont.truetype(g4, int(1.7 * k))
    MONO.seek(0)
    mono = ImageFont.truetype(MONO, int(1.45 * k))
    x0 = 3.2 * k
    d.text((x0, 9.0 * k), 'Kropp64', font=big, fill=255, anchor='ls')
    d.text((x0, 13.0 * k), 'Klockfrekvens 67 BPM', font=sm, fill=255, anchor='ls')
    d.text((x0, 16.0 * k), 'Idle-klock 49 BPM', font=sm, fill=255, anchor='ls')
    d.text((x0, 22.8 * k), 'K64-0067  SE  2026', font=mono, fill=255, anchor='ls')
    d.text((x0, 25.2 * k), 'Rigg nr 1', font=mono, fill=255, anchor='ls')
    # datamatris nere till hoger
    rnd = random.Random(64)
    m0x, m0y, cell = 21.2 * k, 20.6 * k, 0.4 * k
    for i in range(14):
        for j in range(14):
            on = (i == 0 or j == 13) or (j == 0 and i % 2 == 0) or (i == 13 and j % 2 == 1) or rnd.random() < 0.48
            if on:
                d.rectangle([m0x + i * cell, m0y + j * cell, m0x + (i + 1) * cell - 1, m0y + (j + 1) * cell - 1], fill=255)
    # pinne 1
    d.polygon([(1.4 * k, 1.4 * k), (3.2 * k, 1.4 * k), (1.4 * k, 3.2 * k)], fill=255)
    im.save(os.path.join(OUT, 'etch.png'), optimize=True)
    print('etch.png', im.size)


if __name__ == '__main__':
    pcb()
    etch()
