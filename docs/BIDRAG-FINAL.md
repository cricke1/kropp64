# Bidraget, slutversion

Varje fält i formuläret på projekt.sweclockers.com/asus/lamna-in, i samma ordning. Texten i kodblocken klistras in
som den är. Tecken räknas med `python3 docs/rakna_tecken.py` (inuti kodblocken, radbrytningar inräknade).

## Spår

Egen AI-assistent

## Rubrik (max 120)

```text
Kropp64: HWiNFO för kroppen. Pixel Watch, 1177 och ett AI-läkarteam som körs helt lokalt på min Mac mini
```

## I en mening (max 160)

```text
Jag hade koll på varje grad i GPU:n men aldrig på min egen vilopuls. Nu gör ett lokalt läkarteam det, och en moderator stryker allt utan källa.
```

## Vad byggde du, och hur? (max 8000)

```text
Min GPU har jag full koll på. Klockfrekvens, temp, last, allt i HWiNFO på andra skärmen. Min egen kropp? Ingen aning. Jag är 18, har byggt egna AI-grejer på en Mac mini sedan OpenClaw-hypen i januari och sitter inne väldigt mycket. Klockan på handleden samlar puls, sömn och HRV dygnet runt, och ingen tittar.

Så jag byggde en sensorpanel för kroppen. Och ett läkarteam av AI-agenter som läser den. Allt körs lokalt på Mac minin, 16 GB, ingen hälsodata lämnar huset.

SENSORPANELEN
Översikten ser ut som en hårdvarumonitor, för det är så jag läser saker. Hjärta (Pixel Watch): Klockfrekvens, Idle-klock (vilopuls), Timingmarginal (HRV). Kylning: hudtemperatur och Headroom, återhämtning 0-100 med öppen formel. Last: steg, Stresstest (träning) och Uptime vid datorn. Skämten står i rubrikerna, riktiga enheter står alltid bredvid siffrorna.

Och det jag faktiskt ville se: Mac minin loggar vilken sorts program jag har i fokus varje minut (kod, spel, chatt, webb), mobilen gör samma sak med skärmtiden, och allt hamnar bredvid pulsen. Klockfrekvensen under en spelkväll mot en kodkväll, på riktigt.

LÄKARTEAMET ÄR EN FORUMTRÅD
När något avviker från min egen baslinje (median och MAD per timme på dygnet, 28 dagar) startar vakten en tråd:
1. Trådstartaren, en allmänläkare, läser ett faktablad som räknats fram i kod och kallar in 2-4 specialister: kardiolog, sömnläkare, idrottsläkare, stressläkare, Labbet.
2. Specialisterna svarar med strukturerad JSON. Varje påstående måste peka på en mätpunkt, en journalrad eller ett provsvar.
3. Moderatorn stryker allt som inte håller. "Strukit av moderator. Anledning: saknar källa."
4. Trollet frågar om jag har testat att dra åt armbandet. Specialisterna får bemöta.
5. Trådstartaren markerar en lösning.

Moderatorn är det jag är mest nöjd med, för den är inte en AI. Den är vanlig Python. Den kollar att källan finns bland det tråden hämtat, att varje siffra finns i källan (puls mot puls, procent mot SpO2), att det som kallas baslinje verkligen är baslinjen. När kardiologen skrev att min baslinje var 73,2 och källan sa 72,5 ströks det. Ingen modell kan prata sig förbi den. Och brådskan bestäms av ett öppet regelverk, inte av modellen: teamet får höja den, aldrig sänka. Akuta larm (puls över 140 i vila, SpO2 under 88, fall) är vanliga regler som larmar mobilen på millisekunder, helt utan språkmodell.

I webben blir tråden ett pixelkontor: läkarna går till arkivet när de söker i journalen, till labbet när de läser provsvar och pratar med egna röster. När moderatorn stryker något stryks meningen över framför dig. I trailern fick de gräla ordentligt och Kardiologen välta bordet. Den scenen är regisserad, inspelad bildruta för bildruta ur appens egen kontorsmotor.

LOKALT PÅ 16 GB
qwen3.5:9b i Ollama för alla agenter. På Mac minin läser den prompten i ungefär 390 tokens/s men skriver i 22, så allt är byggt kring det: datan hämtas innan specialisterna börjar, svaren tvingas fram som JSON, 8k kontext, KV-cache i q8_0, en förfrågan åt gången. Då tar modellen 9,1 GB i stället för 14,7 och datorn slutar swappa. Gemma 4 12B hittade lite fler fynd men tog 12,3 GB och 156 s per tråd. Den ryms inte bredvid allt annat. 16 GB är gränsen jag slår i varje dag.

Bonusmätning: samma kod och modell på en lånad laptop med RTX 5050 (llama.cpp) tog 56 sekunder per tråd i stället för 126 på M4:an.

MÄTT, INTE GISSAT
Teamet testas mot 16 scenarier med facit plus 16 holdout-scenarier som skrevs innan de kördes. På holdout gick godtagbar brådska från 56 % i första versionen (3 övertriage, 4 undertriage) till 100 %, täckningen av måste-fynd från 67 till 94 % och tiden per tråd från 226 till 118 sekunder. Omkört med samma kod: rätt brådska i 36 av 36 holdout-trådar. Allt syntetiskt, metoden och förbehållen ligger i repot.

KLOCKA, MOBIL OCH 1177
Egen Wear OS-app på Pixel Watch 5 (puls i bakgrunden, pass med pulszoner, andningsövning, ruta och komplikationer) och en Android-app på mobilen, båda i Material 3. Klockan raderar bara det mobilen kvitterat, mobilen har en egen kö som överlever omstart och nätavbrott. Med nätet avstängt köades 360 punkter, och alla 1 215 fanns på servern två sekunder efter att nätet kom tillbaka, inga dubbletter.

Journalen och provsvaren hämtas från 1177 med mitt eget BankID: ett tryck i appen, BankID öppnas, resten sköts av en headless Chromium på Mac minin. Provsvaren tas via 1177:s egen Excel-export, och sidor som inte ändrats tolkas inte om. Vid akut larm kan mobilen skicka sms till en anhörig om jag inte svarar inom vald tid.

HUR, OCH MIN ROLL
Koden är skriven av Claude Code-agenter, flera parallellt. Jag var produktägare och grindvakt: sa nej till ett dussintal idéer innan den här fick fortsätta, krävde att den skulle vara agentisk från grunden, slängde allt som byggde på påhittad data och bytte namn när jag insåg att "konsilium" mest betyder kyrkomöte. Claude Code skrev koden mot testdatabaser, min hälsodata har aldrig varit i molnet.

Det är inte en medicinteknisk produkt och ställer inga diagnoser. Det ger underlag och frågor att ta med till vården.

VAD PRISET SKULLE BETYDA
Med 128 GB: en större modell för specialisterna, alla specialister parallellt i stället för en i taget, och en tråd på sekunder i stället för minuter. Just nu får jag välja mellan rösterna och läkarteamet. Det slutar jag med.
```

## Vad gick fel på vägen? (max 4000)

```text
24 NOV, MORGON. Första försöket var en kuliss. Min Discord-agent fick bygga ett tävlingsbidrag och spottade på en timme ur sig 4 000 rader Python: en hälsoagent på påhittad data med snyggt terminaldemo och siffror ingen mätt. Jag slängde allt och började om med en regel: varje siffra ska vara uppmätt. Lärdom: säger man "gör det imponerande" till en agent, optimerar den för att det ska SE imponerande ut.

Första riktiga tråden tog 278 sekunder och kom inte fram till något alls. Kardiologen anropade ett verktyg som inte finns och stressläkaren hämtade samma serie tre gånger. 47 656 prompttokens. Andra körningen: 563 sekunder, och nu var moderatorn för sträng och strök till och med pulsen från själva larmet.

Ollama dog med 500 mitt i ett möte. Modellen som är 6,6 GB på pappret tog 14,7 GB och Mac minin swappade. 8k kontext, en förfrågan i taget och q8_0 gav 9,1 GB och halva tiden.

Servern startade som tjänst och svarade aldrig. macOS låter inte launchd läsa Skrivbordet. Repot fick flytta.

En oberoende granskningsagent hittade att vem som helst på mitt hemnät kunde skicka in falsk puls. Puls 150 i vila hade gett ett akut larm. Nu får allt utanför localhost och Tailscale 403. Samma granskning visade att larmet för låg syremättnad i praktiken aldrig kunde slå till, eftersom vakten räknade från "nu" och SpO2 kommer timmar senare.

Den första utvärderingen: rätt brådska i 40 % av fallen, och båda de akuta missades. Därför går akuta larm aldrig via en språkmodell.

Qwen växte till 15 GiB under en lång körning och datorn swappade. Nu laddas modellen ur om den sväller.

Ollama på Windows vägrade registrera modellen ("bad manifest") på två versioner. RTX-jämförelsen kördes till slut med llama.cpp och en egen proxy som översätter Ollamas API.

Klockappen laggade, 60 % tappade bildrutor. Det var ett debugbygge och hela listan ritades om varje sekund. Release-bygge och smartare omritning: 12 %.

1177:s provsvar kom inte med, eftersom sidan bara visar ihopfällda provtagningar. Nu används deras egen Excel-export.

Renderingarna, rösterna och byggmiljön låg på den lånade laptopen, som skulle återställas mitt i allt. Signeringsnyckeln för apparna fanns bara där. Den räddades till Mac minin, annars hade apparna fått installeras om från noll.

Och namnet var fel två gånger. Konsiliet betyder mest kyrkomöte, Överklockad kunde vara vilket hårdvaruverktyg som helst. Det blev Kropp64.
```

## Modeller och verktyg (max 500)

```text
Lokalt i Ollama: qwen3.5:9b (alla agenter i läkarteamet, POST-skärmen, tolkning av 1177-sidor). llama.cpp på RTX 5050 för jämförelsen. Rösterna: Chatterbox med svenska vikter (Parambe). Bygget: Claude Code med Claude Opus 5.5, flera agenter parallellt. Övrigt: Python, FastAPI, SQLite, Playwright (1177), Preact, Vite, Kotlin, Jetpack Compose, Wear OS Health Services, Health Connect, Blender (renderingar), Tailscale, Cloudflare Tunnel.
```

## Hårdvara (max 300)

```text
Mac mini M4 16 GB (server, alla lokala modeller, 1177-hämtningen). Pixel Watch 5 och Samsung Galaxy Z Flip8. Lånad Lenovo-laptop med RTX 5050 för rösterna, 3D-renderingarna och RTX-jämförelsen.
```

## Tokens

- Var kördes AI:n: **Både och**
- Tokens bearbetade lokalt: **9 878 376** (Ollama på Mac minin plus llama.cpp-körningen på RTX 5050)
- Tokens betalda i molnet: **1 321 041 453** (Claude Code under bygget, med cache)
- Hur vet du antalet tokens: **Från en tokenräknare**

Uppdatera precis innan inlämning med `python3 tools/tokenredovisning.py` (siffrorna ovan är från 2026-11-26 kväll).
Utan cache (bara ny input och output) var molnet 3 136 932 tokens. Det står i repot.

## Bilder (1-10, högst 5 MB, PNG/JPG/WebP/GIF), i den här ordningen

1. `docs/bidrag-media/01-kropp64.jpg` - kortbilden: 3D-rendering med de riktiga appskärmarna och OSD-titel
2. `docs/bidrag-media/02-post.webp` - animerad POST-skärm ("WARNING: Vilopuls ej övervakad på 18 år.")
3. `docs/bidrag-media/03-graleet.webp` - animerad: läkarna grälar, Kardiologen välter bordet, moderatorn stryker påståendet
4. `docs/bidrag-media/04-appen.webp` - animerad: riktiga mobilappen med min riktiga data
5. `docs/bidrag-media/05-riggen.webp` - animerad: kroppen som PC-chassi
6. `docs/bidrag-media/06-health-status.png` - siffrorna som PC Health Status
7. `docs/bidrag-media/07-16gb.jpg` - 16 GB-gränsen, 3D-rendering
8. Riktigt foto: handleden med Pixel Watch vid tangentbordet (tas av mig)
9. Riktigt foto: Mac minin på skrivbordet (tas av mig)

## Video på YouTube

`docs/video/kropp64-trailer-1920x1080.mp4`, 55 s. Titel på YouTube: "Kropp64: HWiNFO för kroppen (SweClockers AI-tävling 2026)".
Olistad räcker. Beskrivning: "Min GPU har jag full koll på. Min vilopuls? Ingen aning. Så jag byggde HWiNFO för kroppen: Pixel Watch och 1177-journalen läses av sex AI-läkare som körs lokalt på en Mac mini 16 GB. De grälar, och en moderator i vanlig Python stryker allt som saknar källa. Allt i trailern är eget: kontorsscenen är inspelad ur appens egen motor, 3D i Blender, musiken syntetiserad i Python med hjärtslaget som takt. https://kropp64.se"

## Länk

https://kropp64.se

## Om dig

E-post, namn vid bidraget och SweClockers-användarnamn fylls i av mig.
