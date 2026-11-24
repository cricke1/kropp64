# Utvärdering av konsiliet

Genereras av `eval/rapport.py`. 15 scenarier med syntetisk data och känt facit (se `eval/scenarier.py`).
Brådska godtagbar = inom facits godtagbara nivåer. Täckning = andel måste-fynd i slutbedömningen.
Förbjudna = påståenden som inte får göras (utan negation). Strykandel = granskarens strykningar / specialistpåståenden.
Overifierade = siffror i slutbedömningens egen text som inte finns i någon hämtad källa.
Baslinjefel = meningar som kallar en siffra baslinje fast den inte är ett baslinjevärde.

Mac mini M4 16 GB, Ollama, en förfrågan i taget.

| Variant | n | Brådska godtagbar | Exakt | Över/under | Täckning | Förbjudna | Strykandel | Belagda/möte | Overifierade | Baslinjefel | Sek median (max) | Prompt-/ut-tokens | Domare |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-24 baslinje | 15 | 40% | 33% | 3/6 | 64% | 0 | 11% | 6.5 | 3 | 0 | 300 (481) | 22474/4300 | - |
| 2026-11-24 v2-hybrid | 15 | 100% | 87% | 0/0 | 78% | 0 | 26% | 7.8 | 0 | 0 | 138 (157) | 19873/2430 | - |
| 2026-11-24 v3-hybrid | 15 | 100% | 87% | 0/0 | 76% | 0 | 19% | 4.5 | 0 | 1 | 117 (129) | 18106/1760 | - |
| 2026-11-24 v3-fri | 15 | 100% | 87% | 0/0 | 79% | 1 | 14% | 5.3 | 2 | 2 | 121 (142) | 19270/1894 | - |
| 2026-11-24 v3-regel | 15 | 100% | 87% | 0/0 | 84% | 0 | 24% | 4.8 | 0 | 0 | 116 (151) | 19030/1844 | - |
| 2026-11-24 v3-utan-diskussion | 15 | 100% | 87% | 0/0 | 77% | 0 | 17% | 5.1 | 2 | 1 | 108 (140) | 16163/1614 | - |

## Varianter

- **2026-11-24 baslinje**: Pipelinen som den var (commit bf2001e): qwen3.5:9b, specialister med verktygsloop, fri brådska 
- **2026-11-24 v2-hybrid**: Faktablad + regelram (hybrid: teamet får flytta brådskan ett steg), diskussion, inga extra verktygsrundor 
- **2026-11-24 v3-hybrid**: v2 + granskarfixar (fältnamn, tusental, intervall, tecken), F:tolkning som källa, kortare svar, helst 2 specialister 
- **2026-11-24 v3-fri**: v3, teamet väljer brådska fritt (larmspärr kvar) `KONSILIET_LAGE_BRADSKA=fri`
- **2026-11-24 v3-regel**: v3, brådskan = regelverket `KONSILIET_LAGE_BRADSKA=regel`
- **2026-11-24 v3-utan-diskussion**: v3 utan replikrunda mot advokaten `KONSILIET_LAGE_DISKUSSION=0`

## Per scenario (brådska, täckning)

| Scenario | Facit | baslinje | v2-hybrid | v3-hybrid | v3-fri | v3-regel | v3-utan-diskussion |
|---|---|---|---|---|---|---|---|
| akut_takykardi | kontakta_vard_nu | FEL ingen 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% |
| traning_puls | ingen | ok ingen 100% | ok ingen 33% | ok ingen 33% | ok ingen 67% | ok ingen 67% | ok ingen 33% |
| sensorspikar | ingen | FEL ta_upp_med_varden 50% | ok ingen 50% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% |
| klocka_los | bevaka | FEL kontakta_vard_nu 50% | ok bevaka 0% | ok bevaka 50% | ok bevaka 0% | ok bevaka 50% | ok bevaka 100% |
| forkylning | bevaka | FEL ingen 50% | ok bevaka 100% | ok bevaka 75% | ok bevaka 50% | ok bevaka 75% | ok bevaka 50% |
| sent_spelande | bevaka | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% |
| spo2_dippar | ta_upp_med_varden | FEL ingen 67% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% |
| aktiv_vs_stilla | ingen | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 67% |
| allt_normalt | ingen | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% |
| trott_fraga | ingen | FEL kontakta_vard_nu 0% | ok bevaka 100% | ok bevaka 67% | ok bevaka 67% | ok bevaka 67% | ok bevaka 67% |
| lagt_ferritin | ta_upp_med_varden | FEL ingen 25% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 75% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% |
| motstridigt | bevaka | ok bevaka 33% | ok bevaka 33% | ok bevaka 33% | ok bevaka 33% | ok bevaka 67% | ok bevaka 33% |
| spo2_akut | kontakta_vard_nu | FEL bevaka 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% |
| aterkommande_hopp | ta_upp_med_varden | FEL bevaka 50% | ok kontakta_vard_nu 50% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 75% | ok kontakta_vard_nu 75% |
| stress_projekt | bevaka | ok ingen 100% | ok bevaka 100% | ok bevaka 67% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% |
| h_natt_takykardi | kontakta_vard_nu | - | - | - | - | - | - |
| h_cykling | ingen | - | - | - | - | - | - |
| h_anemi | ta_upp_med_varden | - | - | - | - | - | - |
| h_lag_nattpuls | ingen | - | - | - | - | - | - |
| h_enstaka_syrefall | ingen | - | - | - | - | - | - |
