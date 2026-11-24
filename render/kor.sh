#!/bin/bash
# kor.sh <skript.py> <namn> <args efter ut-filen...>   -> renderar ut\<namn>.png, vantar, hamtar till scratch
# argument: bredd hojd [samples] [variant]
s=$1; n=$2; shift 2; w=$1; h=$2; shift 2
D="$(cd "$(dirname "$0")" && pwd)"; L=${LOKAL:?satt LOKAL=mapp for hamtade bilder}
R='C:\Users\crick\Desktop\_lenovo\konsiliet3d\ut'
ssh "$LENOVO" "del /q $R\\$n.png.tid.txt $R\\$n.png 2>nul"; "$D/lenovo.sh" run "$s" $w $h "$R\\$n.png" "$@" >/dev/null
until ssh "$LENOVO" "if exist $R\\$n.png.tid.txt (echo KLAR) else (findstr /i /c:Traceback /c:\"Error:\" $R\\${s%.py}.log)" 2>/dev/null | grep -qiE "KLAR|error|traceback"; do sleep 4; done
ssh "$LENOVO" "type $R\\${s%.py}.log" | grep -iE "Traceback|Error|File \"|RENDERTID" | grep -v "^Fra" | tail -12
"$D/lenovo.sh" get "C:/Users/crick/Desktop/_lenovo/konsiliet3d/ut/$n.png" "$L/$n.png" >/dev/null && magick "$L/$n.png" -depth 8 "$L/$n.png"
ls "$D"/ut/*_ankare.json >/dev/null 2>&1; scp -q "$LENOVO:C:/Users/crick/Desktop/_lenovo/konsiliet3d/ut/${n}_ankare.json" "$L/" 2>/dev/null; true
