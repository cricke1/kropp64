#!/bin/bash
# Renderar sajtens kretskortsbild pa Lenovon. Mellanfiler stannar pa Lenovon, bara slutbilden hamtas.
#   render/sajt/kor.sh <bredd> <hojd> <samples> <namn> [variant]     (LOKAL=mapp att hamta till)
# Kraver LENOVO=anvandare@vard. Texturerna ritas forst med texturer.py.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"; L=${LOKAL:?satt LOKAL}; H=${LENOVO:?satt LENOVO}
RF=C:/Users/crick/Desktop/_lenovo/konsiliet3d; R='C:\Users\crick\Desktop\_lenovo\konsiliet3d'
w=$1; h=$2; s=$3; n=$4; v=${5:-slut}
python3 "$D/texturer.py" "$L/tex" >/dev/null
for f in "$D/../common.py" "$D/pcb_layout.py" "$D/kretskort.py" "$L/tex/pcb.png" "$L/tex/etch.png"; do scp -q "$f" "$H:$RF/$(basename "$f")"; done
ssh "$H" "del /q $R\\ut\\$n.png $R\\ut\\$n.png.klar $R\\ut\\$n.png.tid.txt $R\\ut\\${n}_heat*.exr 2>nul" || true
"$D/../lenovo.sh" run kretskort.py $w $h "$R\\ut\\$n.png" $s $v ${EXPO:--3.2} ${FSTOP:-9} >/dev/null
until ssh "$H" "if exist $R\\ut\\$n.png.klar (echo KLAR) else (findstr /i /c:Traceback /c:\"Error:\" $R\\ut\\kretskort.log)" 2>/dev/null | grep -qiE "KLAR|error|traceback"; do sleep 5; done
ssh "$H" "type $R\\ut\\kretskort.log" | grep -iE "Traceback|Error|File \"|RENDERTID|ANKARE|HEAT" | tail -12
scp -q "$H:$RF/ut/$n.png" "$L/$n.png"
scp -q "$H:$RF/ut/${n}_ankare.json" "$L/" || true
scp -q "$H:$RF/ut/${n}_heat.pgm" "$L/${n}_heat.pgm" || true
ls -la "$L/$n"*
