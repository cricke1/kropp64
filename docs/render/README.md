# Renderingar

3D-bilder för bidraget, gjorda i Blender 4.5.3 (Cycles, OptiX, GPU-denoising) på laptopen "Lenovo"
med RTX 5050 8 GB. Scenerna är Python-skript i `render/` och kan renderas om. Etiketterna läggs på
efteråt med PIL och IBM Plex Sans/Mono, samma typsnitt som webben.

| Fil | Vad | Rendertid på RTX 5050 |
|---|---|---|
| `kropp64-hjalte-16x9.png` | Hjältebild 1920x1080 med ordmärke | 55,1 s (512 sampel, adaptiv) |
| `kropp64-hjalte-16x9-ren.jpg` | Samma utan text | |
| `kropp64-hjalte-4x5.png` | Hjältebild 1080x1350 med ordmärke | 44,6 s |
| `kropp64-hjalte-4x5-ren.jpg` | Samma utan text | |
| `kropp64-dataflode.png` | Isometrisk bild av dataflödet, 1920x1080 | 30,4 s |
| `kropp64-16gb-gransen.png` | "Rigg nr 2 är också på gränsen", 1920x1080 | 47,9 s |
| `kropp64-animation.mp4` | 8 s, 30 bilder/s, 1920x1080, H.264 yuv420p | 240 bilder på 61 min (snitt 15,3 s, 8,9-39,7 s per bild, 96 sampel) |

Mac minin är modellerad efter måtten på M4-modellen från 2024: 127 x 127 x 50 mm, två USB-C och
hörlursuttag fram, statuslampa, indragen fot. Klockan är en Pixel Watch 3 (41 mm) och telefonen har
Pixel-mått. Insidan i 16 GB-bilden är en illustration, inte en exakt kopia av Apples kretskort.

**Skärmarna i hjältebilden och dataflödet är en illustration med exempelvärden** (Klockfrekvens 67 BPM,
Headroom 72 och tabellen), ritade av `render/skarmar.py` i appens färger. De är inte uppmätt data.

Siffrorna i 16 GB-bilden: 14,7 GB och 9,1 GB är uppmätta på Mac minin (se RESAN.md).
Qwen3.8-27B: 17,7 GB (17 741 872 154 byte, varav vikterna 16,8 GB) enligt modellens manifest i Ollamas register, sparat i `bench/resultat/qwen3.8-27b-manifest.json` (hämtat 2026-11-25). Det är bara filen; kontext och operativsystem kommer ovanpå. Modellen har inte laddats ner eller körts här, eftersom den inte får plats i 16 GB.

## Rendera om

```
export LENOVO=anvandare@laptop LOKAL=/tmp/renders   # ssh-mål och mapp för hämtade bilder
render/lenovo.sh push                       # kopiera skript och texturer till Lenovon
render/kor.sh hero.py hero_bred 1920 1080 512 bred
render/kor.sh hero.py hero_hog 1080 1350 512 hog
render/kor.sh flow.py flow 1920 1080 512
render/kor.sh limit.py limit 1920 1080 512
render/lenovo.sh run anim.py 1920 1080 'C:\...\ut\anim' 128
python3 render/post_hero.py / post_flow.py / post_limit.py   # etiketter
```
