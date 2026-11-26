# Tävlingsbidrag, utkast

Utkast till formuläret på projekt.sweclockers.com/asus för **Kropp64**. Fälten och teckengränserna följer formuläret.
Antalet tecken är räknat på texten inuti kodblocket (Python `len`, radbrytningar inräknade). Klistra in texten utan
kodblocket.

Det som står inom hakparentes med FYLLS I ska ersättas med riktiga uppgifter innan bidraget skickas. Inget i
utkastet påstår något om vad systemet hittat i min riktiga data, eftersom det inte har gått tillräckligt länge än.
Räkna om tecknen efter ändringar: `python3 -c "import sys;print(len(open(sys.argv[1]).read().strip()))" fil.txt`.

## Rubrik

102 av 120 tecken.

```text
Kropp64: sensorpanelen för kroppen, med ett lokalt AI-läkarteam som larmar när jag själv kör för varmt
```

## Beskriv projektet med en mening

153 av 160 tecken.

```text
Som AIDA64 och HWiNFO64, fast för kroppen: ett lokalt AI-läkarteam läser klockans sensorer, och en moderator i kod stryker allt som inte går att belägga.
```

## Vad byggde du, och hur?

5786 av 8000 tecken.

```text
Jag är 18, köpte en Mac mini M4 med 16 GB under OpenClaw-trenden i januari och har byggt egna AI-grejer på den sedan dess. Det betyder också att jag sitter inne väldigt mycket. Jag vill börja träna mer, sova bättre och se hur kodpass och spelkvällar faktiskt syns i kroppen. Klockan samlar redan allt det där, men ingen tittar på det. Så jag byggde en sensorpanel för kroppen, med ett läkarteam som läser sensorerna, och allt körs på Mac minin.

Puls vid datorn
Mac minin loggar vilken sorts program jag har i fokus varje minut (kod, spel, chatt, webb) och lägger det bredvid pulsen. Panelen "Uptime vid datorn" visar minuter per kategori och medianpulsen under just de minuterna, och tidslinjen visar datortiden som band under pulskurvan. Bara kategorin sparas, aldrig fönstertitlar.

Sensorpanelen
Översikten är byggd som en hårdvarumonitor: en tät tabell med Aktuellt, Min, Max och Medel per sensor, grupperat som hårdvara. Hjärta (Pixel Watch): Klockfrekvens, Idle-klock, Timingmarginal (HRV). Andning: andningsfrekvens, SpO2. Kylning: hudtemperatur, Headroom (återhämtning med öppen formel). Last: steg, Stresstest, Uptime. Skämten står i rubrikerna, riktiga enheter står alltid bredvid siffrorna. Morgonbriefen heter POST-skärmen.

Datan
Pixel Watch skickar puls, steg och träningspass till mobilen, som skickar vidare till Mac minin. HRV, syremättnad, andning, hudtemperatur och sömn kommer via Health Connect. Journalen och provsvaren hämtar jag från 1177 med mitt eget BankID.

En vakt går igenom datan hela tiden. Akuta saker (puls över 140 i vila, syremättnad under 88 %, klockans fall-larm) är vanliga regler som larmar mobilen på millisekunder, utan någon språkmodell. Avvikelser mot min egen baslinje (median och MAD per timme på dygnet, 28 dagar, puls bara från vilominuter) startar en tråd.

Läkarteamet är en supporttråd
1. Ett faktablad räknas fram i kod: observerat mot baslinje, nätter, prover. Varje del får en referens.
2. Trådstartaren, en allmänläkare, kallar in 2-4 specialister: kardiolog, sömnläkare, idrottsläkare, stressläkare, Labbet.
3. Specialisterna svarar i tråden med strukturerad JSON. Varje påstående måste lista sina källor, och schemat låser källorna till referenser som faktiskt finns i tråden.
4. Moderatorn stryker allt som inte håller: "Strukit av moderator. Anledning: saknar källa."
5. Trollet, djävulens advokat, frågar om jag har testat att dra åt armbandet, och specialisterna får bemöta.
6. Trådstartaren markerar en lösning. Den granskas igen, och brådskan bestäms av ett regelverk, inte av modellen. Bara en akut vaktregel kan ge "kontakta vården nu".

Moderatorn är det jag är mest nöjd med. Den är inte en språkmodell, utan vanlig Python. Den kollar att källan finns bland det tråden hämtat, att varje siffra finns bland källans värden (puls mot puls, procent mot SpO2, med avrundning och minuter till timmar godkänt), att ett tal som kallas baslinje verkligen är baslinjen, och att en slutsats har källa av rätt typ. När en specialist skrev att baslinjen var 73,2 och källan sa 72,5 ströks det. Ingen modell kan prata sig förbi den.

Kontoret
Varje steg i tråden sänds som en händelse över WebSocket. I webben blir det ett pixelkontor: läkarna går till arkivet när de söker i journalen, till labbet när de läser provsvar, sätter sig vid bordet och svarar i bubblor med källor under. När moderatorn stryker något stryks meningen över. Figurerna är ritade i kod, 16x24 pixlar.

Lokalt på 16 GB
Allt körs i Ollama: qwen3.5:9b för alla agenter, medgemma:4b som valfri kunskapskälla som aldrig räknas som källa. På Mac minin läser 9B-modellen prompten i 75 tokens/s och skriver i 17. Det formade allt: datan hämtas innan specialisterna börjar, svaren tvingas fram som JSON, kontexten är 8k med KV-cache i q8_0 och en förfrågan åt gången. Då tar modellen 9,1 GB i stället för 14,7.

Mätt
Mot 16 scenarier med syntetisk data och facit, plus 16 holdout-scenarier som skrevs innan de kördes. På holdout gick godtagbar brådska från 56 % i gamla pipelinen (3 övertriage, 4 undertriage) till 100 %, täckningen av måste-fynd från 67 % till 94 % och mediantiden för en tråd från 226 till 118 sekunder. Omkört med samma kod och modell: rätt brådska i 36 av 36 holdout-trådar och godtagbar i 64 av 64 tränade, täckning 91-94 % mellan körningarna. Samma 16 holdout med gemma4:12b gav lite bättre täckning (98 %) men tog 156 sekunder och 12,3 GB, så den ryms inte bredvid allt annat i 16 GB.

Klocka och mobil
Egen Wear OS-app med en kö som bara töms när mobilen kvitterat, och en Android-app med egen kö som överlever omstart och nätavbrott. På emulatorer: med mobilens nät avstängt köades 360 punkter, och alla 1 215 fanns på servern 2 sekunder efter att nätet kom tillbaka, utan dubbletter. Vid akut larm kan mobilen skicka sms till en anhörig om jag inte svarar inom vald tid. Det är avstängt tills man slår på det.

Hur, och min roll
Koden är skriven av Claude Code-agenter, flera parallellt. Jag var produktägare och grindvakt: jag sa nej till ett dussintal idéer innan den här fick fortsätta, krävde att den skulle vara agentisk från grunden, styrde om när agenterna fyllde ut med demosiffror, krävde att allt ska gå att köra på riktig data och bytte namn när jag såg att "konsilium" mest betyder kyrkomöte. Ingen hälsodata går till molnet; Claude Code skrev koden mot testdatabaser.

Vad det har hittat
[FYLLS I: vad systemet hittade i min riktiga data efter X veckor, med datum och vad som stod i lösningen]

Det är inte en medicinteknisk produkt och ställer inga diagnoser. Det ger underlag och frågor, och akuta larm går aldrig via en språkmodell.

Vad priset skulle betyda (plan, inte mätt)
Med 128 GB: en större modell för specialisterna, specialisterna parallellt i stället för en i taget, och en tråd på sekunder i stället för minuter.
```

## Vad gick fel på vägen?

2521 av 4000 tecken.

```text
Första försöket var en kuliss. Min Discord-agent fick bygga ett tävlingsbidrag och gjorde på en timme 4 000 rader Python: en hälsoagent på påhittad data, med snyggt terminaldemo. Allt kördes på påhittad data och demot visade siffror ingen mätt. Jag slängde det och började om med kravet att varje siffra ska vara uppmätt. Lärdom: säger man "gör det imponerande" till en agent optimerar den för att det ska se imponerande ut.

Första riktiga tråden tog 278 sekunder och gav ingen bedömning alls. Specialisterna fastnade i att hämta data, kardiologen anropade ett verktyg som inte finns och stressläkaren hämtade samma serie tre gånger. 47 656 prompttokens. Det var promptläsningen som åt tiden, eftersom hela samtalet skickas om vid varje steg. Fix: datan runt larmet hämtas innan mötet och slutbedömningen tvingas fram som JSON.

Andra körningen tog 563 sekunder och moderatorn var för sträng: den strök pulsen från larmet (larmet var inte registrerat som källa), klockslag och omräkningar som 450 min = 7,5 h. Fixat och inlagt som tester.

Ollama svarade 500 mitt i ett möte. Modellen som är 6,6 GB på pappret tog 14,7 GB med 16k kontext och parallella förfrågningar, och datorn swappade. 8k kontext, en förfrågan åt gången, q8_0 och flash attention gav 9,1 GB och 250 sekunder i stället för 563.

Servern startade som tjänst men svarade aldrig. macOS skyddar Skrivbordet, och en process från launchd får inte läsa där. Repot fick flytta.

Klock- och mobilemulatorn gick inte att parkoppla utan Googlekonto, så Bluetooth-hoppet ersattes med en testbrygga i debugbygget. Allt utom själva hoppet är testat på emulatorerna.

Sms-larmet kom 70 sekunder för sent, eftersom Android 14 inte ger exakta alarm utan tillstånd. Med USE_EXACT_ALARM gick det 39 ms efter fristen.

En oberoende granskningsagent hittade att vem som helst på mitt hemnät kunde läsa journalen och skicka in falsk puls med en påhittad header. Med falsk puls 150 i vila hade man kunnat utlösa ett akut larm. Nu får allt utanför localhost och Tailscale 403.

Samma granskning visade att vakten räknade bakåt från "nu", fast SpO2 kommer via Health Connect timmar senare. Larmet för låg syremättnad kunde i praktiken aldrig slå till.

Den första utvärderingen gav godtagbar brådska i 40 % av 15 scenarier och missade båda de akuta fallen. Därför går akuta larm aldrig via modellen, och brådskan styrs nu av ett regelverk.

Namnet var fel två gånger. Konsiliet betyder mest kyrkomöte, Överklockad kunde vara vilket hårdvaruverktyg som helst. Det blev Kropp64.
```

## Modeller och verktyg

415 av 500 tecken.

```text
Lokalt i Ollama: qwen3.5:9b (alla agenter i läkarteamet, POST-skärmen, tolkning av 1177-sidor), medgemma:4b (valfri medicinsk bakgrundskunskap, räknas aldrig som källa). Bygget: Claude Code med Claude Opus 5.5, flera agenter parallellt. Övrigt: Python, FastAPI, SQLite, NumPy, Playwright (1177 och PDF), Preact, Vite, Kotlin, Wear OS Health Services, Health Connect, Room, WorkManager, Tailscale, Cloudflare Tunnel.
```

## Hårdvara

224 av 300 tecken.

```text
Mac mini M4, 16 GB unified memory (server och alla lokala modeller). Pixel Watch [FYLLS I: modell] (Wear OS) och en Pixel-mobil. Lånad Lenovo-laptop (RTX 5050) för Android-bygget, emulatorerna, rösterna och 3D-renderingarna.
```

## Tokens

Kör `python3 tools/tokenredovisning.py` precis innan bidraget skickas och använd raderna under
"Till tävlingsformuläret". Siffrorna nedan är från 2026-11-26 13:45 och växer så länge bygget pågår.

Claude Code skickar hela samtalet som indata vid varje svar, och det mesta läses ur cachen. Tävlingens egen
inlämningsprompt räknar det som indata, alltså med cache. Därför står talet med cache i fältet. Talet utan cache
(bara ny indata och utdata) redovisas bredvid i texten och i repot, så att ingen behöver gissa vilket som avses.

| Fält | Värde 2026-11-26 | Vad det är |
|---|--:|---|
| Tokens i molnet | 1 113 035 997 | Claude Code under bygget, med cache: input 6 418 + cache-skrivning 16 972 189 + cache-läsning 1 093 461 391 + output 2 595 999. Utan cache (input + output): 2 602 417. Idéfasen och den oberoende granskningen räknas inte här men redovisas i skriptets utdata. |
| Tokens lokalt | 9 077 141 | Ollama på Mac minin: varje anrop från tabellen llm_calls plus utvärderingskörningarnas resultatfiler, prompt + output. |

Ingen hälsodata går till molnet: mätdata, journal och trådar bearbetas bara av de lokala modellerna. Claude Code
skrev koden mot testdatabaser med syntetisk data.

## Bilder

Tio bilder i `docs/bidrag-bilder/`, 1920x1080 PNG, alla under 5 MB och märkta i bilden. Förteckning i
docs/bidrag-bilder/README.md. Föreslagen ordning (sensorpanelen och pulsen vid datorn först, det är det SweClockers
känner igen):

1. 04-oversikt.png (sensorpanelen)
2. 05-puls-vid-datorn.png
3. 02-moderatorn-stryker.png (moderatorn stryker ett påstående)
4. 01-kontoret-i-arbete.png
5. 03-bedomningen.png
6. 07-arkitektur.png
7. 06-systemet.png
8. 09-klockappen.png
9. 08-mobilappen.png
10. 10-kontoret-pa-mobilen.png

[FYLLS I: byt en av bilderna mot en bild från riktig data när den finns, märkt "riktig data"]

## Video

[FYLLS I: YouTube-länk]. Filmen är klar: docs/video/kropp64-bidrag-1920x1080.mp4 (3 min 11 s, byggd av
render/slutvideo.py, se docs/video/README.md). Den ska laddas upp på YouTube, olistad eller publik.

## Länk

https://kropp64.se (demo med syntetisk data: https://demo.kropp64.se)

## Källkod

[FYLLS I: https://github.com/cricke1/kropp64 när repot är publikt]
