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

   Chromium körs headless (inga fönster) med `--mute-audio` och `--autoplay-policy=no-user-gesture-required`, och sidan öppnas med
   `?ljud=1`. Inget spelas i datorns högtalare.
3. Ljudspåret: läkarnas röster är förgenererade för demomanuset (`web/public/demo-rost/<nr>.ogg`, se
   `web/dev/rost-demo.mjs`) och byggs in i demobygget, så den publika demon kör ingen talsyntes. Under
   inspelningen loggas när varje röst börjar spela i sidan (samma klocka som screencastens tidsstämplar), och
   filerna läggs in på exakt de tiderna med ffmpeg (`adelay` + `amix`). Varje replik är normaliserad till
   -19 LUFS (hela filmen mätt till -20,3 och -20,4 LUFS integrerat), toppar under -2 dBTP. AAC 128 kbit/s i mp4, Opus i webm.

Rösterna görs med Parambe (Chatterbox Multilingual med svenska vikter) lokalt i hemnätet, klonade ur en röstbank
vars referensklipp ursprungligen gjordes med ElevenLabs (syntetiska röster, gratisplan, icke-kommersiellt).
Se RESAN.md. Ingen klippning utöver att första sekunden (sidbytet) är bortskuren.

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

## Bidragsfilmen (3 min 11 s)

| Fil | Format |
|---|---|
| `kropp64-bidrag-1920x1080.mp4` | 16:9, 30 bilder/s, H.264 crf 18, AAC 192 kbit/s, -20,0 LUFS integrerat |

Byggs av `render/slutvideo.py` av material som redan finns här: 3D-animationen, sensorpanelen och pulsen vid
datorn (docs/bidrag-bilder 04 och 05), riggen, demotråden kortad till 2-60 s och 121-191,4 s (trollet,
strykningen och lösningen är kvar), 16 GB-bilden och ett slutkort. Skyltarna ritas med PIL i IBM Plex.

Berättarrösten är Gemini TTS (rösten Sulafat), och det är systemet som pratar ("Jag är Kropp64"), inte jag.
Den normaliseras till -19 LUFS som demons röster. Allt i kontoret och riggen är syntetisk demo och märkt så.
Siffran "36 av 36 rätt brådska" är holdout-körningarna i eval/RESULTAT.md, syntetisk data.

```
python3 render/slutvideo.py <arbetsmapp> <mapp med n1.wav-n5.wav>
```
