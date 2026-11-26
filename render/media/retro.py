"""Formspråket för bidraget: PC-hårdvara, inte en mall. BIOS/POST-skärmar, RivaTuner-OSD och Award-BIOS-blått.
Allt ritas med PIL i IBM Plex Mono (IBM:s eget typsnitt, passande för en BIOS)."""
from PIL import Image, ImageDraw, ImageFilter
from text import font

W, H = 1920, 1080
SVART = (0, 0, 0)
GRA = (170, 170, 170); VIT = (255, 255, 255); GUL = (255, 255, 85); CYAN = (85, 255, 255); ROD = (255, 85, 85); GRON = (85, 255, 85)
BIOS_BLA = (0, 0, 170); BIOS_GRA = (170, 170, 170)
OSD_ORANGE = (255, 150, 0); OSD_GUL = (255, 230, 60); OSD_VIT = (255, 255, 255)


def mono(size, w=500):
    return font("mono", 500, size)


def post(rader, n_tecken=None, size=40, x=60, y=50, cursor=True) -> Image.Image:
    """POST-skärm: svart, grå text, (text, färg)-rader. n_tecken begränsar hur mycket som skrivits ut."""
    im = Image.new("RGB", (W, H), SVART); d = ImageDraw.Draw(im); f = mono(size)
    kvar = n_tecken if n_tecken is not None else 10 ** 9
    yy = y; lh = int(size * 1.32)
    for text, farg in rader:
        if kvar <= 0: break
        visa = text[:kvar]; kvar -= len(text) + 1
        d.text((x, yy), visa, font=f, fill=farg)
        if cursor and kvar <= 0:
            bb = d.textbbox((x, yy), visa, font=f)
            d.rectangle((bb[2] + 4, yy + size - 6, bb[2] + 4 + int(size * 0.6), yy + size), fill=GRA)
        yy += lh
    return im


def osd(im: Image.Image, rader, x=40, y=34, size=44) -> Image.Image:
    """RivaTuner-OSD: etikett i orange, värde i vitt/gult, svart kontur. rader: (etikett, värde, värdefärg)."""
    im = im.copy() if im.mode == "RGBA" else im.convert("RGB").copy(); d = ImageDraw.Draw(im); f = mono(size)
    lh = int(size * 1.22)
    ew = max(d.textbbox((0, 0), e, font=f)[2] for e, *_ in rader) + int(size * 0.8)
    for i, (etikett, varde, farg) in enumerate(rader):
        yy = y + i * lh
        d.text((x, yy), etikett, font=f, fill=OSD_ORANGE, stroke_width=4, stroke_fill=SVART)
        d.text((x + ew, yy), varde, font=f, fill=farg or OSD_VIT, stroke_width=4, stroke_fill=SVART)
    return im


def bios_ram(titel: str, size=34) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Award-BIOS-skärm: blå bakgrund, dubbel ram, titel i rubrikraden."""
    im = Image.new("RGB", (W, H), BIOS_BLA); d = ImageDraw.Draw(im); f = mono(size)
    d.rectangle((30, 24, W - 30, H - 24), outline=GRA, width=3)
    d.rectangle((40, 34, W - 40, H - 34), outline=GRA, width=3)
    tw = d.textbbox((0, 0), titel, font=f)[2]
    d.rectangle(((W - tw) // 2 - 20, 14, (W + tw) // 2 + 20, 14 + size + 16), fill=BIOS_BLA)
    d.text(((W - tw) // 2, 20), titel, font=f, fill=VIT)
    return im, d


def bios_halsa(rader, titel="Kropp64 Setup Utility - PC Health Status", fot="↑↓:Move  Enter:Select  F10:Rösta  ESC:Exit",
               size=46, markerad=None) -> Image.Image:
    """'PC Health Status': etikett med punkter fram till värdet. rader: (etikett, värde, färg)."""
    im, d = bios_ram(titel); f = mono(size)
    y = 150; lh = int(size * 1.75)
    for i, (e, v, farg) in enumerate(rader):
        if markerad == i:
            d.rectangle((90, y - 8, W - 90, y + size + 12), fill=(170, 0, 0))
        punkter = "." * max(3, 40 - len(e))
        d.text((120, y), f"{e} {punkter}", font=f, fill=GUL if markerad != i else VIT)
        vb = d.textbbox((0, 0), v, font=f)[2]
        d.text((W - 120 - vb, y), v, font=f, fill=farg or VIT)
        y += lh
    ff = mono(30); fw = d.textbbox((0, 0), fot.replace("↑↓", "^v"), font=ff)[2]
    d.text(((W - fw) // 2, H - 90), fot.replace("↑↓", "^v"), font=ff, fill=VIT)
    return im


def bios_dialog(fraga: str, svar: str = "", under: str = "", size=54) -> Image.Image:
    """BIOS-dialog i rött mitt på blå skärm: 'SAVE to CMOS and EXIT (Y/N)? Y'."""
    im, d = bios_ram("Kropp64 Setup Utility")
    f = mono(size); text = f"{fraga} {svar}"
    tw = d.textbbox((0, 0), fraga + " Y", font=f)[2]
    bw, bh = tw + 140, size + 110
    x0, y0 = (W - bw) // 2, (H - bh) // 2 - 40
    d.rectangle((x0 + 16, y0 + 16, x0 + bw + 16, y0 + bh + 16), fill=SVART)
    d.rectangle((x0, y0, x0 + bw, y0 + bh), fill=(170, 0, 0))
    d.rectangle((x0 + 10, y0 + 10, x0 + bw - 10, y0 + bh - 10), outline=GUL, width=3)
    d.text((x0 + 70, y0 + 55), text, font=f, fill=GUL)
    if under:
        fu = mono(36); uw = d.textbbox((0, 0), under, font=fu)[2]
        d.text(((W - uw) // 2, y0 + bh + 70), under, font=fu, fill=VIT)
    return im


def telefonram(bredd=440, hojd=1027):
    """Mask med rundade hörn för skärmen och en ram med skugga runt den."""
    mask = Image.new("L", (bredd, hojd), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bredd - 1, hojd - 1), 44, fill=255)
    ram = Image.new("RGBA", (bredd + 140, hojd + 140), (0, 0, 0, 0))
    skugga = Image.new("RGBA", ram.size, (0, 0, 0, 0))
    ImageDraw.Draw(skugga).rounded_rectangle((60, 80, 60 + bredd + 20, 80 + hojd + 20), 60, fill=(0, 0, 0, 200))
    ram = Image.alpha_composite(ram, skugga.filter(ImageFilter.GaussianBlur(28)))
    ImageDraw.Draw(ram).rounded_rectangle((58, 58, 82 + bredd, 82 + hojd), 56, fill=(30, 33, 36, 255), outline=(70, 76, 80, 255), width=3)
    return mask, ram
