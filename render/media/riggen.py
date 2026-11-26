#!/usr/bin/env python3
"""Animerad WebP: riggen, kroppen som PC-chassi i 3D. Pulsen stiger i vila, kylflänsarna går mot varmt."""
import subprocess, tempfile
from pathlib import Path
from text import REPO, UT, skylt, RAD

RIGG = REPO / "docs/video/riggen-demo-1920x1080.mp4"
W, H = 1440, 900  # 16:10, mitten av bilden
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    skylt(W, H, "Riggen: din kropp som PC-chassi", "Pulsen stiger i vila, kylflänsarna går mot rött. Live i webben.", RAD, storlek=42).save(t / "s.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(RIGG), "-loop", "1", "-i", str(t / "s.png"), "-filter_complex",
                    "[0:v]crop=1728:1080:96:0,scale=1440:900:flags=lanczos,fps=15[v];[v][1:v]overlay=enable='gte(t,0.6)',trim=0:14",
                    str(t / "f%04d.png")], check=True)
    ram = sorted(t.glob("f*.png"))
    args = ["img2webp", "-loop", "0", "-lossy", "-q", "70", "-m", "4", "-d", "67"] + [str(f) for f in ram[:-1]]
    args += ["-d", "1500", str(ram[-1]), "-o", str(UT / "03-riggen.webp")]
    subprocess.run(args, check=True, capture_output=True)
print(UT / "03-riggen.webp")
