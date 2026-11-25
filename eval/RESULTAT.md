# Utvärdering av konsiliet

## Slutsiffran

| Körning | n | Godtagbar brådska | Exakt | Över-/undertriage | Täckning av måste-fynd | Strykandel | Median s (max) | Utdatatokens/möte |
|---|---|---|---|---|---|---|---|---|
| Gamla pipelinen, 16 tränade scenarier | 16 | 56% | 44% | 3/4 | 60% | 14% | 290 (350) | 4460 |
| Nuvarande (v8), 16 tränade scenarier | 16 | 100% | 88% | 0/0 | 92% | 15% | 123 (166) | 1866 |
| Gamla pipelinen, 16 holdout-scenarier | 16 | 56% | 38% | 3/4 | 67% | 16% | 226 (395) | 4167 |
| Nuvarande (v8), 16 holdout-scenarier | 16 | 100% | 100% | 0/0 | 94% | 16% | 118 (155) | 1806 |
| v8 med gemma4:12b, 16 holdout-scenarier | 16 | 100% | 88% | 0/0 | 98% | 5% | 156 (180) | 1718 |

## Modellval

qwen3.5:9b är kvar som modell. Samma v8 och samma 16 holdout-scenarier med gemma4:12b: samma brådska (16 av 16 godtagbara, 14 exakta mot 16, de två andra ett steg högre), bättre täckning (98 % mot 94 %) och klart bättre källdisciplin (granskaren strök 5 % mot 16 %), men median 156 s mot 118 s och 12,3 GiB i Ollama mot 8,4 GiB. Med gemma4:12b nådde swappen 10,8 GB och disken 8 GB ledigt. Den här datorn delas med röst, webb och vakt, så den extra tiden och minnet vägde tyngre. Med mer minne är gemma4:12b det första att byta till.

## Metod

- **Data:** en syntetisk person, minutupplöst simulering av 28 dygn (`eval/sim.py`). All data är märkt `syntetisk` och skrivs till slängbara databaser under `eval/tmp/`, aldrig till den riktiga.
- **Klocka:** varje scenario körs i en egen process vars klocka flyttas till scenariots tidpunkt (03:40 för nattliga syrefall, 21:40 för pulsrusningen). Vaktens egna regler får titta på datan och deras larm fryses i `eval/utlosare.json`, så att alla varianter får exakt samma utlösare.
- **Facit** (`eval/scenarier.py`): rätt brådska, vilka brådskor som är godtagbara, fynd som måste finnas (reguljära uttryck) och påståenden som inte får göras (räknas bara utan negation).
- **Tränade scenarier:** 16. Förbättringarna gjordes medan de kördes, så de är optimistiska.
- **Holdout:** 16 scenarier i fem omgångar, var och en skriven innan den kördes. När en holdout-omgång visade ett fel rättades orsaken generellt (inte scenariot) och en ny omgång skrevs för att mäta igen. Holdout 5 är delvis förorenad: vilopulsregeln för frågor skrevs efter att holdout 5:s faktablad (men inte teamets svar) setts. Första körningen av varje omgång: holdout 1 och 2 med v4 (10 av 10 brådska), holdout 3 med v5 (2 av 2), holdout 4 med v7 (2 av 2, ett missat fynd), holdout 5 med v8 (2 av 2).
- **Tid:** modellen laddas ur före varje scenario, så tiden inkluderar en kall modellstart. Körningar som överlappade en annan modell i minnet (swap) är omkörda; minnet efter varje scenario sparas (`ollama_minne_gib_efter`).
- **Domare:** medgemma:4b (en annan modell än Qwen som kör mötet) svarar på ja/nej-frågor mot facit. Den är för snäll (gav den gamla pipelinens holdout 2, med 1 av 5 rätt brådska, 5,0) och redovisas bara som komplement.
- **Spridning:** varje variant är körd en gång. Samma scenario kan ge olika svar vid omkörning, särskilt i den gamla pipelinen; skillnader på några procentenheter i täckning är brus.

## Alla körningar

Genereras av `eval/rapport.py`.
Brådska godtagbar = inom facits godtagbara nivåer. Täckning = andel måste-fynd i slutbedömningen.
Förbjudna = påståenden som inte får göras (utan negation). Strykandel = granskarens strykningar / specialistpåståenden.
Overifierade = siffror i slutbedömningens egen text som inte finns i någon hämtad källa.
Baslinjefel = meningar som kallar en siffra baslinje fast den inte är ett baslinjevärde.

Mac mini M4 16 GB, Ollama, en förfrågan i taget.

| Variant | n | Brådska godtagbar | Exakt | Över/under | Täckning | Förbjudna | Strykandel | Belagda/möte | Overifierade | Baslinjefel | Sek median (max) | Prompt-/ut-tokens | Domare |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-24 baslinje | 16 | 56% | 44% | 3/4 | 60% | 0 | 14% | 6.8 | 4 | 0 | 290 (350) | 26442/4460 | 4.43 |
| 2026-11-24 v2-hybrid | 15 | 100% | 87% | 0/0 | 78% | 0 | 26% | 7.8 | 0 | 0 | 138 (157) | 19873/2430 | - |
| 2026-11-24 v3-fri | 15 | 100% | 87% | 0/0 | 79% | 1 | 14% | 5.3 | 0 | 2 | 121 (142) | 19270/1894 | - |
| 2026-11-24 v3-hybrid | 15 | 100% | 87% | 0/0 | 76% | 0 | 19% | 4.5 | 0 | 1 | 117 (129) | 18106/1760 | - |
| 2026-11-24 v3-medgemma | 15 | 100% | 80% | 0/0 | 76% | 0 | 26% | 4.7 | 1 | 0 | 128 (165) | 20618/2025 | - |
| 2026-11-24 v3-regel | 15 | 100% | 87% | 0/0 | 84% | 0 | 24% | 4.8 | 0 | 0 | 116 (151) | 19030/1844 | - |
| 2026-11-24 v3-think | 5 | 100% | 60% | 0/0 | 60% | 0 | 24% | 4.2 | 0 | 0 | 210 (222) | 19210/3886 | - |
| 2026-11-24 v3-utan-diskussion | 15 | 100% | 87% | 0/0 | 77% | 0 | 17% | 5.1 | 2 | 1 | 108 (140) | 16163/1614 | - |
| 2026-11-24 v3-verktyg1 | 8 | 100% | 100% | 0/0 | 88% | 0 | 16% | 4.6 | 3 | 0 | 185 (230) | 27117/2404 | - |
| 2026-11-24 v4-utan-regler | 15 | 73% | 40% | 0/4 | 85% | 0 | 15% | 5.3 | 0 | 0 | 121 (181) | 18390/1708 | 5.0 |
| 2026-11-24 v4 | 15 | 100% | 80% | 0/0 | 86% | 0 | 15% | 5.0 | 3 | 0 | 120 (270) | 19324/1686 | 4.87 |
| 2026-11-25 v5 | 16 | 100% | 81% | 0/0 | 92% | 0 | 12% | 6.0 | 2 | 0 | 122 (146) | 23845/1825 | 4.88 |
| 2026-11-25 v6 | 16 | 100% | 75% | 0/0 | 94% | 0 | 10% | 6.8 | 1 | 1 | 124 (154) | 24918/1919 | 5.0 |
| 2026-11-25 v8 | 16 | 100% | 88% | 0/0 | 92% | 0 | 15% | 6.2 | 0 | 0 | 123 (166) | 25055/1866 | 4.88 |
| 2026-11-25 holdout-baslinje | 5 | 60% | 40% | 0/2 | 70% | 0 | 27% | 4.8 | 2 | 0 | 233 (395) | 25329/4332 | 5.0 |
| 2026-11-25 holdout-v4 | 5 | 100% | 100% | 0/0 | 90% | 0 | 10% | 4.8 | 0 | 0 | 109 (114) | 18422/1704 | 5.0 |
| 2026-11-25 holdout-v5 | 5 | 100% | 100% | 0/0 | 100% | 0 | 10% | 6.8 | 0 | 0 | 116 (140) | 24803/1890 | 4.6 |
| 2026-11-25 holdout-v6 | 5 | 100% | 100% | 0/0 | 90% | 0 | 13% | 5.8 | 0 | 0 | 122 (145) | 23999/1920 | 5.0 |
| 2026-11-25 holdout-v8 | 5 | 100% | 100% | 0/0 | 90% | 0 | 12% | 5.2 | 0 | 0 | 118 (142) | 24125/1792 | 5.0 |
| 2026-11-25 holdout-v8-gemma12b | 5 | 100% | 80% | 0/0 | 100% | 0 | 6% | 6.4 | 0 | 0 | 156 (174) | 26891/1758 | - |
| 2026-11-25 holdout2-baslinje | 5 | 20% | 0% | 2/2 | 33% | 0 | 10% | 5.4 | 0 | 0 | 219 (257) | 21770/3880 | 5.0 |
| 2026-11-25 holdout2-v4 | 5 | 100% | 100% | 0/0 | 100% | 0 | 14% | 5.0 | 0 | 0 | 98 (123) | 17053/1564 | 5.0 |
| 2026-11-25 holdout2-v5 | 5 | 100% | 100% | 0/0 | 77% | 0 | 30% | 4.8 | 0 | 0 | 114 (118) | 22339/1656 | 5.0 |
| 2026-11-25 holdout2-v6 | 5 | 100% | 100% | 0/0 | 100% | 0 | 12% | 5.6 | 0 | 0 | 122 (126) | 21916/1800 | 5.0 |
| 2026-11-25 holdout2-v8 | 5 | 100% | 100% | 0/0 | 90% | 0 | 19% | 5.8 | 1 | 1 | 119 (141) | 23366/1815 | 5.0 |
| 2026-11-25 holdout2-v8-gemma12b | 5 | 100% | 80% | 0/0 | 93% | 0 | 6% | 6.8 | 0 | 0 | 172 (180) | 27088/1837 | - |
| 2026-11-25 holdout3-baslinje | 2 | 100% | 50% | 0/0 | 75% | 0 | 13% | 6.5 | 1 | 0 | 335 (335) | 28401/4746 | 5.0 |
| 2026-11-25 holdout3-v5 | 2 | 100% | 100% | 0/0 | 100% | 0 | 17% | 5.5 | 0 | 0 | 118 (118) | 22371/1686 | 5.0 |
| 2026-11-25 holdout3-v6 | 2 | 100% | 100% | 0/0 | 100% | 1 | 7% | 5.5 | 0 | 0 | 121 (121) | 20426/1646 | 5.0 |
| 2026-11-25 holdout3-v8 | 2 | 100% | 100% | 0/0 | 100% | 0 | 17% | 5.0 | 0 | 0 | 137 (137) | 21216/1758 | 5.0 |
| 2026-11-25 holdout3-v8-gemma12b | 2 | 100% | 100% | 0/0 | 100% | 0 | 6% | 6.0 | 0 | 0 | 148 (148) | 24836/1482 | - |
| 2026-11-25 holdout4-baslinje | 2 | 100% | 100% | 0/0 | 100% | 0 | 0% | 6.0 | 0 | 0 | 222 (222) | 19458/3584 | 5.0 |
| 2026-11-25 holdout4-v7 | 2 | 100% | 100% | 0/0 | 75% | 0 | 10% | 8.5 | 0 | 0 | 133 (133) | 24202/1884 | - |
| 2026-11-25 holdout4-v8 | 2 | 100% | 100% | 0/0 | 100% | 0 | 17% | 8.5 | 0 | 0 | 155 (155) | 27366/2087 | 5.0 |
| 2026-11-25 holdout4-v8-gemma12b | 2 | 100% | 100% | 0/0 | 100% | 0 | 0% | 7.5 | 0 | 2 | 172 (172) | 27188/1658 | - |
| 2026-11-25 holdout5-baslinje | 2 | 50% | 50% | 1/0 | 100% | 0 | 21% | 5.5 | 0 | 0 | 299 (299) | 25892/4476 | 5.0 |
| 2026-11-25 holdout5-v8 | 2 | 100% | 100% | 0/0 | 100% | 0 | 13% | 5.0 | 0 | 0 | 116 (116) | 21356/1585 | 5.0 |
| 2026-11-25 holdout5-v8-gemma12b | 2 | 100% | 100% | 0/0 | 100% | 0 | 7% | 6.0 | 0 | 0 | 150 (150) | 22868/1618 | - |

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
- **2026-11-25 v6**: v5 + provsvaren med vid trötthetsfrågor 
- **2026-11-25 v8**: v6 + låg puls-tumregel, pulsen nu mot baslinjen, egen fråga som källa, vilopulsregel för frågor 
- **2026-11-25 holdout-baslinje**: Holdout (5 scenarier skrivna efter regelverket), gamla pipelinen 
- **2026-11-25 holdout-v4**: Holdout (5 scenarier skrivna efter regelverket), v4 
- **2026-11-25 holdout-v5**: Holdout 1, v5 
- **2026-11-25 holdout-v6**: Holdout 1, v6 
- **2026-11-25 holdout-v8**: Holdout 1, v8 
- **2026-11-25 holdout-v8-gemma12b**: v8 med gemma4:12b som modell i hela mötet `KONSILIET_MODEL_ORCH=gemma4:12b`
- **2026-11-25 holdout2-baslinje**: Holdout 2, gamla pipelinen 
- **2026-11-25 holdout2-v4**: Holdout 2 (5 nya scenarier), v4 
- **2026-11-25 holdout2-v5**: Holdout 2, v5 
- **2026-11-25 holdout2-v6**: Holdout 2, v6 
- **2026-11-25 holdout2-v8**: Holdout 2, v8 
- **2026-11-25 holdout2-v8-gemma12b**: v8 med gemma4:12b som modell i hela mötet `KONSILIET_MODEL_ORCH=gemma4:12b`
- **2026-11-25 holdout3-baslinje**: Holdout 3, gamla pipelinen 
- **2026-11-25 holdout3-v5**: Holdout 3 (skrivna efter felet i holdout 1), v5 
- **2026-11-25 holdout3-v6**: Holdout 3, v6 
- **2026-11-25 holdout3-v8**: Holdout 3, v8 
- **2026-11-25 holdout3-v8-gemma12b**: v8 med gemma4:12b som modell i hela mötet `KONSILIET_MODEL_ORCH=gemma4:12b`
- **2026-11-25 holdout4-baslinje**: Holdout 4, gamla pipelinen 
- **2026-11-25 holdout4-v7**: Holdout 4 (skrivna efter felet i holdout 1 v6), v7 
- **2026-11-25 holdout4-v8**: Holdout 4, v8 
- **2026-11-25 holdout4-v8-gemma12b**: v8 med gemma4:12b som modell i hela mötet `KONSILIET_MODEL_ORCH=gemma4:12b`
- **2026-11-25 holdout5-baslinje**: Holdout 5, gamla pipelinen 
- **2026-11-25 holdout5-v8**: Holdout 5 (skrivna efter felet i holdout 4), v8 
- **2026-11-25 holdout5-v8-gemma12b**: v8 med gemma4:12b som modell i hela mötet `KONSILIET_MODEL_ORCH=gemma4:12b`

## Per scenario (brådska, täckning)

| Scenario | Facit | baslinje | v2-hybrid | v3-fri | v3-hybrid | v3-medgemma | v3-regel | v3-think | v3-utan-diskussion | v3-verktyg1 | v4-utan-regler | v4 | v5 | v6 | v8 | holdout-baslinje | holdout-v4 | holdout-v5 | holdout-v6 | holdout-v8 | holdout-v8-gemma12b | holdout2-baslinje | holdout2-v4 | holdout2-v5 | holdout2-v6 | holdout2-v8 | holdout2-v8-gemma12b | holdout3-baslinje | holdout3-v5 | holdout3-v6 | holdout3-v8 | holdout3-v8-gemma12b | holdout4-baslinje | holdout4-v7 | holdout4-v8 | holdout4-v8-gemma12b | holdout5-baslinje | holdout5-v8 | holdout5-v8-gemma12b |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| akut_takykardi | kontakta_vard_nu | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | FEL bevaka 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| traning_puls | ingen | ok ingen 100% | ok ingen 33% | ok ingen 67% | ok ingen 33% | ok bevaka 33% | ok ingen 67% | ok bevaka 33% | ok ingen 33% | ok ingen 67% | ok ingen 67% | ok ingen 67% | ok ingen 100% | ok ingen 100% | ok ingen 33% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| sensorspikar | ingen | FEL kontakta_vard_nu 50% | ok ingen 50% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok bevaka 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| klocka_los | bevaka | ok ingen 0% | ok bevaka 0% | ok bevaka 0% | ok bevaka 50% | ok bevaka 50% | ok bevaka 50% | ok bevaka 50% | ok bevaka 100% | ok bevaka 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok bevaka 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| forkylning | bevaka | ok bevaka 50% | ok bevaka 100% | ok bevaka 50% | ok bevaka 75% | ok bevaka 75% | ok bevaka 75% | ok bevaka 50% | ok bevaka 50% | ok bevaka 75% | FEL ingen 25% | ok bevaka 75% | ok bevaka 75% | ok bevaka 75% | ok bevaka 75% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| sent_spelande | bevaka | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 67% | ok bevaka 100% | - | ok bevaka 100% | ok bevaka 100% | ok ingen 100% | ok bevaka 67% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| spo2_dippar | ta_upp_med_varden | FEL bevaka 67% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | FEL bevaka 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| aktiv_vs_stilla | ingen | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 67% | ok ingen 100% | - | ok ingen 67% | ok ingen 100% | ok ingen 67% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| allt_normalt | ingen | FEL bevaka 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | ok ingen 100% | - | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| trott_fraga | ingen | FEL kontakta_vard_nu 0% | ok bevaka 100% | ok bevaka 67% | ok bevaka 67% | ok bevaka 67% | ok bevaka 67% | - | ok bevaka 67% | - | ok ingen 100% | ok bevaka 67% | ok bevaka 67% | ok bevaka 100% | ok bevaka 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| lagt_ferritin | ta_upp_med_varden | FEL ingen 25% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 75% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | ok ta_upp_med_varden 100% | - | FEL bevaka 75% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| motstridigt | bevaka | ok bevaka 33% | ok bevaka 33% | ok bevaka 33% | ok bevaka 33% | ok bevaka 33% | ok bevaka 67% | - | ok bevaka 33% | - | ok ingen 67% | ok bevaka 67% | ok bevaka 67% | ok ingen 67% | ok bevaka 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| spo2_akut | kontakta_vard_nu | FEL bevaka 67% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 67% | ok kontakta_vard_nu 100% | - | ok kontakta_vard_nu 67% | - | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| aterkommande_hopp | ta_upp_med_varden | FEL bevaka 50% | ok kontakta_vard_nu 50% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 75% | ok kontakta_vard_nu 75% | - | ok kontakta_vard_nu 75% | - | ok kontakta_vard_nu 75% | ok kontakta_vard_nu 75% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| stress_projekt | bevaka | ok ingen 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 67% | ok bevaka 100% | ok bevaka 100% | - | ok bevaka 100% | - | ok ingen 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| trott_spelkvallar | bevaka | ok bevaka 50% | - | - | - | - | - | - | - | - | - | - | ok bevaka 100% | ok bevaka 100% | ok bevaka 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| h_natt_takykardi | kontakta_vard_nu | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL ingen 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | ok kontakta_vard_nu 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| h_cykling | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok ingen 0% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok bevaka 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| h_anemi | ta_upp_med_varden | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL bevaka 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| h_lag_nattpuls | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 50% | ok ingen 100% | ok ingen 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| h_enstaka_syrefall | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok bevaka 50% | ok ingen 50% | ok ingen 100% | ok ingen 100% | ok ingen 50% | ok ingen 100% | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| h2_morgonlopning | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok bevaka 0% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok bevaka 100% | - | - | - | - | - | - | - | - | - | - | - | - |
| h2_snarkning | ta_upp_med_varden | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL kontakta_vard_nu 67% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | - | - | - | - | - | - | - | - | - | - | - |
| h2_feber | bevaka | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL ingen 0% | ok bevaka 100% | ok bevaka 33% | ok bevaka 100% | ok bevaka 100% | ok bevaka 67% | - | - | - | - | - | - | - | - | - | - | - | - |
| h2_tsh | ta_upp_med_varden | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL ingen 50% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | ok ta_upp_med_varden 100% | - | - | - | - | - | - | - | - | - | - | - | - |
| h2_spel_ok | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL bevaka 50% | ok ingen 100% | ok ingen 50% | ok ingen 100% | ok ingen 50% | ok ingen 100% | - | - | - | - | - | - | - | - | - | - | - | - |
| h3_syrefall_forra_natten | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok bevaka 50% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - | - | - | - | - |
| h3_en_kort_natt | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - | - | - | - | - |
| h4_lag_puls_dag | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok ingen 100% | ok ingen 100% | ok ingen 100% | ok ingen 100% | - | - | - |
| h4_hog_puls_kaffe | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok ingen 100% | ok ingen 50% | ok ingen 100% | ok ingen 100% | - | - | - |
| h5_trappor | ingen | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | ok ingen 100% | ok ingen 100% | ok ingen 100% |
| h5_vila_hog | bevaka | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | FEL kontakta_vard_nu 100% | ok bevaka 100% | ok bevaka 100% |
