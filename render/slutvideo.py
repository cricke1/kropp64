#!/usr/bin/env python3
"""Bidragsfilmen (16:9, ca 3 min) av material som redan finns i repot.

  python3 render/slutvideo.py <arbetsmapp> <berättarröst-mapp>

Berättarrösten (n1-n5.wav) är Gemini TTS, rösten Sulafat. Det är systemet som pratar ("Jag är Kropp64"),
inte jag. Läkarnas röster och allt i kontoret kommer från demofilmen (docs/video/README.md), där allt är
syntetiskt och märkt. Utdata: docs/video/kropp64-bidrag-1920x1080.mp4 (ligger inte i git, för stor).

Delar:
  A  3D-animationen (docs/render/kropp64-animation.mp4), sista bilden hålls så länge rösten pratar
  B  sensorpanelen och pulsen vid datorn (docs/bidrag-bilder 04 och 05), långsam zoom
  C  riggen (docs/video/riggen-demo-1920x1080.mp4)
  D  mellankort
  E  demotråden, kortad: 2-60 s och 121-191,4 s, med skyltar vid trollet, strykningen och lösningen
  F  16 GB-gränsen (docs/render/kropp64-16gb-gransen.png) med mätresultatet
  G  slutkort
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
FONTS = REPO / "render" / "fonts"
W, H, FPS = 1920, 1080, 30
BG, TEXT, TEXT2, OK, WARN = (14, 17, 19), (230, 232, 231), (155, 164, 169), (76, 195, 138), (217, 160, 63)


def font(kind: str, w: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"ibm-plex-{kind}-latin-{w}-normal.woff"), size)


def run(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def dur(p: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(p)]).decode().strip())


def skylt(ut: Path, rubrik: str, rad: str = "", farg=OK, pos: str = "ned") -> Path:
    """Genomskinlig PNG med en skylt (rubrik + rad), nere till vänster eller uppe till vänster."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f1, f2 = font("sans", 600, 44), font("sans", 400, 32)
    b1 = d.textbbox((0, 0), rubrik, font=f1)
    b2 = d.textbbox((0, 0), rad, font=f2) if rad else (0, 0, 0, 0)
    bw = max(b1[2], b2[2]) + 72
    bh = 44 + (b1[3] - b1[1]) + (20 + b2[3] - b2[1] if rad else 0) + 36
    x, y = 64, (H - bh - 72 if pos == "ned" else 64)
    d.rounded_rectangle((x, y, x + bw, y + bh), 14, fill=(14, 17, 19, 236))
    d.rectangle((x, y, x + 8, y + bh), fill=farg + (255,))
    d.text((x + 40, y + 28), rubrik, font=f1, fill=TEXT)
    if rad:
        d.text((x + 40, y + 28 + (b1[3] - b1[1]) + 24), rad, font=f2, fill=TEXT2)
    im.save(ut)
    return ut


def kort(ut: Path, rader: list[tuple[str, str, int, tuple]]) -> Path:
    """Helt kort på mörk bakgrund. rader: (text, typsnitt, storlek, färg), centrerat."""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    fs = [font(t.split("-")[0], int(t.split("-")[1]), s) for _, t, s, _ in rader]
    hojd = [d.textbbox((0, 0), txt, font=f)[3] for (txt, *_), f in zip(rader, fs)]
    y = (H - sum(hojd) - 36 * (len(rader) - 1)) // 2
    for (txt, _, _, farg), f, h in zip(rader, fs, hojd):
        bw = d.textbbox((0, 0), txt, font=f)[2]
        d.text(((W - bw) // 2, y), txt, font=f, fill=farg)
        y += h + 36
    im.save(ut)
    return ut


VIDEO = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS)]
LJUD = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def rost(n: Path, start: float, total: float) -> str:
    """Filterkedja: rösten normaliseras till -19 LUFS (som demon) och läggs in vid start, utfylld till total."""
    ms = int(start * 1000)
    return (f"loudnorm=I=-19:TP=-2:LRA=7,aresample=48000,aformat=channel_layouts=stereo,"
            f"adelay={ms}|{ms},apad,atrim=0:{total:.3f}")


def main() -> None:
    tmp, nar = Path(sys.argv[1]), Path(sys.argv[2])
    tmp.mkdir(parents=True, exist_ok=True)
    delar: list[Path] = []

    # A: animationen, hålls ut så länge rösten pratar
    a_len = round(dur(nar / "n1.wav") + 1.2, 2)
    s = skylt(tmp / "sA.png", "Kropp64", "Sensorpanelen för din viktigaste rigg: dig själv.", pos="upp")
    anim = REPO / "docs/render/kropp64-animation.mp4"
    run("-i", str(anim), "-loop", "1", "-i", str(s), "-i", str(nar / "n1.wav"), "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration=5,trim=0:{a_len},setpts=PTS-STARTPTS[v0];"
        f"[1:v]format=rgba,fade=in:st=1.0:d=0.6:alpha=1[s];[v0][s]overlay=shortest=1,trim=0:{a_len}[v];"
        f"[2:a]{rost(None, 0.3, a_len)}[a]", "-map", "[v]", "-map", "[a]", "-t", str(a_len),
        *VIDEO, *LJUD, str(tmp / "A.mp4"))
    delar.append(tmp / "A.mp4")

    # B: sensorpanelen och pulsen vid datorn, långsam zoom
    b_len = round(dur(nar / "n2.wav") + 1.3, 2)
    half = b_len / 2
    bilder = [REPO / "docs/bidrag-bilder/04-oversikt.png", REPO / "docs/bidrag-bilder/05-puls-vid-datorn.png"]
    fr = int(half * FPS)
    zoom = (f"scale=3840:2160,zoompan=z='1+0.06*on/{fr}':x='0':y='0'"
            f":d={fr}:s={W}x{H}:fps={FPS}")
    run("-loop", "1", "-i", str(bilder[0]), "-loop", "1", "-i", str(bilder[1]), "-i", str(nar / "n2.wav"),
        "-filter_complex",
        f"[0:v]format=rgb24,{zoom},trim=0:{half:.3f}[b0];[1:v]format=rgb24,{zoom},trim=0:{half:.3f}[b1];"
        f"[b0][b1]xfade=transition=fade:duration=0.5:offset={half - 0.5:.3f},trim=0:{b_len}[v];"
        f"[2:a]{rost(None, 0.3, b_len)}[a]", "-map", "[v]", "-map", "[a]", "-t", str(b_len),
        *VIDEO, *LJUD, str(tmp / "B.mp4"))
    delar.append(tmp / "B.mp4")

    # C: riggen
    rigg = REPO / "docs/video/riggen-demo-1920x1080.mp4"
    c_len = round(dur(rigg), 2)
    s = skylt(tmp / "sC.png", "Riggen", "Pulsen styr fläktar och kylflänsar. Demo, syntetisk data.", pos="upp")
    run("-i", str(rigg), "-loop", "1", "-i", str(s), "-i", str(nar / "n3.wav"), "-filter_complex",
        f"[1:v]format=rgba,fade=in:st=0.3:d=0.5:alpha=1,fade=out:st=5:d=0.5:alpha=1[s];"
        f"[0:v][s]overlay=shortest=1[v];[2:a]{rost(None, 0.8, c_len)}[a]",
        "-map", "[v]", "-map", "[a]", "-t", str(c_len), *VIDEO, *LJUD, str(tmp / "C.mp4"))
    delar.append(tmp / "C.mp4")

    # D: mellankort
    k = kort(tmp / "kD.png", [("En tråd från larm till lösning", "sans-600", 72, TEXT),
                              ("Allt körs lokalt. Syntetisk demo, kortad från 3 min.", "sans-400", 40, TEXT2)])
    run("-loop", "1", "-i", str(k), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-filter_complex",
        "[0:v]format=yuv420p,fade=in:st=0:d=0.3,fade=out:st=2.4:d=0.4[v]", "-map", "[v]", "-map", "1:a",
        "-t", "2.8", *VIDEO, *LJUD, str(tmp / "D.mp4"))
    delar.append(tmp / "D.mp4")

    # E: demotråden, kortad, med skyltar (tider i den kortade delen)
    demo = REPO / "docs/video/kropp64-demo-1920x1080.mp4"
    klipp = [(2.0, 60.0), (121.0, 191.4)]
    skyltar = [  # (start, slut, png)
        (35.8, 44.0, skylt(tmp / "e1.png", "Trollet ifrågasätter alltid", "Djävulens advokat letar vardagliga förklaringar.", WARN)),
        (69.5, 76.5, skylt(tmp / "e2.png", "Kardiologen drar en slutsats", "utan något i datan som stöder den.", WARN)),
        (77.0, 88.0, skylt(tmp / "e3.png", "Moderatorn stryker den", "Vanlig Python, ingen AI: varje påstående måste ha en källa.", OK)),
        (112.0, 126.0, skylt(tmp / "e4.png", "Brådskan sätts av ett regelverk", "Modellen får höja, aldrig sänka. Bara en vaktregel kan ge \"kontakta vården nu\".", OK)),
    ]
    delklipp = []
    for i, (a, b) in enumerate(klipp):
        p = tmp / f"E{i}.mp4"
        run("-ss", str(a), "-to", str(b), "-i", str(demo), "-af", "afade=in:d=0.15,areverse,afade=in:d=0.15,areverse",
            *VIDEO, *LJUD, str(p))
        delklipp.append(p)
    lista = tmp / "E.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in delklipp))
    run("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(tmp / "Eraw.mp4"))
    ins, fc, prev = ["-i", str(tmp / "Eraw.mp4")], "", "0:v"
    for j, (a, b, png) in enumerate(skyltar, start=1):
        ins += ["-loop", "1", "-i", str(png)]
        fc += (f"[{j}:v]format=rgba,fade=in:st={a}:d=0.4:alpha=1,fade=out:st={b - 0.4}:d=0.4:alpha=1[s{j}];"
               f"[{prev}][s{j}]overlay=shortest=1:enable='between(t,{a},{b})'[o{j}];")
        prev = f"o{j}"
    run(*ins, "-filter_complex", fc.rstrip(";"), "-map", f"[{prev}]", "-map", "0:a", *VIDEO, "-c:a", "copy",
        str(tmp / "E.mp4"))
    delar.append(tmp / "E.mp4")

    # F: 16 GB-gränsen
    f_len = round(dur(nar / "n4.wav") + 1.4, 2)
    s = skylt(tmp / "sF.png", "36 av 36 rätt brådska", "på holdout-testfall skrivna innan de kördes (syntetisk data)", OK, pos="upp")
    run("-loop", "1", "-i", str(REPO / "docs/render/kropp64-16gb-gransen.png"), "-loop", "1", "-i", str(s),
        "-i", str(nar / "n4.wav"), "-filter_complex",
        f"[0:v]format=rgb24,scale=3840:2160,zoompan=z='1.06-0.06*on/{int(f_len * FPS)}':x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)':d={int(f_len * FPS)}:s={W}x{H}:fps={FPS}[b];"
        f"[1:v]format=rgba,fade=in:st=4.5:d=0.5:alpha=1[s];[b][s]overlay=shortest=1,trim=0:{f_len}[v];"
        f"[2:a]{rost(None, 0.3, f_len)}[a]", "-map", "[v]", "-map", "[a]", "-t", str(f_len),
        *VIDEO, *LJUD, str(tmp / "F.mp4"))
    delar.append(tmp / "F.mp4")

    # G: slutkort
    g_len = round(dur(nar / "n5.wav") + 2.6, 2)
    k = kort(tmp / "kG.png", [("Kropp64", "sans-600", 128, TEXT),
                              ("kropp64.se", "mono-500", 48, OK),
                              ("Mac mini M4 16 GB · qwen3.5:9b i Ollama · ingen hälsodata i molnet", "sans-400", 34, TEXT2)])
    run("-loop", "1", "-i", str(k), "-i", str(nar / "n5.wav"), "-filter_complex",
        f"[0:v]format=yuv420p,fade=in:st=0:d=0.5,fade=out:st={g_len - 0.8}:d=0.8[v];"
        f"[1:a]{rost(None, 0.5, g_len)}[a]", "-map", "[v]", "-map", "[a]", "-t", str(g_len),
        *VIDEO, *LJUD, str(tmp / "G.mp4"))
    delar.append(tmp / "G.mp4")

    lista = tmp / "alla.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in delar))
    ut = REPO / "docs/video/kropp64-bidrag-1920x1080.mp4"
    run("-f", "concat", "-safe", "0", "-i", str(lista), *VIDEO, *LJUD, "-movflags", "+faststart", str(ut))
    print(ut, round(dur(ut), 1), "s")


if __name__ == "__main__":
    main()
