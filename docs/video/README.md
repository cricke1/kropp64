# Demofilmer

Inspelningar av webbens demoläge (`drift/publik-demo.sh`, bygget med `KONSILIET_PUBLIK_DEMO=1`) när det spelar upp
ett helt konsilium i realtid, cirka 3 minuter. Allt i filmerna är syntetiskt: konsiliet är ett manus och bannern
"Demo - syntetisk data" syns i varje bildruta.

| Fil | Format |
|---|---|
| `konsiliet-demo-1920x1080.mp4` / `.webm` | 16:9, 30 bilder/s, H.264 respektive VP9 |
| `konsiliet-demo-1080x1920.mp4` / `.webm` | 9:16 (mobilvyn), 30 bilder/s |

Filmerna ligger inte i git (för stora). Så spelas de in igen:

1. `drift/publik-demo.sh` (startar demon på 127.0.0.1:8795).
2. Spela in med Chromiums screencast via Playwright (skarpare pixelgrafik än Playwrights inbyggda video):
   16:9 med viewport 1680x945 och skalfaktor 8/7, 9:16 med viewport 405x720 och skalfaktor 8/3.
   Bilderna sparas med tidsstämplar och sätts ihop med ffmpeg (`-f concat` med varaktighet per bild, `fps=30`).

Ingen ljudspår. Ingen klippning utöver att första sekunden (sidbytet) är bortskuren.
