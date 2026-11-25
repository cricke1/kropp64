# Utvärdering av konsiliet

Genereras av `eval/rapport.py`. 15 scenarier med syntetisk data och känt facit (se `eval/scenarier.py`).
Brådska godtagbar = inom facits godtagbara nivåer. Täckning = andel måste-fynd i slutbedömningen.
Förbjudna = påståenden som inte får göras (utan negation). Strykandel = granskarens strykningar / specialistpåståenden.
Overifierade = siffror i slutbedömningens egen text som inte finns i någon hämtad källa.
Baslinjefel = meningar som kallar en siffra baslinje fast den inte är ett baslinjevärde.

Mac mini M4 16 GB, Ollama, en förfrågan i taget.

| Variant | n | Brådska godtagbar | Exakt | Över/under | Täckning | Förbjudna | Strykandel | Belagda/möte | Overifierade | Baslinjefel | Sek median (max) | Prompt-/ut-tokens | Domare |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-24 baslinje | 16 | 56% | 38% | 3/4 | 57% | 0 | 14% | 6.8 | 4 | 0 | 290 (382) | 26438/4530 | - |
| 2026-11-24 v2-hybrid | 15 | 100% | 87% | 0/0 | 78% | 0 | 26% | 7.8 | 0 | 0 | 138 (157) | 19873/2430 | - |
| 2026-11-24 v3-fri | 15 | 100% | 87% | 0/0 | 79% | 1 | 14% | 5.3 | 0 | 2 | 121 (142) | 19270/1894 | - |
| 2026-11-24 v3-hybrid | 15 | 100% | 87% | 0/0 | 76% | 0 | 19% | 4.5 | 0 | 1 | 117 (129) | 18106/1760 | - |
| 2026-11-24 v3-medgemma | 15 | 100% | 80% | 0/0 | 76% | 0 | 26% | 4.7 | 1 | 0 | 128 (165) | 20618/2025 | - |
| 2026-11-24 v3-regel | 15 | 100% | 87% | 0/0 | 84% | 0 | 24% | 4.8 | 0 | 0 | 116 (151) | 19030/1844 | - |
| 2026-11-24 v3-think | 5 | 100% | 60% | 0/0 | 60% | 0 | 24% | 4.2 | 0 | 0 | 210 (222) | 19210/3886 | - |
| 2026-11-24 v3-utan-diskussion | 15 | 100% | 87% | 0/0 | 77% | 0 | 17% | 5.1 | 2 | 1 | 108 (140) | 16163/1614 | - |
| 2026-11-24 v3-verktyg1 | 8 | 100% | 100% | 0/0 | 88% | 0 | 16% | 4.6 | 3 | 0 | 185 (230) | 27117/2404 | - |
| 2026-11-24 v4-utan-regler | 15 | 73% | 40% | 0/4 | 85% | 0 | 15% | 5.3 | 0 | 0 | 121 (181) | 18390/1708 | - |
| 2026-11-24 v4 | 15 | 100% | 80% | 0/0 | 86% | 0 | 15% | 5.0 | 3 | 0 | 120 (270) | 19324/1686 | - |
| 2026-11-25 v5 | 11 | 100% | 82% | 0/0 | 92% | 0 | 9% | 6.0 | 2 | 0 | 120 (134) | 23467/1783 | - |
| 2026-11-25 holdout-baslinje | 5 | 60% | 40% | 0/2 | 70% | 0 | 27% | 4.8 | 2 | 0 | 233 (395) | 25329/4332 | - |
| 2026-11-25 holdout-v4 | 5 | 100% | 100% | 0/0 | 90% | 0 | 10% | 4.8 | 0 | 0 | 109 (114) | 18422/1704 | - |
| 2026-11-25 holdout2-baslinje | 5 | 20% | 0% | 2/2 | 33% | 0 | 10% | 5.4 | 0 | 0 | 219 (257) | 21770/3880 | - |
| 2026-11-25 holdout2-v4 | 5 | 100% | 100% | 0/0 | 100% | 0 | 14% | 5.0 | 0 | 0 | 98 (123) | 17053/1564 | - |

## Varianter

- **2026-11-24 baslinje**: Pipelinen som den var (commit bf2001e): qwen3.5:9b, specialister med verktygsloop, fri brådska 
- **2026-11-24 v2-hybrid**: Faktablad + regelram (hybrid: teamet får flytta brådskan ett steg), diskussion, inga extra verktygsrundor 
- **2026-11-24 v3-fri**: v3, teamet väljer brådska fritt (larmspärr kvar) `KONSILIET_LAGE_BRADSKA=fri`
- **2026-11-24 v3-hybrid**: v2 + granskarfixar (fältnamn, tusental, intervall, tecken), F:tolkning som källa, kortare svar, helst 2 specialister 
- **2026-11-24 v3-medgemma**: v3 + MedGemma-bakgrund i faktabladet (modellbyte i Ollama) `KONSILIET_LAGE_MEDGEMMA=1`
- **2026-11-24 v3-regel**: v3, brådskan = regelverket `KONSILIET_LAGE_BRADSKA=regel`
- **2026-11-24 v3-think**: v3 med tänkande (think) i slutbedömningen `KONSILIET_LAGE_THINK=1`
- **2026-11-24 v3-utan-diskussion**: v3 utan replikrunda mot advokaten `KONSILIET_LAGE_DISKUSSION=0`
- **2026-11-24 v3-verktyg1**: v3 + en egen verktygsrunda per specialist `KONSILIET_LAGE_VERKTYGSRUNDOR=1`
- **2026-11-24 v4-utan-regler**: v4 utan regelverk: ingen F:tolkning i faktabladet och fri brådska (larmspärren kvar) `KONSILIET_LAGE_BRADSKA=fri KONSILIET_LAGE_TOLKNING=0`
- **2026-11-24 v4**: v3 + tolkningstexter i faktabladet (signalkvalitet, HRV-fall efter träning/temperatur), puls efter pass, råd som handlingar, slutsatsstöd ur källtext 
- **2026-11-25 v5**: v4 + sömnskuld, sena kvällar, träningsbelastning, riktning utskriven, perioder med ramord 
- **2026-11-25 holdout-baslinje**: Holdout (5 scenarier skrivna efter regelverket), gamla pipelinen 
- **2026-11-25 holdout-v4**: Holdout (5 scenarier skrivna efter regelverket), v4 
- **2026-11-25 holdout2-baslinje**: Holdout 2, gamla pipelinen 
- **2026-11-25 holdout2-v4**: Holdout 2 (5 nya scenarier), v4 

## Per scenario (brådska, täckning)

| Scenario | Facit | baslinje | v2-hybrid | v3-fri | v3-hybrid | v3-medgemma | v3-regel | v3-think | v3-utan-diskussion | v3-verktyg1 | v4-utan-regler | v4 | v5 | holdout-baslinje | holdout-v4 | holdout2-baslinje | holdout2-v4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| akut_takykardi | kontakta_vard_nu | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | FEL bevaka 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | - | - | - | - |
| traning_puls | ingen | ok ingen 100% | ok ingen 33% | ok ingen 67% | ok ingen 33% | ok bevaka 33% | ok ingen 67% | ok bevaka 33% | ok ingen 33% | ok ingen 67% | ok ingen 67% | ok ingen 67% | ok ingen 100% | - | - | - | - |
| sensorspikar | ingen | FEL kontakta_vard_nu 50% | ok ingen 50% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok bevaka 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - | - |
| klocka_los | bevaka | ok ingen 0% | ok bevaka 0% | ok bevaka 0% | ok bevaka 50% | ok bevaka 50% | ok bevaka 50% | ok bevaka 50% | ok bevaka 100% | ok bevaka 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - | - |
| forkylning | bevaka | ok bevaka 50% | ok bevaka 100% | ok bevaka 50% | ok bevaka 75% | ok bevaka 75% | ok bevaka 75% | ok bevaka 50% | ok bevaka 50% | ok bevaka 75% | FEL ingen 25% | ok bevaka 75% | ok bevaka 75% | - | - | - | - |
| sent_spelande | bevaka | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 67% | ok bevaka 100% | - | ok bevaka 100% | ok bevaka 100% | ok ingen 100% | ok bevaka 67% | ok bevaka 100% | - | - | - | - |
| spo2_dippar | ta_upp_med_varden | FEL bevaka 67% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | FEL bevaka 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | - | - | - |
| aktiv_vs_stilla | ingen | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 67% | ok ingen 100% | - | ok ingen 67% | ok ingen 100% | ok ingen 67% | ok ingen 100% | ok ingen 100% | - | - | - | - |
| allt_normalt | ingen | FEL bevaka 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | ok ingen 100% | - | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - | - |
| trott_fraga | ingen | FEL kontakta_vard_nu 0% | ok bevaka 100% | ok bevaka 67% | ok bevaka 67% | ok bevaka 67% | ok bevaka 67% | - | ok bevaka 67% | - | ok ingen 100% | ok bevaka 67% | ok bevaka 67% | - | - | - | - |
| lagt_ferritin | ta_upp_med_varden | FEL ingen 25% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 75% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | ok ta_upp_med_varden 100% | - | FEL bevaka 75% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | - | - | - |
| motstridigt | bevaka | ok bevaka 33% | ok bevaka 33% | ok bevaka 33% | ok bevaka 33% | ok bevaka 33% | ok bevaka 67% | - | ok bevaka 33% | - | ok ingen 67% | ok bevaka 67% | - | - | - | - | - |
| spo2_akut | kontakta_vard_nu | FEL bevaka 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 100% | - | ok kontakta_vard_nu 67% | - | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | - | - | - | - | - |
| aterkommande_hopp | ta_upp_med_varden | FEL bevaka 50% | ok kontakta_vard_nu 50% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 75% | ok kontakta_vard_nu 75% | - | ok kontakta_vard_nu 75% | - | ok kontakta_vard_nu 75% | ok kontakta_vard_nu 75% | - | - | - | - | - |
| stress_projekt | bevaka | ok ingen 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 67% | ok bevaka 100% | ok bevaka 100% | - | ok bevaka 100% | - | ok ingen 100% | ok bevaka 100% | - | - | - | - | - |
| trott_spelkvallar | bevaka | ok ingen 0% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| h_natt_takykardi | kontakta_vard_nu | - | - | - | - | - | - | - | - | - | - | - | - | FEL ingen 100% | ok kontakta_vard_nu 100% | - | - |
| h_cykling | ingen | - | - | - | - | - | - | - | - | - | - | - | - | ok ingen 0% | ok ingen 100% | - | - |
| h_anemi | ta_upp_med_varden | - | - | - | - | - | - | - | - | - | - | - | - | FEL bevaka 100% | ok ta_upp_med_varden 100% | - | - |
| h_lag_nattpuls | ingen | - | - | - | - | - | - | - | - | - | - | - | - | ok ingen 100% | ok ingen 100% | - | - |
| h_enstaka_syrefall | ingen | - | - | - | - | - | - | - | - | - | - | - | - | ok bevaka 50% | ok ingen 50% | - | - |
| h2_morgonlopning | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok bevaka 0% | ok ingen 100% |
| h2_snarkning | ta_upp_med_varden | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL kontakta_vard_nu 67% | ok ta_upp_med_varden 100% |
| h2_feber | bevaka | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL ingen 0% | ok bevaka 100% |
| h2_tsh | ta_upp_med_varden | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL ingen 50% | ok ta_upp_med_varden 100% |
| h2_spel_ok | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL bevaka 50% | ok ingen 100% |
| h3_syrefall_forra_natten | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| h3_en_kort_natt | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
