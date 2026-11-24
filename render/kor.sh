#!/bin/bash
# kor.sh <skript.py> <namn> <args efter ut-filen...>   -> renderar ut\<namn>.png, vantar, hamtar till scratch
# argument: bredd hojd [samples] [variant]
s=$1; n=$2; shift 2; w=$1; h=$2; shift 2
D="$(cd "$(dirname "$0")" && pwd)"; L=${LOKAL:-/private/tmp/claude-501/-Users-sture-Desktop-claude/b2af5bad-3b8f-4ad8-b8cd-b4b27f3bd1df/scratchpad/r}
R='C:\Users\crick\Desktop\_lenovo\konsiliet3d\ut'
ssh crick@100.110.236.58 "del /q $R\\$n.png.tid.txt $R\\$n.png 2>nul"; "$D/lenovo.sh" run "$s" $w $h "$R\\$n.png" "$@" >/dev/null
until ssh crick@100.110.236.58 "if exist $R\\$n.png.tid.txt (echo KLAR) else (findstr /i /c:Traceback /c:\"Error:\" $R\\${s%.py}.log)" 2>/dev/null | grep -qiE "KLAR|error|traceback"; do sleep 4; done
ssh crick@100.110.236.58 "type $R\\${s%.py}.log" | grep -iE "Traceback|Error|File \"|RENDERTID" | grep -v "^Fra" | tail -12
"$D/lenovo.sh" get "C:/Users/crick/Desktop/_lenovo/konsiliet3d/ut/$n.png" "$L/$n.png" >/dev/null && magick "$L/$n.png" -depth 8 "$L/$n.png"
ls "$D"/ut/*_ankare.json >/dev/null 2>&1; scp -q "crick@100.110.236.58:C:/Users/crick/Desktop/_lenovo/konsiliet3d/ut/${n}_ankare.json" "$L/" 2>/dev/null; true
