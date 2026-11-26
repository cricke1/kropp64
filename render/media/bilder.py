#!/usr/bin/env python3
"""Bidragsbilderna (1-10, högst 5 MB styck) i projektets formspråk: POST-skärm, RivaTuner-OSD och
Award-BIOS (retro.py). Animerade WebP där det går, eftersom de spelas upp direkt i forumtråden.

  .venv/bin/python bilder.py [namn ...]     utan namn: alla
Utdata i docs/bidrag-media/. Kortbilden (01) görs av kort.py när 3D-renderingen är klar.
"""
import subprocess, sys, tempfile
from pathlib import Path
from PIL import Image
import retro as R
from text import REPO

UT = REPO / "docs/bidrag-media"
DEMO = REPO / "docs/video/kropp64-demo-1920x1080.mp4"
RIGG = REPO / "docs/video/riggen-demo-1920x1080.mp4"
MOBIL = REPO / "render/media/skarm/mobil-film.mp4"
BW, BH = 1600, 1000  # 16:10, som galleriet på tävlingssidan


def ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def webp(ramar: list[Path], ut: Path, ms: int, sista_ms: int = 1500, q: int = 70):
    args = ["img2webp", "-loop", "0", "-lossy", "-q", str(q), "-m", "4", "-d", str(ms)] + [str(f) for f in ramar[:-1]]
    args += ["-d", str(sista_ms), str(ramar[-1]), "-o", str(ut)]
    subprocess.run(args, check=True, capture_output=True)
    mb = ut.stat().st_size / 1e6
    if mb > 4.9 and q > 40:  # tävlingssidan tar högst 5 MB
        return webp(ramar, ut, ms, sista_ms, q - 12)
    print(ut.name, f"{mb:.1f} MB")


def osd_png(rader, w, h, x=30, y=26, size=40) -> Image.Image:
    return R.osd(Image.new("RGBA", (w, h), (0, 0, 0, 0)), rader, x=x, y=y, size=size)


def post_anim():
    """02: POST-skärmen skrivs ut och stannar på varningen."""
    from trailer import POST
    with tempfile.TemporaryDirectory() as t:
        t = Path(t); tecken = sum(len(r) + 1 for r, _ in POST); ramar = []
        steg = list(range(0, tecken, 9)) + [tecken]
        for i, n in enumerate(steg):
            im = R.post(POST, n_tecken=n, size=46).resize((BW, BH), Image.LANCZOS)
            p = t / f"{i:04d}.png"; im.save(p); ramar.append(p)
        # blinkande markör på slutet
        for j in range(6):
            im = R.post(POST, n_tecken=tecken, size=46, cursor=j % 2 == 0).resize((BW, BH), Image.LANCZOS)
            p = t / f"z{j}.png"; im.save(p); ramar.append(p)
        webp(ramar, UT / "02-post.webp", 40, sista_ms=4000)


def strykningen():
    """03: kardiologen drar en slutsats, moderatorn stryker den. Pixelkontoret förstorat med närmaste granne."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        osd_png([("KARDIOLOG", "\"hjärtmuskelinflammation\"", R.OSD_GUL), ("KÄLLA", "???", R.ROD)], BW, BH, y=860, size=44).save(t / "o1.png")
        osd_png([("MODERATOR", "STRUKET", R.ROD), ("SKÄL", "inget i datan pekar dit", None),
                 ("MODELL", "ingen, det är vanlig Python", R.GRON)], BW, BH, y=810, size=44).save(t / "o2.png")
        ff("-ss", "133.5", "-t", "11", "-i", str(DEMO), "-loop", "1", "-i", str(t / "o1.png"), "-loop", "1", "-i", str(t / "o2.png"),
           "-filter_complex", f"[0:v]crop=828:518:332:172,scale={BW}:{BH}:flags=neighbor,fps=12[v];"
           "[v][1:v]overlay=enable='between(t,0.3,6.3)'[a];[a][2:v]overlay=enable='gte(t,6.6)',trim=0:11", str(t / "f%04d.png"))
        webp(sorted(t.glob("f*.png")), UT / "03-moderatorn-stryker.webp", 83, sista_ms=3000)


def appen():
    """04: riktiga appen i telefonram på svart, med OSD bredvid."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t); mask, ram = R.telefonram(380, 887)
        mask.save(t / "m.png"); ram.save(t / "r.png")
        bg = R.osd(Image.new("RGB", (BW, BH), (0, 0, 0)), [("APPEN", "Android + Wear OS", R.OSD_GUL), ("DESIGN", "Material 3", None),
                                                           ("DATA", "min riktiga, inte demo", R.GRON), ("KALLSTART", "210 ms", None),
                                                           ("STORLEK", "5,3 MB", None)], x=90, y=330, size=46)
        bg.save(t / "bg.png")
        ff("-i", str(t / "bg.png"), "-ss", "0.5", "-t", "22", "-i", str(MOBIL), "-i", str(t / "m.png"), "-i", str(t / "r.png"),
           "-filter_complex", "[1:v]fps=10,scale=380:887,format=rgba[sk];[2:v]format=gray[m];[sk][m]alphamerge[skr];"
           "[0:v][3:v]overlay=1050:-10[b];[b][skr]overlay=1110:46", "-t", "22", str(t / "f%04d.png"))
        webp(sorted(t.glob("f*.png")), UT / "04-appen.webp", 100, sista_ms=1000, q=66)


def riggen():
    """05: riggen, kroppen som PC-chassi."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        osd_png([("RIGGEN", "kroppen som PC-chassi", R.OSD_GUL), ("FLÄKTAR", "styrs av pulsen", None),
                 ("VARMT", "när pulsen stiger i vila", R.ROD)], BW, BH, y=170, size=42).save(t / "o.png")
        ff("-i", str(RIGG), "-loop", "1", "-i", str(t / "o.png"), "-filter_complex",
           f"[0:v]crop=1728:1080:96:0,scale={BW}:{BH},fps=12[v];[v][1:v]overlay=shortest=1,trim=0:14", str(t / "f%04d.png"))
        webp(sorted(t.glob("f*.png")), UT / "05-riggen.webp", 83, sista_ms=1500, q=64)


def halsa():
    """06: siffrorna som en PC Health Status-skärm."""
    rader = [("Rätt brådska, holdout-fall", "36/36", R.GRON), ("Godtagbar brådska", "56% -> 100%", R.VIT),
             ("Måste-fynd i svaret", "67% -> 94%", R.VIT), ("Tid per tråd, M4", "226 s -> 118 s", R.VIT),
             ("Missade akuta fall", "4 -> 0", R.VIT), ("Minne, qwen3.5:9b", "9,1 / 16 GB", R.GUL),
             ("RTX 5050 mot M4", "56 s / 126 s", R.CYAN)]
    im = R.bios_halsa(rader, fot="Syntetiska testfall, skrivna innan körning.  eval/RESULTAT.md", markerad=0)
    im.resize((BW, BH), Image.LANCZOS).save(UT / "06-health-status.png", optimize=True)
    print("06-health-status.png")


def grans():
    """07: 16 GB-renderingen med OSD."""
    g = Image.open(REPO / "docs/render/kropp64-16gb-gransen.png").convert("RGB")
    g = R.osd(g, [("RAM", "16 GB räcker. Precis.", R.OSD_GUL), ("GEMMA 12B", "bättre, men 12,3 GB", R.ROD),
                  ("MED 128 GB", "hela teamet parallellt", R.GRON)], x=60, y=60, size=46)
    g.resize((BW, BH), Image.LANCZOS).save(UT / "07-16gb.jpg", quality=92)
    print("07-16gb.jpg")


ALLA = {"post": post_anim, "strykningen": strykningen, "appen": appen, "riggen": riggen, "halsa": halsa, "grans": grans}
if __name__ == "__main__":
    for namn in (sys.argv[1:] or ALLA):
        ALLA[namn]()
