# Demofilmer

Inspelningar av webbens demoläge (`drift/publik-demo.sh`, bygget med `KONSILIET_PUBLIK_DEMO=1`) när det spelar upp
ett helt konsilium i realtid, cirka 3 minuter. Allt i filmerna är syntetiskt: konsiliet är ett manus och bannern
"Demo - syntetisk data" syns i varje bildruta.

| Fil | Format |
|---|---|
| `kropp64-demo-1920x1080.mp4` / `.webm` | 16:9, 30 bilder/s, H.264 respektive VP9 |
| `kropp64-demo-1080x1920.mp4` / `.webm` | 9:16 (mobilvyn), 30 bilder/s |

Filmerna ligger inte i git (för stora). Så spelas de in igen:

1. `drift/publik-demo.sh` (startar demon på 127.0.0.1:8795).
2. Spela in med Chromiums screencast via Playwright (skarpare pixelgrafik än Playwrights inbyggda video):
   16:9 med viewport 1680x945 och skalfaktor 8/7, 9:16 med viewport 405x720 och skalfaktor 8/3.
   Bilderna sparas med tidsstämplar och sätts ihop med ffmpeg (`-f concat` med varaktighet per bild, `fps=30`).

Ingen ljudspår. Ingen klippning utöver att första sekunden (sidbytet) är bortskuren.

## Riggen (14 s)

| Fil | Format |
|---|---|
| `riggen-demo-1920x1080.mp4` / `.webm` | 16:9, 30 bilder/s, H.264 (crf 18) respektive VP9, 14 s, inget ljud |

Riggvyn i demobygget när pulsen stiger i vila (64 till 96 BPM), kylflänsarna går mot varmt och kameran glider
in mot processorn när en tråd startar om pulsen. Allt är syntetiskt: banner överst och "Demo - syntetisk data" i
riggen. Så spelas den in igen:

1. Bygg demon (`KONSILIET_PUBLIK_DEMO=1 npx vite build --outDir <mapp>`) och servera mappen statiskt.
2. Öppna `#/riggen?capture=1&demostart=4` med Playwright (headless Chromium, `--use-angle=metal`), viewport
   1680x945 med skalfaktor 8/7. I inspelningsläget har riggen ingen egen bildloop: skriptet anropar
   `window.__rigg.stega(1, 1/30)` och tar en skärmbild per steg, så filmen blir exakt 30 bilder/s oavsett
   hur snabb datorn är.
3. `ffmpeg -framerate 30 -i f%04d.jpg -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart` (och VP9 för webm).
