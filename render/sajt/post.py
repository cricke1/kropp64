"""Efterbehandling av kretskortsbilden till sajten (kors pa Macen).

  python3 render/sajt/post.py <kretskort.png> <kretskort_heat.pgm> <site/bilder>
Ger webp i flera bredder (bred 3:2 och kvadratisk mobilutsnitt), varmekameraversionen (AOV:n "heat" genom
en ironbow-palett, suddad och nedskalad som en riktig varmekamera) och og.jpg.
"""
import io, os, sys
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
src, heat, ut = sys.argv[1:4]
os.makedirs(ut, exist_ok=True)
MOBIL_X0 = 600          # kvadratiskt utsnitt 1600x1600 som borjar har (processorn och lysdioden kommer med)

foto = Image.open(src).convert('RGB')
W, H = foto.size


def spara(im, namn, q=80):
    im.save(os.path.join(ut, namn), 'WEBP', quality=q, method=6)
    print(namn, im.size, os.path.getsize(os.path.join(ut, namn)) // 1024, 'kB')


def bredder(im, prefix, w_list, q=80):
    for w in w_list:
        h = round(im.height * w / im.width)
        spara(im.resize((w, h), Image.LANCZOS), '%s-%d.webp' % (prefix, w), q)


# lite skarpa efter nedskalning, lagom korn ar redan med fran renderingen
bredder(foto, 'kretskort', [2400, 1600, 1200], 78)
mobil = foto.crop((MOBIL_X0, 0, MOBIL_X0 + H, H))
bredder(mobil, 'kretskort-mobil', [1200, 800], 78)

# varmekamera
STOPP = [(0.0, (4, 2, 20)), (0.16, (38, 4, 104)), (0.36, (136, 18, 140)), (0.54, (214, 48, 70)),
         (0.70, (245, 122, 22)), (0.86, (252, 208, 64)), (1.0, (255, 251, 226))]


def lut():
    tab = []
    for i in range(256):
        t = i / 255
        for (a, ca), (b, cb) in zip(STOPP, STOPP[1:]):
            if a <= t <= b:
                f = (t - a) / (b - a)
                tab.append(tuple(round(ca[k] + (cb[k] - ca[k]) * f) for k in range(3)))
                break
    return tab


h16 = Image.open(heat)
h8 = h16.point(lambda v: v / 256).convert('L')
# en riktig varmekamera har lag upplosning: ner till 320 bred, mjuk upp
small = h8.resize((320, round(320 * H / W)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.2))
h8 = small.resize((W, H), Image.BICUBIC)
# kanter fran fotot, svagt, som MSX-overlagringen i varmekameror
kant = foto.convert('L').filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1.0))
kant = ImageEnhance.Brightness(kant).enhance(0.6)
from PIL import ImageChops
h8 = ImageChops.add(h8, kant.point(lambda v: v // 5))
tab = lut()
varm = Image.merge('RGB', [h8.point([c[k] for c in tab]) for k in range(3)])

# skala i hogerkanten, som pa en riktig varmekamera, men utan pahittade grader
d = ImageDraw.Draw(varm)
f = TTFont(os.path.join(REPO, 'site/fonts/martian-mono.woff2'))
f = instancer.instantiateVariableFont(f, {'wght': 500, 'wdth': 87.5})
f.flavor = None
b = io.BytesIO(); f.save(b); b.seek(0)
font = ImageFont.truetype(b, 26)
x1, y0, y1 = W - 70, 360, 1240
for y in range(y0, y1):
    t = 1 - (y - y0) / (y1 - y0)
    d.line([(x1, y), (x1 + 22, y)], fill=tab[round(t * 255)])
d.rectangle([x1 - 1, y0 - 1, x1 + 23, y1], outline=(240, 236, 228))
d.text((x1 + 11, y0 - 16), 'varmt', font=font, fill=(240, 236, 228), anchor='ms')
d.text((x1 + 11, y1 + 40), 'kallt', font=font, fill=(240, 236, 228), anchor='ms')
bredder(varm, 'varme', [1600], 76)
bredder(varm.crop((MOBIL_X0, 0, MOBIL_X0 + H, H)), 'varme-mobil', [800], 76)

# og-bild 1200x630
og = foto.crop((300, 120, 300 + 2100, 120 + round(2100 * 630 / 1200))).resize((1200, 630), Image.LANCZOS)
og.save(os.path.join(ut, 'og.jpg'), quality=84, optimize=True, progressive=True)
print('og.jpg', os.path.getsize(os.path.join(ut, 'og.jpg')) // 1024, 'kB')
