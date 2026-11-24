#!/bin/bash
# Bygger landningssidan för kropp64.se till site/dist. Statiska filer, inget byggsteg i webbläsaren.
#   site/bygg.sh
# Kontorsloopen klipps ur demofilmen i docs/video (spelas in enligt docs/video/README.md).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UT="$REPO/site/dist"
rm -rf "$UT" && mkdir -p "$UT/bilder" "$UT/fonts"
cp "$REPO/site/index.html" "$REPO/site/style.css" "$UT/"
cp "$REPO/web/public/favicon.svg" "$UT/"
F="$REPO/web/node_modules/@fontsource"
cp "$F/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2" "$UT/fonts/plex-sans-400.woff2"
cp "$F/ibm-plex-sans/files/ibm-plex-sans-latin-500-normal.woff2" "$UT/fonts/plex-sans-500.woff2"
cp "$F/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff2" "$UT/fonts/plex-sans-600.woff2"
cp "$F/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2" "$UT/fonts/plex-mono-400.woff2"
cp "$REPO/docs/render/kropp64-hjalte-16x9-ren.jpg" "$UT/bilder/hjalte.jpg"
cp "$REPO/docs/bidrag-bilder/04-oversikt.png" "$UT/bilder/sensorpanelen.png"
cp "$REPO/docs/bidrag-bilder/05-puls-vid-datorn.png" "$UT/bilder/puls-vid-datorn.png"
FILM="$REPO/docs/video/kropp64-demo-1920x1080.mp4"
if [ -f "$FILM" ]; then
  # 24 sekunder runt moderatorns strykning, utan ljud, 1280 bred
  ffmpeg -y -loglevel error -ss 118 -t 24 -i "$FILM" -an -vf "scale=1280:-2:flags=lanczos" \
    -c:v libvpx-vp9 -crf 36 -b:v 0 -row-mt 1 -deadline good -cpu-used 4 "$UT/bilder/kontoret.webm"
  ffmpeg -y -loglevel error -ss 140 -i "$FILM" -frames:v 1 -vf "scale=1280:-2:flags=lanczos" -q:v 3 "$UT/bilder/kontoret.jpg"
else
  echo "Saknar $FILM, kontorsloopen hoppas över" >&2
fi
du -sh "$UT"
