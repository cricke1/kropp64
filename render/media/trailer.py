#!/usr/bin/env python3
"""Trailern (16:9, 55 s), klippt till musiken i musik.py.

Formspråket kommer ur projektets egen värld, PC-hårdvara: en POST-skärm som skrivs ut medan hjärtat slår,
RivaTuner-OSD i stället för textskyltar, en blå "PC Health Status" för siffrorna och en BIOS-dialog som
slutkort (retro.py). Materialet är eget: 3D-animationen, riktiga skärmfilmer från mobilen, demofilmen ur
webben och riggen.

  .venv/bin/python trailer.py
Utdata: docs/video/kropp64-trailer-1920x1080.mp4 (ligger inte i git).
"""
import subprocess, tempfile
from pathlib import Path
from PIL import Image
import retro as R
from text import REPO

W, H, FPS = 1920, 1080, 30
MEDIA = REPO / "render/media"
DEMO = REPO / "docs/video/kropp64-demo-1920x1080.mp4"
ANIM = REPO / "docs/render/kropp64-animation.mp4"
RIGG = REPO / "docs/video/riggen-demo-1920x1080.mp4"
MOBIL = MEDIA / "skarm/mobil-film.mp4"
MUSIK = MEDIA / "ut/musik.wav"
UT = REPO / "docs/video/kropp64-trailer-1920x1080.mp4"
VIDEO = ["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]

POST = [("Kropp64 Modular BIOS v0.64, An Energy Star Ally", R.VIT), ("Copyright (C) 2026, Kropp64 Software, Inc.", R.GRA), ("", R.GRA),
        ("CPU     : Mänskligt hjärta, 1 kärna @ ?? BPM", R.GRA), ("Memory  : 16384 MB (Mac mini M4) ........ OK", R.GRA),
        ("Sensors : Pixel Watch 5 .................. Found", R.GRA), ("Journal : 1177 via BankID ................ Found", R.GRA),
        ("AI Team : qwen3.5:9b, 6 agenter .......... Local", R.GRA), ("", R.GRA),
        ("WARNING: Vilopuls ej övervakad på 18 år.", R.ROD), ("", R.GRA), ("Press DEL to enter SETUP", R.VIT)]


def run(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def tom(farg=(0, 0, 0)):
    return Image.new("RGB", (W, H), farg)


def main():
    global MOBIL
    with tempfile.TemporaryDirectory() as tt:
        t = Path(tt); delar = []
        # Skärminspelningen har variabel bildfrekvens; konstant 30 fps först, annars blir telefonen tom.
        run("-i", str(MOBIL), "-vf", "fps=30", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(t / "mobil30.mp4"))
        MOBIL = t / "mobil30.mp4"

        def bildsekvens(namn, bilder):
            d = t / namn; d.mkdir()
            for i, im in enumerate(bilder):
                im.save(d / f"{i:04d}.png")
            run("-framerate", str(FPS), "-i", str(d / "%04d.png"), *VIDEO, str(t / f"{namn}.mp4"))
            delar.append(t / f"{namn}.mp4")

        def stillbild(namn, im, langd, zoom=0.0004):
            p = t / f"{namn}.png"; im.save(p)
            run("-loop", "1", "-i", str(p), "-vf", f"zoompan=z='1+{zoom}*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(langd * FPS)}:s={W}x{H}:fps={FPS}",
                "-t", str(langd), *VIDEO, str(t / f"{namn}.mp4"))
            delar.append(t / f"{namn}.mp4")

        def osd_klipp(namn, kalla, start, langd, osd_rader, crop=None, osd_y=34, neighbor=False):
            R.osd(Image.new("RGBA", (W, H), (0, 0, 0, 0)), osd_rader, y=osd_y).save(t / f"{namn}_osd.png")
            vf = f"crop={crop},scale={W}:{H}:flags={'neighbor' if neighbor else 'lanczos'}" if crop else f"scale={W}:{H}"
            run("-ss", str(start), "-t", str(langd), "-i", str(kalla), "-loop", "1", "-i", str(t / f"{namn}_osd.png"),
                "-filter_complex", f"[0:v]{vf}[v];[v][1:v]overlay=shortest=1", *VIDEO, str(t / f"{namn}.mp4"))
            delar.append(t / f"{namn}.mp4")

        mask, ram = R.telefonram()
        mask.save(t / "mask.png"); ram.save(t / "ram.png")

        def telefon(namn, start, langd, osd_rader):
            R.osd(tom(), osd_rader, x=120, y=400, size=50).save(t / f"{namn}_bg.png")
            run("-i", str(t / f"{namn}_bg.png"), "-ss", str(start), "-t", str(langd), "-i", str(MOBIL), "-i", str(t / "mask.png"),
                "-i", str(t / "ram.png"), "-filter_complex",
                "[1:v]scale=440:1027,format=rgba[sk];[2:v]format=gray[m];[sk][m]alphamerge[skr];"
                "[0:v][3:v]overlay=1250:-6[b];[b][skr]overlay=1320:64",
                "-t", str(langd), *VIDEO, str(t / f"{namn}.mp4"))
            delar.append(t / f"{namn}.mp4")

        # 0-7 s: POST-skärmen skrivs ut, markören blinkar på sista raden
        tecken = sum(len(r) + 1 for r, _ in POST)
        bildsekvens("a", [R.post(POST, n_tecken=int(min(tecken, i / (5.8 * FPS) * tecken)), size=46,
                                 cursor=(i // 8) % 2 == 0 or i < 5.8 * FPS) for i in range(int(7.0 * FPS))])

        # 7-10 s: 3D-animationen med OSD
        osd_klipp("b1", ANIM, 3.0, 3.0, [("KROPP64", "HWiNFO för kroppen", R.OSD_GUL), ("SERVER", "Mac mini M4, 16 GB", None),
                                           ("MOLN", "0 byte hälsodata", R.GRON)])

        # 10-17 s: riktiga mobilskärmar på svart, OSD till vänster
        telefon("c1", 14.6, 3.4, [("SENSORPANEL", "live", R.GRON), ("PULS", "från Pixel Watch 5", None), ("HRV, SÖMN", "Health Connect", None)])
        telefon("c2", 0.6, 3.6, [("FRÅGA", "Ska jag träna i dag?", R.OSD_GUL), ("SVAR", "direkt, regler i koden", None),
                                 ("GISSNING", "ingen", R.GRON)])

        # 17-31 s: pixelkontoret, OSD längst ner till vänster så att pratbubblorna syns
        KONTOR = "828:466:332:225"
        osd_klipp("d1", DEMO, 7.0, 4.6, [("VAKT", "vilopulsen över baslinjen", R.OSD_GUL), ("TRÅD", "#1 startad", R.GRON),
                                           ("TEAM", "6 agenter, lokalt", None)], crop=KONTOR, neighbor=True, osd_y=830)
        osd_klipp("d2", DEMO, 38.6, 4.4, [("TROLLET", "\"har du dragit åt armbandet?\"", R.OSD_GUL),
                                            ("ROLL", "djävulens advokat", None)], crop=KONTOR, neighbor=True, osd_y=880)
        osd_klipp("d3", DEMO, 133.2, 5.0, [("KARDIOLOG", "\"hjärtmuskelinflammation\"", R.OSD_GUL),
                                             ("KÄLLA", "???", R.ROD)], crop=KONTOR, neighbor=True, osd_y=880)

        # 31 s: droppet
        stillbild("e1", R.bios_dialog("PÅSTÅENDE STRUKET: INGEN KÄLLA", "",
                                      under="Moderatorn är vanlig Python. Ingen modell kan prata sig förbi den."), 2.4, zoom=0.0012)
        osd_klipp("d4", DEMO, 140.2, 2.8, [("MODERATOR", "STRUKET", R.ROD), ("SKÄL", "inget i datan pekar dit", None)],
                  crop="828:466:332:172", neighbor=True, osd_y=880)
        rader = [("Rätt brådska, holdout", "36/36", R.GRON), ("Godtagbar brådska", "56% -> 100%", R.VIT),
                 ("Tid per tråd", "226 s -> 118 s", R.VIT), ("Missade akuta fall", "4 -> 0", R.VIT),
                 ("Minne, qwen3.5:9b", "9,1 / 16 GB", R.GUL), ("RTX 5050 mot M4", "56 s / 126 s", R.CYAN)]
        bildsekvens("e2", [R.bios_halsa(rader[:min(len(rader), 1 + i // 12)], markerad=min(len(rader), 1 + i // 12) - 1)
                           for i in range(int(5.0 * FPS))])
        osd_klipp("f1", RIGG, 5.0, 3.4, [("RIGGEN", "kroppen som PC-chassi", R.OSD_GUL), ("FLÄKTAR", "styrs av pulsen", None)], osd_y=200)
        telefon("f2", 5.6, 2.4, [("1177", "BankID, ett tryck", R.OSD_GUL), ("JOURNAL", "läses på Mac minin", None), ("MOLN", "0 byte", R.GRON)])

        # 45-55 s: hjärtat saktar in
        g = Image.open(REPO / "docs/render/kropp64-16gb-gransen.png").convert("RGB").resize((W, H))
        stillbild("g1", R.osd(g, [("RAM", "16 GB räcker. Precis.", R.OSD_GUL), ("MED 128 GB", "hela teamet parallellt", R.GRON)],
                              x=80, y=70, size=48), 3.0, zoom=0.0008)
        bildsekvens("h1", [R.bios_dialog("RÖSTA PÅ KROPP64 (Y/N)?", "Y" if i > 24 else ("_" if (i // 8) % 2 == 0 else " "),
                                         under="projekt.sweclockers.com/asus  -  1-13 december  -  kropp64.se")
                           for i in range(int(5.0 * FPS))])

        lista = t / "lista.txt"; lista.write_text("".join(f"file '{p}'\n" for p in delar))
        run("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(t / "bild.mp4"))
        langd = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(t / "bild.mp4")]))
        run("-i", str(t / "bild.mp4"), "-i", str(MUSIK), "-filter_complex",
            f"[1:a]atrim=0:{langd},afade=out:st={langd - 1.2}:d=1.2,loudnorm=I=-14:TP=-1.5[a]", "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(UT))
        print(UT, round(langd, 1), "s")


if __name__ == "__main__":
    main()
