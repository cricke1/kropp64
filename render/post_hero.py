"""Diskret ordmarke pa hjaltebilden: Kropp64 och taglinen i nedre hogra hornet.
python3 post_hero.py <render.png> <ut.png>
"""
import sys, os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(HERE, 'fonts')
SS = 2


def font(kind, w, size):
    return ImageFont.truetype(os.path.join(F, 'ibm-plex-%s-latin-%d-normal.woff' % (kind, w)), int(size * SS))


src, out = sys.argv[1:3]
base = Image.open(src).convert('RGBA')
W, H = base.size
k = min(W, H) / 1080.0
ov = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(ov)
m = 72 * k * SS
y = H * SS - m
x = W * SS - m
d.text((x, y - 34 * k * SS), 'Sensorpanelen för din viktigaste rigg: dig själv.', font=font('sans', 400, 22 * k),
       fill=(0x9b, 0xa4, 0xa9, 235), anchor='rs')
d.text((x, y - 74 * k * SS), 'Kropp64', font=font('sans', 600, 44 * k), fill=(0xe6, 0xe8, 0xe7, 245), anchor='rs')
ov = ov.resize((W, H), Image.LANCZOS)
Image.alpha_composite(base, ov).convert('RGB').save(out)
print('ok', out)
