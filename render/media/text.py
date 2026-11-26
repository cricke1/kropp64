"""Gemensamt för bidragsmaterialet: färger, typsnitt och textskyltar (PIL)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
FONTS = REPO / "render" / "fonts"
UT = REPO / "docs" / "bidrag-media"
BG = (14, 17, 19); TEXT = (236, 238, 237); TEXT2 = (155, 164, 169)
GRON = (76, 195, 138); RAD = (240, 100, 90); BARN = (224, 164, 88); BLA = (127, 182, 195)


def font(kind: str, w: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"ibm-plex-{kind}-latin-{w}-normal.woff"), size)


def skylt(w: int, h: int, rubrik: str, rad: str = "", farg=GRON, pos: str = "ned", storlek: int = 46) -> Image.Image:
    """Genomskinlig bild med en skylt längst ner (eller uppe): färgad kant, fet rubrik, rad under."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f1, f2 = font("sans", 600, storlek), font("sans", 400, int(storlek * 0.62))
    b1 = d.textbbox((0, 0), rubrik, font=f1); b2 = d.textbbox((0, 0), rad, font=f2) if rad else (0, 0, 0, 0)
    bw = max(b1[2], b2[2]) + 80; bh = (b1[3] - b1[1]) + ((b2[3] - b2[1]) + 18 if rad else 0) + 56
    x = 40; y = h - bh - 40 if pos == "ned" else 40
    d.rounded_rectangle((x, y, x + bw, y + bh), 18, fill=(10, 12, 14, 238))
    d.rounded_rectangle((x, y, x + 10, y + bh), 4, fill=farg + (255,))
    d.text((x + 40, y + 24), rubrik, font=f1, fill=TEXT)
    if rad:
        d.text((x + 40, y + 24 + (b1[3] - b1[1]) + 20), rad, font=f2, fill=TEXT2)
    return im
