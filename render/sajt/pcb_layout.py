"""Gemensam layout for kretskortet i sajtens hjaltebild (render/sajt).

Ren Python utan beroenden: laddas bade av texturer.py (Mac, PIL ritar masker) och av kretskort.py
(Blender pa Lenovon, placerar 3D-komponenterna pa samma ytor). Allt i millimeter, kortets mitt = origo,
+x at hoger, +y bort fran kameran.
"""
import math, random

BOARD = (220.0, 150.0, 1.6)      # bredd, djup, tjocklek
PX_PER_MM = 36                    # texturupplosning
CPU = (14.0, 6.0)                 # mitt pa processorn (U1)
SUBSTRATE = 37.5
IHS = 30.0

# EKG-bussen: guldplaterad, oppen ledare fran vanster kant in till processorns substrat
def ecg_path():
    """Lista med (x, y) i mm. Tva slag, sedan rakt in i U1."""
    y0 = CPU[1]
    x = -110.0
    pts = [(x, y0)]
    beat = [  # (dx, dy) relativt baslinjen, ett hjartslag ~44 mm brett
        (6, 0), (2.0, 2.2), (2.0, 2.6), (2.0, 0), (3, 0), (1.0, -1.6), (1.6, 14.0), (1.6, -7.5), (1.2, 0),
        (4, 0), (3.0, 3.8), (3.0, 4.2), (3.0, 0), (9, 0)]
    for _ in range(2):
        cx = pts[-1][0]
        for dx, dy in beat:
            cx += dx
            pts.append((cx, y0 + dy))
    pts.append((CPU[0] - SUBSTRATE / 2 - 0.5, y0))
    return pts


def components(seed=64):
    """Komponenter som ska bade ha lodytor i texturen och en 3D-kropp. Varje post:
    (typ, x, y, rotation_grader, etikett)"""
    rnd = random.Random(seed)
    out = []
    cx, cy = CPU
    # VRM-raden ovanfor processorn: drosslar, MOSFET, polymerkondensatorer
    for i in range(6):
        x = cx - 30 + i * 12.0
        out.append(('choke', x, cy + 34, 0, 'L%d' % (i + 1)))
        out.append(('mosfet', x, cy + 25, 0, 'Q%d' % (i + 1)))
    for i in range(7):
        out.append(('polycap', cx - 36 + i * 12.0, cy + 47, 0, 'C%d' % (201 + i)))
    # 0402-kondensatorer i rader langs processorns underkant och hogerkant
    for i in range(14):
        out.append(('c0402', cx - 16 + i * 2.4, cy - 24.5, 90, ''))
    for i in range(10):
        out.append(('c0402', cx + 24.5, cy - 12 + i * 2.6, 0, ''))
    # glest strodda motstand och kondensatorer runt EKG-bussen
    for i in range(16):
        x = rnd.uniform(-95, -15)
        y = rnd.uniform(24, 52) if x > -70 else rnd.uniform(-40, -12)
        out.append((rnd.choice(['r0603', 'c0603', 'c0402']), x, y, rnd.choice([0, 90]), ''))
    for i in range(10):
        out.append((rnd.choice(['r0603', 'c0603']), rnd.uniform(40, 95), rnd.uniform(-60, -30), rnd.choice([0, 90]), ''))
    # hjartslags-LED bredvid bussen, flaktkontakten "Andning"
    out.append(('led', -14.0, cy + 13.0, 0, 'D7'))
    out.append(('fan', -48.0, cy + 30.0, 0, 'J4'))
    return out


SILK = [  # (text, x, y, storlek_mm, rotation)
    ('Kropp64 rev 1.0', -98.0, -52.0, 3.4, 0),
    ('Rigg nr 1. Kan inte bytas ut.', -98.0, -57.5, 1.9, 0),
    ('U1', CPU[0] - SUBSTRATE / 2 - 1.0, CPU[1] + SUBSTRATE / 2 + 2.4, 1.8, 0),
    ('Hjärta', -100.0, CPU[1] - 8.0, 2.0, 0),
    ('D7 HB', -14.0 - 2.5, CPU[1] + 16.0, 1.4, 0),
    ('J4 Andning', -48.0 - 7.0, CPU[1] + 36.0, 1.6, 0),
    ('Vcore', CPU[0] - 30 - 6, CPU[1] + 40.5, 1.5, 0),
    ('Klocka 67 BPM', -100.0, CPU[1] + 18.0, 1.6, 0),
]
