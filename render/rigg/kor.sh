#!/bin/bash
# Bygger riggen på Lenovon och hämtar resultatet till web/public/rigg/.
#   LENOVO=anvandare@vard render/rigg/kor.sh [bredd hojd samples]
# Mellanfiler (blend, AO-bilder, PNG) stannar på Lenovon i konsiliet3d\rigg\ut.
set -euo pipefail
H=${LENOVO:?satt LENOVO=anvandare@vard for laptopen}
R='C:\Users\crick\Desktop\_lenovo\konsiliet3d\rigg'
RF=C:/Users/crick/Desktop/_lenovo/konsiliet3d/rigg
B='C:\Users\crick\Desktop\_lenovo\patches3d\blender-4.5.3-windows-x64\blender.exe'
D="$(cd "$(dirname "$0")" && pwd)"
WEB="$D/../../web/public/rigg"
W=${1:-1600}; HH=${2:-1000}; S=${3:-384}

ssh "$H" "if not exist $R\\ut mkdir $R\\ut" >/dev/null
scp -q "$D/rigg.py" "$H:$RF/rigg.py"
ssh "$H" "del /q $R\\ut\\klar.txt $R\\ut\\kropp64-rigg.glb 2>nul" || true
t0=$(date +%s)
ssh "$H" "powershell -NoProfile -Command \"Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd /c $B -b -P $R\\rigg.py -- $R\\ut $W $HH $S > $R\\ut\\rigg.log 2>&1'; CurrentDirectory='$R'} | Select ProcessId,ReturnValue\""
until ssh "$H" "if exist $R\\ut\\klar.txt (echo KLAR) else (findstr /c:Traceback /c:\"Error:\" $R\\ut\\rigg.log)" 2>/dev/null | grep -qE "KLAR|Error|Traceback"; do sleep 5; done
ssh "$H" "type $R\\ut\\rigg.log" | grep -E "RIGG|Traceback|Error|File \"" | tail -20
echo "Total tid: $(( $(date +%s) - t0 )) s"
ssh "$H" "if exist $R\\ut\\klar.txt (exit 0) else (exit 1)" || { echo "Bygget misslyckades" >&2; exit 1; }
mkdir -p "$WEB"
scp -q "$H:$RF/ut/kropp64-rigg.glb" "$WEB/kropp64-rigg.glb"
scp -q "$H:$RF/ut/rigg-still.png" "$D/rigg-still.png.tmp"
magick "$D/rigg-still.png.tmp" -quality 84 "$WEB/rigg-still.webp" && rm "$D/rigg-still.png.tmp"
ls -l "$WEB"
