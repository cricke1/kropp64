#!/bin/bash
# Bygger landningssidan för kropp64.se till site/dist. Statiska filer, inget byggsteg i webbläsaren.
#   site/bygg.sh
# Hjältebilden och värmekameran renderas med render/sajt (se render/sajt/kor.sh och post.py) och ligger
# färdiga i site/bilder. Kontorsloopen klipps ur demofilmen i docs/video (spelas in enligt docs/video/README.md).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UT="$REPO/site/dist"
rm -rf "$UT" && mkdir -p "$UT/bilder" "$UT/fonts"
cp "$REPO/site/index.html" "$REPO/site/style.css" "$REPO/site/sida.js" "$UT/"
cp "$REPO/web/public/favicon.svg" "$UT/"
cp "$REPO/site/fonts/"* "$UT/fonts/"
cp "$REPO/site/bilder/"* "$UT/bilder/"
cwebp -quiet -q 82 "$REPO/docs/bidrag-bilder/04-oversikt.png" -o "$UT/bilder/sensorpanelen.webp"
cwebp -quiet -q 82 "$REPO/docs/bidrag-bilder/05-puls-vid-datorn.png" -o "$UT/bilder/puls-vid-datorn.webp"
FILM="$REPO/docs/video/kropp64-demo-1920x1080.mp4"
if [ -f "$FILM" ]; then
  # 24 sekunder runt moderatorns strykning, utan ljud, 1280 bred. Laddas först när den syns.
  ffmpeg -y -loglevel error -ss 118 -t 24 -i "$FILM" -an -vf "scale=1280:-2:flags=lanczos" \
    -c:v libvpx-vp9 -crf 36 -b:v 0 -row-mt 1 -deadline good -cpu-used 4 "$UT/bilder/kontoret.webm"
  ffmpeg -y -loglevel error -ss 140 -i "$FILM" -frames:v 1 -vf "scale=1280:-2:flags=lanczos" "$UT/bilder/kontoret.png"
  cwebp -quiet -q 78 "$UT/bilder/kontoret.png" -o "$UT/bilder/kontoret.webp" && rm "$UT/bilder/kontoret.png"
else
  echo "Saknar $FILM, kontorsloopen hoppas över" >&2
fi
# Riggvyn (three.js) som laddas på begäran: web/src/rigg/sajt.ts -> dist/rigg/rigg.js, plus modellen och stillbilden
(cd "$REPO/web" && UT="$UT/rigg" npx vite build --config vite.sajt.config.ts --logLevel error)
cp "$REPO/web/public/rigg/kropp64-rigg.glb" "$REPO/web/public/rigg/rigg-still.webp" "$UT/rigg/"
du -sh "$UT"
