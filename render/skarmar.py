"""Skarmtexturer for hjaltebilden: Kropp64:s sensorpanel pa mobilen och pulsvyn pa klockan.
Vardena ar EXEMPELVARDEN for en produktbild (samma som i docs/VARUMARKE.md), inte uppmatt data.

python3 skarmar.py   -> tex_mobil_panel.png, tex_klocka_panel.png
"""
import os, math
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(HERE, 'fonts')


def font(kind, w, size):
    return ImageFont.truetype(os.path.join(F, 'ibm-plex-%s-latin-%d-normal.woff' % (kind, w)), size)


BG = (0x0e, 0x11, 0x13); SURF = (0x14, 0x18, 0x1b); LINE = (0x26, 0x2d, 0x32)
TXT = (0xe6, 0xe8, 0xe7); TXT2 = (0x9b, 0xa4, 0xa9); TXT3 = (0x6a, 0x74, 0x7a)
HR = (0x4c, 0xc3, 0x8a); SPO2 = (0x4f, 0xb3, 0xd9); HRV = (0xe0, 0x90, 0x5e)


def rtext(d, xy, s, f, fill):
    x, y = xy
    w = d.textlength(s, font=f)
    d.text((x - w, y), s, font=f, fill=fill)


def mobil():
    W, H = 1080, 2400
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    m = 60
    d.text((m, 40), '21:14', font=font('sans', 500, 40), fill=TXT)
    d.text((m, 170), 'Kropp64', font=font('sans', 600, 72), fill=TXT)
    d.ellipse((W - m - 250, 205, W - m - 232, 223), fill=HR)
    rtext(d, (W - m, 190), 'Ansluten', font('sans', 400, 40), TXT2)
    d.text((m, 270), 'Sensorpanelen för din viktigaste rigg', font=font('sans', 400, 38), fill=TXT3)
    # stor avlasning
    d.text((m, 380), 'Klockfrekvens', font=font('sans', 500, 44), fill=TXT2)
    d.text((m - 6, 430), '67', font=font('mono', 500, 230), fill=TXT)
    d.text((m + 300, 590), 'BPM', font=font('mono', 400, 60), fill=HR)
    d.text((m + 300, 520), 'beats, inte MHz', font=font('sans', 400, 36), fill=TXT3)
    # pulskurva (jamn, lugn vila)
    gx0, gx1, gy0, gy1 = m, W - m, 730, 1010
    for k in range(4):
        y = gy0 + (gy1 - gy0) * k / 3
        d.line((gx0, y, gx1, y), fill=LINE, width=2)
    pts = []
    n = 240
    for i in range(n):
        t = i / (n - 1)
        v = 66 + 4 * math.sin(t * 9.0) + 2.5 * math.sin(t * 31 + 1) + 1.2 * math.sin(t * 77 + 2)
        if 0.55 < t < 0.68:
            v += 22 * math.sin((t - 0.55) / 0.13 * math.pi)
        pts.append((gx0 + t * (gx1 - gx0), gy1 - (v - 50) / 50 * (gy1 - gy0)))
    d.line(pts, fill=HR, width=6, joint='curve')
    d.ellipse((pts[-1][0] - 12, pts[-1][1] - 12, pts[-1][0] + 12, pts[-1][1] + 12), fill=HR)
    d.text((gx0, gy1 + 16), '18:00', font=font('mono', 400, 32), fill=TXT3)
    rtext(d, (gx1, gy1 + 16), 'nu', font('mono', 400, 32), TXT3)
    # tabell i HWiNFO-stil
    y = 1120
    cols = [m, 650, 780, 905, W - m]
    hf = font('sans', 500, 34)
    d.text((cols[0], y), 'Sensor', font=hf, fill=TXT3)
    for c, s in zip(cols[1:], ('Aktuellt', 'Min', 'Max', 'Medel')):
        rtext(d, (c, y), s, hf, TXT3)
    y += 64
    groups = [
        ('Hjärta (Pixel Watch)', [('Klockfrekvens', '67', '52', '118', '71', HR), ('Idle-klock', '54', '51', '58', '54', HR),
                                  ('Timingmarginal (HRV)', '48', '31', '62', '45', HRV)]),
        ('Kylning', [('Headroom', '72', '', '', '', TXT)]),
        ('Last', [('Steg', '6 412', '', '', '', TXT), ('Uptime vid datorn', '6 h', '', '', '', TXT)]),
    ]
    rf = font('sans', 400, 40)
    nf = font('mono', 400, 40)
    for g, rows in groups:
        d.line((m, y, W - m, y), fill=LINE, width=2)
        y += 22
        d.text((m, y), g, font=font('sans', 600, 40), fill=TXT)
        y += 70
        for (nm, a, mi, ma, me, col) in rows:
            d.text((m + 24, y), nm, font=rf, fill=TXT2)
            rtext(d, (cols[1], y), a, nf, col)
            rtext(d, (cols[2], y), mi, nf, TXT3)
            rtext(d, (cols[3], y), ma, nf, TXT3)
            rtext(d, (cols[4], y), me, nf, TXT3)
            y += 66
        y += 18
    # flikrad
    d.rectangle((0, H - 210, W, H), fill=SURF)
    d.line((0, H - 210, W, H - 210), fill=LINE, width=2)
    tabs = ['Panel', 'Tidslinje', 'Tråden', 'Fråga', 'Inställn.']
    for i, t in enumerate(tabs):
        cx = W * (i + 0.5) / len(tabs)
        f = font('sans', 500, 34)
        w = d.textlength(t, font=f)
        d.text((cx - w / 2, H - 160), t, font=f, fill=TXT if i == 0 else TXT3)
    d.rectangle((W * 0.5 / len(tabs) - 50, H - 210, W * 0.5 / len(tabs) + 50, H - 204), fill=SPO2)
    d.rounded_rectangle((W / 2 - 120, H - 50, W / 2 + 120, H - 40), 5, fill=TXT2)
    im.save(os.path.join(HERE, 'tex_mobil_panel.png'))


def klocka():
    S = 600
    im = Image.new('RGB', (S, S), (0, 0, 0))
    d = ImageDraw.Draw(im)
    c = S / 2

    def ctext(y, s, f, fill):
        w = d.textlength(s, font=f)
        d.text((c - w / 2, y), s, font=f, fill=fill)
    ctext(62, '21:14', font('sans', 500, 44), TXT)
    ctext(150, 'Klockfrekvens', font('sans', 500, 42), TXT2)
    ctext(200, '67', font('sans', 500, 170), TXT)
    ctext(400, 'BPM', font('mono', 500, 44), HR)
    # tunn bage som pulsindikator
    d.arc((22, 22, S - 22, S - 22), 125, 125 + 290 * 0.45, fill=HR, width=10)
    d.arc((22, 22, S - 22, S - 22), 125 + 290 * 0.45 + 3, 125 + 290, fill=(0x22, 0x27, 0x2a), width=10)
    ctext(470, 'Headroom 72', font('sans', 400, 34), TXT3)
    im.save(os.path.join(HERE, 'tex_klocka_panel.png'))


if __name__ == '__main__':
    mobil()
    klocka()
