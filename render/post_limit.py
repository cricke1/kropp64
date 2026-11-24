"""Text och stapeldiagram ovanpa 16 GB-renderingen. Bara uppmatta/angivna siffror:
Qwen3.5 9B 14,7 GB fore justering, 9,1 GB efter (RESAN.md), Qwen3.8-27B ca 18 GB (far inte plats).
python3 post_limit.py <render.png> <ankare.json> <ut.png>
"""
import sys, os, json
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(HERE, 'fonts')
SS = 2


def font(kind, w, size):
    return ImageFont.truetype(os.path.join(F, 'ibm-plex-%s-latin-%d-normal.woff' % (kind, w)), int(size * SS))


TXT = (0xe6, 0xe8, 0xe7, 255); TXT2 = (0x9b, 0xa4, 0xa9, 255); TXT3 = (0x6a, 0x74, 0x7a, 255)
LINE = (0x9b, 0xa4, 0xa9, 150); TRACK = (0x26, 0x2d, 0x32, 255)
OK = (0x4c, 0xc3, 0x8a, 255); WARN = (0xd9, 0xa0, 0x3f, 255); DANGER = (0xe5, 0x57, 0x4e, 255)

src, anf, out = sys.argv[1:4]
base = Image.open(src).convert('RGBA')
W, H = base.size
k = W / 1920.0
A = {n: (v[0] * SS, v[1] * SS) for n, v in json.load(open(anf)).items()}
ov = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(ov)


def P(x, y):
    return (x * k * SS, y * k * SS)


def u(v):
    return v * k * SS


def text(xy, s, f, fill, anchor='la'):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


# hanvisning till minnet pa M4-paketet: en punkt per minneskapsel, ihopdragna till en etikett nedanfor
ly = u(985)
jx = (A['minne0'][0] + A['minne1'][0]) / 2
jy = max(A['minne0'][1], A['minne1'][1]) + u(60)
for key in ('minne0', 'minne1'):
    x, y = A[key]
    d.line((x, y, jx, jy), fill=LINE, width=int(u(1.5)))
    d.ellipse((x - u(4), y - u(4), x + u(4), y + u(4)), fill=TXT)
d.line((jx, jy, jx, ly - u(10)), fill=LINE, width=int(u(1.5)))
text((jx, ly), '16 GB enhetligt minne', font('sans', 600, 24 * k), TXT, 'ma')
text((jx, ly + u(32)), 'på M4-paketet, delas av CPU, GPU och språkmodellen', font('sans', 400, 19 * k), TXT2, 'ma')

# hoger kolumn
x0, x1 = 1180, 1820
text(P(x0, 150), 'Kropp64  /  Systemet', font('mono', 500, 19 * k), TXT3)
text(P(x0, 182), 'Rigg nr 2 är också', font('sans', 600, 46 * k), TXT)
text(P(x0, 240), 'på gränsen', font('sans', 600, 46 * k), TXT)
text(P(x0, 318), 'Mac mini M4 med 16 GB. Minnet som språkmodellen', font('sans', 400, 21 * k), TXT2)
text(P(x0, 348), 'tog i Ollama, uppmätt på den här datorn.', font('sans', 400, 21 * k), TXT2)

GB = 20.0
bx0, bx1 = x0, x1


def gx(v):
    return bx0 + (bx1 - bx0) * v / GB


rows = [
    ('Qwen3.5 9B, 16k kontext, parallellt', 14.7, '14,7 GB', WARN, 'Ollamas standardläge. Datorn swappade.'),
    ('Qwen3.5 9B, 8k kontext, en i taget', 9.1, '9,1 GB', OK, 'KV-cache q8_0 och flash attention. Nuvarande.'),
    ('Qwen3.8-27B', 18.0, 'ca 18 GB', DANGER, 'får inte plats'),
]
y = 440
bh = 22
for (name, v, vs, col, note) in rows:
    text(P(x0, y), name, font('sans', 500, 21 * k), TXT)
    yb = y + 38
    d.rounded_rectangle(P(gx(0), yb) + P(gx(16), yb + bh), radius=u(3), fill=TRACK)
    vv = min(v, 16.0)
    d.rounded_rectangle(P(gx(0), yb) + P(gx(vv), yb + bh), radius=u(3), fill=col)
    if v > 16:
        # det som inte far plats: streckat over gransen
        xa, xb = gx(16), gx(v)
        d.rectangle(P(xa, yb) + P(xb, yb + bh), outline=col, width=int(u(2)))
        xx = xa
        while xx < xb:
            d.line(P(xx, yb + bh) + P(min(xx + bh, xb), yb + max(0, bh - (min(xx + bh, xb) - xx))), fill=col, width=int(u(2)))
            xx += 10
    text(P(x1, y), vs, font('mono', 500, 21 * k), col, 'ra')
    d.line(P(gx(16), yb - 7) + P(gx(16), yb + bh + 7), fill=TXT, width=int(u(2)))
    text(P(x0, yb + bh + 12), note, font('sans', 400, 18 * k), TXT3)
    y += 128

# 16 GB-gransen
gxl = gx(16)
text(P(gxl, y - 18), '16 GB', font('mono', 500, 19 * k), TXT, 'ma')
text(P(gx(0), y - 18), '0', font('mono', 400, 18 * k), TXT3, 'la')

ov = ov.resize((W, H), Image.LANCZOS)
Image.alpha_composite(base, ov).convert('RGB').save(out)
print('ok', out)
