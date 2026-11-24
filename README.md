# Konsiliet

Ett läkarteam av lokala AI-agenter som bevakar min hälsodata från klockan, på en Mac mini M4 med 16 GB.

När något i datan avviker från min egen baslinje kallas teamet in: en ordförande, de specialister som behövs,
en djävulens advokat och en granskare. De läser samma data och journal, och varje påstående de gör måste peka
på en mätpunkt, en journalrad eller ett provsvar. Granskaren är vanlig kod, inte en språkmodell, och stryker
allt som inte går att belägga. Det som blir kvar är ett underlag med frågor att ta med till vården, aldrig en
diagnos. Allt körs på Mac minin. Ingen hälsodata skickas till någon molntjänst.

I webben syns mötet som ett pixelkontor där läkarna går till arkivet, slår upp kurvor och pratar med varandra.

![Arkitektur](docs/arkitektur.svg)

## Status

Ärligt läge den 24 november 2026:

- Hela kedjan klocka, mobil, server, vakt och konsilium fungerar och är testad på emulatorer och syntetisk
  testdata (se [RESAN.md](RESAN.md)). Den har ännu inte gått länge på min riktiga klocka, så det finns inga
  resultat från riktig data att visa än.
- Utvärderingen av konsiliet pågår. Den första mätningen (3 scenarier) gav rätt brådska i 1 av 3 fall och
  missade det akuta fallet. Senaste siffror: [eval/RESULTAT.md](eval/RESULTAT.md) och `eval/resultat/`.
- Alla skärmbilder och filmer i repot är märkta som demo, syntetisk testdata eller emulator.

## Varför lokalt

Puls dygnet runt, sömn, journalanteckningar och provsvar från 1177 är bland det känsligaste som finns om en
människa. Jag vill inte skicka det till en molnmodell för att få en sammanfattning. En Mac mini med 16 GB räcker
för en 9B-modell om man är snål med minnet, och det är just begränsningen som gjort bygget intressant: allt i
konsiliet är format efter att en modell som läser prompten i ungefär 75 tokens/s och skriver i 17 tokens/s ska
hinna klart innan nästa larm.

Molnet (Claude Code) användes bara för att bygga koden. Ingen hälsodata gick dit.

## Varför agenter, och var det inte är agenter

Ett larm om hög nattpuls kan förklaras av ett träningspass, kort sömn, en infektion på väg, en klocka som sitter
löst eller något som faktiskt behöver undersökas. Att väga sådant mot varandra passar ett team där var och en
slår upp sin del och någon annan försöker motbevisa.

Men det som måste vara rätt varje gång är inte en språkmodell:

- **Vakten** är regler och statistik. Akuta larm (t.ex. puls över 140 i vila, SpO2 under 88 %, klockans
  fall-larm) går till mobilen på millisekunder utan att vänta på någon modell. Bara de reglerna kan leda till
  sms till en anhörig.
- **Faktabladet** räknas fram i kod innan mötet: observerat mot baslinje, nätter, prover, med en referens per del.
- **Granskaren** är deterministisk kod. Ingen modell kan prata sig förbi den.
- **Brådskan** styrs av regelverket. Teamet kan justera inom en ram men aldrig ge "kontakta vården nu" om inte
  en akut vaktregel slagit till.

## Ett konsilium, steg för steg

Koden finns i [server/src/konsiliet/konsiliet.py](server/src/konsiliet/konsiliet.py).

1. **Utlösare.** Vakten hittar en avvikelse (robust z-poäng mot min egen baslinje för samma timme på dygnet,
   28 dagar bakåt, med puls bara från vilominuter), eller så ställer jag en fråga.
2. **Faktablad.** Räknas fram deterministiskt. Varje del får en referens (`F:puls`, `F:natter`, `F:prover` ...),
   och verktygsuppslag ger egna: `S:hr:<start>-<slut>` (serie), `B:` (baslinje), `J:` (journal), `L:` (provsvar),
   `N:` (natt).
3. **Ordföranden** (allmänläkare) läser utlösaren och faktabladet och kallar in 2-4 av kardiolog, sömnläkare,
   idrottsläkare, stressmedicin och klinisk kemist.
4. **Specialisterna** lämnar varsin bedömning som strukturerad JSON (Ollama `format` med JSON-schema). Varje
   påstående har en lista med källor, och schemat låser källorna till referenser som faktiskt finns i mötet.
   De kan slå upp mer med verktyg: `hamta_serie`, `jamfor_baslinje`, `hamta_somn`, `sok_journal`, `hamta_labb`.
5. **Granskaren** prövar varje påstående (se nedan). Det som stryks syns som en överstruken mening i kontoret.
6. **Djävulens advokat** letar vardagliga och tekniska förklaringar, med källor. Specialisterna bemöter dem.
7. **Ordföranden** skriver slutbedömningen. Den granskas igen, mening för mening, och brådskan sätts av
   regelverket.
8. Allt sparas med transkript, bevis och tokenåtgång. Varje steg sänds som en händelse på en buss, och det är
   de händelserna som styr figurerna i kontoret.

### Granskaren

`kontrollera()` i konsiliet.py stryker ett påstående om något av detta gäller:

- det saknar källa, eller källan finns inte bland det mötet faktiskt hämtat
- en siffra i texten finns inte bland källans värden. Siffror med enhet jämförs mot rätt sorts värden (puls
  mot puls, procent SpO2 mot SpO2). Avrundning och enkla omräkningar som minuter till timmar godkänns. Klockslag,
  datum och perioder räknas inte som mätvärden.
- ett tal kallas baslinje men är inget baslinjevärde i källan
- en slutsats (t.ex. om rytm, infektion eller syresättning) saknar källa av rätt typ

Ett verkligt exempel från bygget: en specialist skrev att baslinjen var 73,2 när källan sa 72,5. Granskaren
strök det. Den var också för sträng i början och strök klockslag och omräkningar som 450 min = 7,5 h. Båda
fallen finns nu som enhetstester i [server/tests/test_granskare.py](server/tests/test_granskare.py).

Granskaren kontrollerar att det som sägs finns i datan. Den kan inte avgöra om en medicinsk tolkning är klok.
Det är därför slutsatser kräver källa av rätt typ och brådskan inte bestäms av modellen.

## Uppmätt

Bara siffror som finns i en fil i repot.

| Vad | Värde | Källa |
|---|---|---|
| qwen3.5:9b, generering | 17,4 tokens/s | [bench/resultat/qwen3.5_9b.json](bench/resultat/qwen3.5_9b.json) |
| qwen3.5:9b, promptläsning | 75,4 tokens/s | samma |
| qwen3.5:9b, laddningstid / minne i benchen | 20,5 s / 7,21 GB | samma |
| Rätt verktyg valt på 10 testfrågor | 9 av 10 (rätt argument 8 av 10), median 1,38 s | samma |
| Första riktiga konsiliet | 278 s, ingen bedömning, 47 656 prompttokens | [RESAN.md](RESAN.md) |
| Minne för modellen med 16k kontext och parallella förfrågningar | 14,7 GB av 16, datorn swappade | RESAN.md |
| Efter 8k kontext, en förfrågan åt gången, KV-cache q8_0, flash attention | 9,1 GB, ett konsilium 250 s i stället för 563 s | RESAN.md |
| Första utvärderingen, 3 scenarier | rätt brådska 1 av 3, median 228 s, i snitt 19 960 prompt- och 3 482 ut-tokens | [eval/resultat/2026-11-24-baslinje.json](eval/resultat/2026-11-24-baslinje.json) |
| Nätavbrott i kedjan (emulatorer) | 360 punkter köade i mobilen, alla 1 215 på servern 2 s efter att nätet kom tillbaka, inga dubbletter | RESAN.md |
| Sms-frist efter akut larm, med exakta alarm | sms skickat 39 ms efter fristen (tidigare 70 s för sent) | RESAN.md |

Tokenåtgången, både Claude Code under bygget och de lokala modellerna, räknas fram ur loggarna med
`python3 tools/tokenredovisning.py`. Skriptet redovisar input, output, cache-skrivning och cache-läsning var för
sig och beskriver exakt hur avgränsningen görs.

## Kör själv

Kräver macOS på Apple Silicon (andra system bör fungera för servern men är inte testade), [Ollama](https://ollama.com),
[uv](https://docs.astral.sh/uv/) och Node 20+.

```sh
# modellerna
ollama pull qwen3.5:9b
ollama pull medgemma:4b          # valfri kunskapskälla

# Ollama-inställningarna som gör att 9B-modellen ryms (en förfrågan åt gången, q8_0, flash attention)
cp drift/se.konsiliet.ollama-env.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/se.konsiliet.ollama-env.plist
# starta om Ollama efteråt

# webben
cd web && npm install && npm run build && cd ..

# servern, på 127.0.0.1:8790 med databasen i ~/.konsiliet/konsiliet.db
cd server && uv sync && uv run uvicorn konsiliet.api:app --host 127.0.0.1 --port 8790
```

Öppna http://127.0.0.1:8790. Utan klocka finns inget att visa förutom demoläget i kontoret
(`#/kontoret?demo=1`). För att se resten med syntetisk data, starta en **separat** testserver med egen databas
och fyll den med `web/dev/ingest.mjs` (instruktioner överst i filen). Kör aldrig testskriptet mot den riktiga databasen.

Som tjänst som startar med datorn: [drift/se.konsiliet.server.plist](drift/se.konsiliet.server.plist). Klock-
och mobilappen byggs och installeras enligt [docs/MOBIL.md](docs/MOBIL.md).

Tester: `cd server && uv run pytest`.

### Publik demo

`drift/publik-demo.sh` startar en helt separat instans på 127.0.0.1:8795 med en engångsdatabas som fylls med
7 dygns syntetisk data, och en webb som är låst i demoläge med en banner på varje sida. Där är språkmodellen,
vakten, rutinerna, datorkopplingen, 1177-hämtningen och WebSocket avstängda, och utifrån går bara läsande
anrop. Databasen raderas när skriptet avslutas. Skriptet startar ingen tunnel; det gör man själv om man vill
visa demon utåt.

## Integritet

- All data ligger i en SQLite-fil på Mac minin. Språkmodellerna körs i Ollama på samma dator.
- Klockan pratar bara med mobilen (Bluetooth). Mobilen pratar bara med Mac minin, över Tailscale.
- Servern lyssnar på alla gränssnitt för att Tailscale ska nå den, men svarar bara localhost och Tailscale-nätet.
  Allt annat får 403. Host-headern kontrolleras (skydd mot DNS rebinding), WebSocket kontrollerar Origin, och
  mobilen skickar en enhetstoken.
- Åtkomst utifrån via Cloudflare Tunnel med Cloudflare Access är planerad men inte uppsatt. Servern har stöd
  för tunneln (anrop via tunneln kräver token), men i dag går allt över Tailscale.
- 1177 hämtas med mitt eget BankID i en lokal webbläsare. Journalen sparas bara på Mac minin.
- Datorkopplingen sparar bara kategorin på programmet i fokus (kod, spel, chatt, webb, annat), aldrig
  fönstertitlar eller innehåll.
- Sms till anhöriga är avstängt tills man själv slår på det, och skickas bara efter ett akut larm som man inte
  kvitterat inom vald tid.

## Begränsningar

- Det här är inte en medicinteknisk produkt och ställer inga diagnoser. Den kan missa saker och den kan larma i
  onödan. Vid akuta besvär: ring 112.
- Utvärderingen är liten än så länge och visar att konsiliet kan sätta fel brådska. Det är skälet till att
  akuta larm aldrig går via språkmodellen.
- HRV, SpO2, andningsfrekvens och hudtemperatur finns inte passivt i Wear OS Health Services. De kommer via
  Health Connect när Fitbit-appen synkar, ofta timmar senare. Vakten utvärderar därför på datans egen tid, och
  något som upptäcks i efterhand blir aldrig akut.
- En 9B-modell på 16 GB är långsam: ett konsilium tar runt fyra minuter.
- Baslinjen behöver några veckors data innan avvikelser betyder något.
- Bluetooth-hoppet mellan klocka och mobil är testat på riktig hårdvara först när appen körs på min Pixel Watch;
  på emulatorerna ersattes det av en testbrygga (se RESAN.md).

## Delar

| Mapp | Vad |
|---|---|
| [server/](server/) | FastAPI, SQLite, vakt, konsiliet, granskare, 1177-hämtare, besöksunderlag som PDF |
| [web/](web/) | Preact och Vite. Pixelkontoret ritat i kod, översikt, konsilier, fråga, systempanel |
| [wear/](wear/) | Wear OS-appen för Pixel Watch |
| [android/](android/) | Mobilappen: brygga, Health Connect, larm, sms |
| [bench/](bench/) | Mätningar av lokala modeller |
| [eval/](eval/) | Utvärdering av konsiliet mot scenarier med facit |
| [drift/](drift/) | launchd-tjänster och den publika demon |
| [tools/](tools/) | Tokenredovisning och bildmärkning |
| [docs/](docs/) | Arkitektur, mobil och klocka, API-önskemål, märkta skärmbilder, bidragsbilder |

## Hur det byggdes

Koden är skriven av Claude Code-agenter (Claude Opus 5.5) som jag styrt: jag bestämde vad som skulle byggas,
testade och underkände, agenterna skrev koden och körde testerna, flera parallellt. Allt som gick fel på vägen
står i [RESAN.md](RESAN.md), inklusive en första version som såg imponerande ut men byggde på påhittade siffror
och därför slängdes.
