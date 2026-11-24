#!/bin/bash
# Hjalpskript: skicka skript till Lenovon, starta Blender frikopplat, hamta resultat.
#   lenovo.sh push                      kopiera render/*.py och tex_*.png
#   lenovo.sh run <skript.py> <args..>  starta blender -b -P (frikopplat, logg i ut\<skript>.log)
#   lenovo.sh get <fjarrfil> <lokal>    hamta en fil och verifiera storleken
H=${LENOVO:?satt LENOVO=anvandare@vard for laptopen}
R='C:\Users\crick\Desktop\_lenovo\konsiliet3d'
RF=C:/Users/crick/Desktop/_lenovo/konsiliet3d
B='C:\Users\crick\Desktop\_lenovo\patches3d\blender-4.5.3-windows-x64\blender.exe'
D="$(cd "$(dirname "$0")" && pwd)"
case "$1" in
push)
  ssh $H "if not exist $R\\ut mkdir $R\\ut"
  for f in "$D"/*.py "$D"/tex_*.png; do scp -q "$f" "$H:$RF/$(basename "$f")" || exit 1; done ;;
run)
  s="$2"; shift 2; log="$R\\ut\\${s%.py}.log"
  ssh $H "powershell -NoProfile -Command \"Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd /c $B -b -P $R\\$s -- $* > $log 2>&1'; CurrentDirectory='$R'} | Select ProcessId,ReturnValue\"" ;;
get)
  scp -q "$H:$2" "$3" || exit 1
  rs=$(ssh $H "powershell -NoProfile -Command \"(Get-Item '$2').Length\"" | tr -d '\r'); ls=$(stat -f %z "$3")
  [ "$rs" = "$ls" ] && echo "ok $3 $ls" || { echo "STORLEK AVVIKER $rs $ls"; exit 1; } ;;
esac
