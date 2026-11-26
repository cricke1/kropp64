#!/usr/bin/env python3
"""Animerad WebP: kardiologen drar en slutsats, moderatorn (vanlig Python) stryker den. Ur demofilmen,
kontoret beskuret och förstorat med närmaste granne så att pixelgrafiken förblir skarp."""
import subprocess, sys, tempfile
from pathlib import Path
from text import REPO, UT, skylt, RAD, BARN

DEMO = REPO / "docs/video/kropp64-demo-1920x1080.mp4"
W, H = 1242, 852  # kontoret 828x568 gånger 1,5

with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    skylt(W, H, "Kardiologen: \"tyder på hjärtmuskelinflammation\"", "Låter tvärsäkert. Men vilken mätpunkt säger det?", BARN, storlek=40).save(t / "s1.png")
    skylt(W, H, "Moderatorn: STRUKET", "Vanlig Python, ingen AI. Ingen källa = ingen mening.", RAD, storlek=44).save(t / "s2.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "133.5", "-t", "13", "-i", str(DEMO), "-loop", "1", "-i", str(t / "s1.png"),
                    "-loop", "1", "-i", str(t / "s2.png"), "-filter_complex",
                    "[0:v]crop=828:568:332:172,scale=1242:852:flags=neighbor,fps=12[v];"
                    "[v][1:v]overlay=enable='between(t,0.5,6.2)'[a];[a][2:v]overlay=enable='gte(t,6.6)',trim=0:13",
                    str(t / "f%04d.png")], check=True)
    ram = sorted(t.glob("f*.png"))
    # Sista bilden hålls kvar en stund så att strykningen hinner läsas innan loopen börjar om.
    args = ["img2webp", "-loop", "0", "-lossy", "-q", "72", "-m", "4", "-d", "83"]
    for f in ram[:-1]:
        args += [str(f)]
    args += ["-d", "2500", str(ram[-1]), "-o", str(UT / "02-moderatorn-stryker.webp")]
    subprocess.run(args, check=True, capture_output=True)
print(UT / "02-moderatorn-stryker.webp")
