# Tävlingsbidrag, utkast

Utkast till formuläret på projekt.sweclockers.com/asus. Fälten och teckengränserna följer formuläret. Antalet tecken
är räknat på texten inuti kodblocket (Python `len`, radbrytningar inräknade). Klistra in texten utan kodblocket.

Det som står inom hakparentes med FYLLS I ska ersättas med riktiga uppgifter innan bidraget skickas. Inget i
utkastet påstår något om vad systemet hittat i min riktiga data, eftersom det inte har gått tillräckligt länge än.
Räkna om tecknen efter ändringar: `python3 -c "import sys;print(len(open(sys.argv[1]).read().strip()))" fil.txt`.

## Rubrik

85 av 120 tecken.

```text
Konsiliet: ett lokalt läkarteam av AI-agenter som vaktar min klockdata på en Mac mini
```

## Beskriv projektet med en mening

136 av 160 tecken.

```text
Klockan larmar, ett team av lokala agenter utreder, och en granskare i ren kod stryker varje påstående som inte går att peka på i datan.
```

## Vad byggde du, och hur?

4763 av 8000 tecken.

```text
Jag är 18, köpte en Mac mini M4 med 16 GB under OpenClaw-trenden i januari och har byggt egna AI-grejer på den sedan dess. Det betyder också att jag sitter inne väldigt mycket. Jag vill börja träna mer, sova bättre och förstå hur stress och spelkvällar faktiskt syns i kroppen. Klockan samlar redan allt det där, men ingen tittar på det. Så jag byggde ett läkarteam som gör det, och som körs helt på Mac minin.

Vad det gör
Pixel Watch skickar puls, steg och träningspass till mobilen, som skickar vidare till Mac minin. HRV, syremättnad, andning, hudtemperatur och sömn kommer via Health Connect. Journalen och provsvaren hämtar jag från 1177 med mitt eget BankID. Mac minin loggar också vilken sorts program jag har i fokus (kod, spel, chatt, webb), så att teamet kan se pulsen under ett kodpass eller en spelkväll. Bara kategorin sparas, aldrig fönstertitlar.

En vakt går igenom datan hela tiden. Akuta saker (puls över 140 i vila, syremättnad under 88 %, klockans fall-larm) är vanliga regler som larmar mobilen på millisekunder, utan någon språkmodell. Avvikelser mot min egen baslinje (median och MAD per timme på dygnet, 28 dagar, puls bara från vilominuter) kallar in konsiliet.

Konsiliet
1. Ett faktablad räknas fram i kod: observerat mot baslinje, nätter, prover. Varje del får en referens.
2. Ordföranden, en allmänläkare, väljer 2-4 specialister: kardiolog, sömnläkare, idrottsläkare, stressmedicin, klinisk kemist.
3. Specialisterna lämnar bedömningar som strukturerad JSON. Varje påstående måste lista sina källor, och schemat låser källorna till referenser som faktiskt finns i mötet. De kan slå upp mer med verktyg mot databasen.
4. Granskaren stryker allt som inte håller.
5. Djävulens advokat letar vardagliga förklaringar (sent träningspass, lös klocka) och specialisterna får bemöta.
6. Ordföranden skriver slutbedömningen, som granskas igen. Brådskan bestäms av ett regelverk, inte av modellen. Bara en akut vaktregel kan ge "kontakta vården nu".

Granskaren är det jag är mest nöjd med. Den är inte en språkmodell, utan vanlig Python. Den kollar att källan finns bland det mötet hämtat, att varje siffra i meningen finns bland källans värden (puls mot puls, procent mot SpO2, med avrundning och minuter till timmar godkänt), att ett tal som kallas baslinje verkligen är baslinjen, och att en slutsats har källa av rätt typ. När en specialist skrev att baslinjen var 73,2 och källan sa 72,5 ströks det. Ingen modell kan prata sig förbi den.

Kontoret
Varje steg i mötet sänds som en händelse över WebSocket. I webben blir det ett pixelkontor: läkarna går till arkivet när de söker i journalen, till labbet när de läser provsvar, sätter sig vid bordet och pratar i bubblor med källor under. När granskaren stryker något stryks meningen över i bubblan. Figurerna är ritade i kod (16x24 pixlar ur textmallar) i stället för renderade, så att de kan byta pose utan bildfiler. Det finns också en översikt med tidslinje, sömn, puls vid datorn och en öppen återhämtningsformel, en systempanel med minne och tokens, och ett besöksunderlag som PDF att ta med till vårdcentralen.

Lokalt på 16 GB
Allt körs i Ollama: qwen3.5:9b för alla agenter, medgemma:4b som valfri kunskapskälla som aldrig får räknas som källa. På Mac minin läser 9B-modellen prompten i 75 tokens/s och skriver i 17. Det formade allt: data runt larmet hämtas innan specialisterna börjar, bedömningar tvingas fram som JSON i stället för att hoppas på rätt verktygsanrop, och kontexten är 8k med KV-cache i q8_0 och en förfrågan åt gången. Då tar modellen 9,1 GB i stället för 14,7 och datorn slutar swappa.

Klocka och mobil
Egen Wear OS-app med en kö som bara töms när mobilen kvitterat, och en Android-app med egen kö som överlever omstart och nätavbrott. Testat på emulatorer: med mobilens nät avstängt köades 360 punkter, och alla 1 215 fanns på servern 2 sekunder efter att nätet kom tillbaka, utan dubbletter. Vid akut larm kan mobilen skicka sms till en anhörig om jag inte svarar inom vald tid. Det är avstängt tills man slår på det.

Hur
Koden är skriven av Claude Code-agenter som jag styrt: jag bestämde vad som skulle byggas och hur det skulle bete sig, testade och underkände. Flera agenter jobbade parallellt med webben, apparna, konsiliets kvalitet, en oberoende säkerhetsgranskning och presentationen. Allt som gick fel står i RESAN.md, och tokenåtgången räknas fram ur loggarna med ett skript i repot.

Vad det har hittat
[FYLLS I: vad systemet hittade i min riktiga data efter X veckor, med datum och vad som stod i bedömningen]
[FYLLS I: om något ledde till att jag ändrade träning, sömn eller tog med något till vården]

Det är inte en medicinteknisk produkt och ställer inga diagnoser. Det ger underlag och frågor, och akuta larm går aldrig via en språkmodell.
```

## Vad gick fel på vägen?

2374 av 4000 tecken.

```text
Första försöket var en kuliss. Min Discord-agent fick bygga ett tävlingsbidrag och gjorde på en timme 4 000 rader Python om en "diabetesagent", med snyggt terminaldemo. Allt kördes på påhittad data och demot visade siffror ingen mätt. Jag slängde det och började om med kravet att varje siffra ska vara uppmätt. Lärdom: säger man "gör det imponerande" till en agent optimerar den för att det ska se imponerande ut.

Första riktiga konsiliet tog 278 sekunder och gav ingen bedömning alls. Specialisterna fastnade i att hämta data, kardiologen anropade ett verktyg som inte finns och stressläkaren hämtade samma serie tre gånger. 47 656 prompttokens. Det var promptläsningen som åt tiden, eftersom hela samtalet skickas om vid varje steg. Fix: datan runt larmet hämtas innan mötet och slutbedömningen tvingas fram som JSON.

Andra körningen tog 563 sekunder och granskaren var för sträng: den strök pulsen från larmet (larmet var inte registrerat som källa), klockslag och omräkningar som 450 min = 7,5 h. Fixat och inlagt som tester.

Ollama svarade 500 mitt i ett möte. Modellen som är 6,6 GB på pappret tog 14,7 GB med 16k kontext och parallella förfrågningar, och datorn swappade. 8k kontext, en förfrågan åt gången, q8_0 och flash attention gav 9,1 GB och 250 sekunder i stället för 563.

Servern startade som tjänst men svarade aldrig. macOS skyddar Skrivbordet, och en process från launchd får inte läsa där. Repot fick flytta.

Klock- och mobilemulatorn gick inte att parkoppla utan Googlekonto, så Bluetooth-hoppet ersattes med en testbrygga i debugbygget. Allt utom själva hoppet är testat på emulatorerna.

Sms-larmet kom 70 sekunder för sent, eftersom Android 14 inte ger exakta alarm utan tillstånd. Med USE_EXACT_ALARM gick det 39 ms efter fristen.

En oberoende granskningsagent hittade att vem som helst på mitt hemnät kunde läsa journalen och skicka in falsk puls med en påhittad header. Med falsk puls 150 i vila hade man kunnat utlösa ett akut larm. Nu får allt utanför localhost och Tailscale 403.

Samma granskning visade att vakten räknade bakåt från "nu", fast SpO2 kommer via Health Connect timmar senare. Larmet för låg syremättnad kunde i praktiken aldrig slå till.

Den första utvärderingen gav rätt brådska i 1 av 3 scenarier och missade det akuta fallet. Därför går akuta larm aldrig via modellen.
[FYLLS I: senaste resultat från eval/RESULTAT.md]
```

## Modeller och verktyg

393 av 500 tecken.

```text
Lokalt i Ollama: qwen3.5:9b (alla agenter i konsiliet, morgonbrief, tolkning av 1177-sidor), medgemma:4b (valfri medicinsk bakgrundskunskap, räknas aldrig som källa). Bygget: Claude Code med Claude Opus 5.5, flera agenter parallellt. Övrigt: Python, FastAPI, SQLite, NumPy, Playwright (1177 och PDF), Preact, Vite, Kotlin, Wear OS Health Services, Health Connect, Room, WorkManager, Tailscale.
```

## Hårdvara

192 av 300 tecken.

```text
Mac mini M4, 16 GB unified memory (server och alla lokala modeller). Pixel Watch [FYLLS I: modell] (Wear OS) och en Pixel-mobil. En Windows-laptop (Lenovo) för Android-bygget och emulatorerna.
```

## Tokens

Kör `python3 tools/tokenredovisning.py` precis innan bidraget skickas och använd raderna under
"Till tävlingsformuläret". Siffrorna nedan är från 2026-11-24 kl. 18.20 och växer så länge bygget pågår.

| Fält | Värde 2026-11-24 | Vad det är |
|---|--:|---|
| Tokens i molnet | 874 380 | Claude Code under bygget, input + output utan cache. Cache-skrivning 2 123 992 och cache-läsning 162 774 735 redovisas separat i skriptets utdata. Idéfasen och den oberoende granskningen räknas inte här men redovisas också där. |
| Tokens lokalt | 110 505 | Ollama på Mac minin: sparade konsilier, serverns räknare sedan start och utvärderingskörningarna (prompt + output). |

Om formuläret frågar efter en enda molnsiffra: använd "utan cache" och skriv i texten att cache redovisas i repot.
[FYLLS I: aktuella siffror från skriptet]

## Bilder

Tio bilder i `docs/bidrag-bilder/`, 1920x1080 PNG, alla under 5 MB och märkta i bilden. Förteckning i
docs/bidrag-bilder/README.md. Föreslagen ordning:

1. 02-granskaren-stryker.png (huvudbild: det som skiljer projektet från andra)
2. 01-kontoret-i-arbete.png
3. 03-bedomningen.png
4. 07-arkitektur.png
5. 04-oversikt.png
6. 05-puls-vid-datorn.png
7. 06-systemet.png
8. 09-klockappen.png
9. 08-mobilappen.png
10. 10-kontoret-pa-mobilen.png

[FYLLS I: byt en av bilderna mot en bild från riktig data när den finns, märkt "riktig data"]

## Video

[FYLLS I: YouTube-länk]. Underlag: docs/video/konsiliet-demo-1920x1080.mp4 (ett helt demokonsilium, 3 min,
märkt demo i varje bildruta). Ett förslag är att klippa in 20-30 sekunder från riktig användning före demot.

## Länk

[FYLLS I: länk till publika demon om den ska visas (drift/publik-demo.sh bakom en tunnel), annars repot]

## Källkod

[FYLLS I: länk till GitHub-repot när det är publicerat]
