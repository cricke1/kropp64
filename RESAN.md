# Resan

Dagbok över bygget. Skrivs medan det händer, inte i efterhand.

## Bakgrund

Köpte Mac minin (M4, 16 GB) under OpenClaw-trenden i januari 2026 och har kört agenter på den sedan dess.

**Vem som skrev koden.** Koden i repot är skriven av Claude Code-agenter (Claude Opus 5.5) som jag styr:
jag bestämmer vad som ska byggas och hur det ska bete sig, testar, underkänner och ber om om-tag. Agenterna
skriver koden, kör testerna och för den här dagboken medan de arbetar, flera parallellt (webb, klocka och
mobil, konsiliets kvalitet, granskning, presentation). Där det står "jag" nedan är det projektet som talar,
inte ett påstående om att jag skrev varje rad själv. Tokenåtgången redovisas med `tools/tokenredovisning.py`.

## 2026-11-24

**Falsk start.** Min Discord-agent fick i uppdrag att bygga ett tävlingsbidrag och producerade på en timme
cirka 4 000 rader Python: en "diabetesagent" med korrelationsmotor, larmkedja och ett snyggt terminaldemo.
Problemet: allt kördes på syntetisk exempeldata, journalformatet var påhittat, och demot innehöll siffror
som ingen hade mätt. Det såg imponerande ut men var en kuliss. Jag slängde storyn och började om här,
med kravet att allt ska köras på min riktiga data och att varje siffra ska vara uppmätt.

Lärdom: en agent som får "gör det imponerande" som mål optimerar för att det ska *se* imponerande ut.

**Arkitektur bestämd.** Egen Wear OS-app på klockan för realtid (Fitbit-synken kommer bara var 15:e minut),
Android-app som brygga, Mac minin som server bakom Cloudflare Tunnel, lokala modeller via Ollama.

**Tjänsten startade men svarade aldrig.** Som launchd-tjänst hängde servern tyst utan en enda loggrad.
Orsak: macOS skyddar Skrivbordet (TCC), och en process som startas av launchd får inte läsa där, inte ens
Python-miljön. Samma fel har bitit mig förut. Lösning: repot flyttat till ~/konsiliet med en symlänk kvar
på Skrivbordet, Python-miljön återskapad med nya sökvägar.

**Pixelkontoret: kod i stället för Blender.** Planen var att rendera kontoret och figurerna i Blender på
laptopen och pixla ner dem. Det blev i stället pixelgrafik ritad direkt i koden: figurerna är 16x24 px
ur textmallar med automatisk kontur, möblerna är rektanglar. Skälet: full kontroll över varje pixel,
inga stora bildfiler i appen, och figurerna kan byta pose (gå, sitta, prata, blinka) utan att rendera om något.

**Demon låtsades använda verktyg som inte finns.** Demomanuset skrevs innan servern hade riktiga verktyg och
hittade på namn som `labs` och `series`. När kontoret sedan styrdes av namnen gick kemisten till sitt
skrivbord i stället för till labbet. Demon använder nu serverns riktiga verktyg (`hamta_serie`, `hamta_labb`,
`sok_journal`, `hamta_somn`), så att demot och verkligheten ser likadana ut.

**Läkarna sprang fram och tillbaka.** Kontoret skickade automatiskt tillbaka en läkare till bordet efter
varje uppslag. Servern skickar samtidigt "gå till ditt skrivbord" mellan varje verktygsrunda, så på riktiga
möten pendlade de. Nu bestämmer servern var läkarna står; kontoret går bara själv tillbaka efter en tur till
arkivet eller labbet.

**Granskaren kan inte alltid peka på meningen.** Granskaren stryker påståenden ur läkarens strukturerade
bedömning, men det läkaren *säger* är en sammanfattning med andra ord. Webben hittar då inte meningen att
stryka i pratbubblan och visar strykningen som ett eget kort ovanför läkaren. Önskemål till servern om att
koppla strykningen till rätt yttrande står i docs/API-ONSKEMAL.md.

**Två agenter, samma testport.** Jag körde en testserver med egen databas på en ledig port. En annan
agent testade samtidigt mot samma port och plötsligt dök möten upp i min testdatabas som jag inte startat.
Ingen riktig data skadades, men det visar varför testskriptet för webben (web/dev/ingest.mjs) nu kräver att
man anger adressen uttryckligen: det ska inte gå att råka skriva syntetiska punkter i den riktiga databasen.

**Skrev över en annan agents fil.** Webbens API-önskemål skrevs till docs/API-ONSKEMAL.md, som mobilagenten
redan hade skapat. Upptäcktes i `git status` före commit; originalet återställdes och webbens önskemål
lades till som ett eget avsnitt.

**Första riktiga konsiliet: 278 sekunder och ingen bedömning.** Båda specialisterna fastnade i att hämta
data och lämnade aldrig någon bedömning. Kardiologen anropade ett verktyg som inte finns (`hamta_journal`),
stressläkaren hämtade samma HRV-serie tre gånger. 47 656 prompttokens: på Mac minin läser Qwen3.5 9B
prompten i 75 tokens/s men skriver i 17 tokens/s, så det är läsningen som äter tiden när en agent skickar
om hela samtalet vid varje steg. Fix: datan runt larmet hämtas innan specialisterna börjar, upprepade
anrop stoppas, och slutbedömningen tvingas fram som strukturerad JSON (Ollama format=schema) i stället
för att hoppas att modellen anropar rätt verktyg.

**Andra körningen: 563 sekunder, granskaren för sträng.** Nu kom bedömningar, men granskaren strök
"151 slag/min" (siffran kom från vaktens larm, som inte var registrerat som källa), klockslag som 16:10
och omräkningar som 450 min = 7,5 h. Den strök också helt korrekt ett påhittat baslinjevärde (73,2 när
källan sa 72,5). Fix: larmet blev en egen källa (U:utlosare), klockslag och perioder räknas inte som
mätvärden, enkla enhetsomräkningar godkänns. Sex enhetstester skrivna från de riktiga strykningarna.

**Ollama svarade 500 mitt i ett möte.** Loggen: "qwen3.5 tool call parsing failed: unexpected EOF".
Svaret klipptes vid tokentaket mitt i verktygsanropets XML. Samtidigt visade loggen minnestoppar på
15,3 GiB av 16: modellen som på pappret är 6,6 GB tog 14,7 GB med 16k kontext och Ollamas standardläge
med flera parallella förfrågningar. Datorn swappade. Fix: 8k kontext, en förfrågan åt gången, KV-cache i
q8_0 och flash attention. Modellen tar nu 9,1 GB och ett helt konsilium tar 250 sekunder i stället för 563.

**Port 8787 var redan upptagen.** En annan av mina nodeservrar (cricketrack, igång sedan 17 timmar) lyssnade på
8787, även på Tailscale-adressen. Uvicorn startade inte och testanrop fick "Cannot GET /api/health" från fel
server. Fix: Konsiliet flyttade till 8790. Emulatortesterna körs mot en egen serverinstans på 8797 med en
separat databas, så att syntetisk puls aldrig hamnar i min riktiga baslinje.

**Android-SDK:n installerades inte, utan felmeddelande.** Installationsskriptet i Windows PowerShell 5.1
körde sdkmanager med `*>>` till en logg och `$ErrorActionPreference = "Stop"`. PowerShell 5.1 gör varje rad
på stderr från ett externt program till ett fel, så skriptet dog vid licensfrågan och loggen sa bara
"extracted". Fix: samma steg i en .bat-fil med vanliga omdirigeringar.

**macOS-filer i Windowsbygget.** tar på Macen packade med `._`-filer (AppleDouble) för varje fil, och
Android-resurser som `._strings.xml` är ogiltiga. Fix: `COPYFILE_DISABLE=1 tar --no-mac-metadata`.

**Health Services 1.1.0 kompilerade inte.** 42 fel av typen "Cannot access class ListenableFuture".
Biblioteket exponerar Guavas ListenableFuture i sitt API men drar inte med det. Fix: lägga till
`com.google.guava:guava:33.3.1-android` i klockappen.

**Klock- och mobilemulatorn gick inte att parkoppla.** Wearable Data Layer kräver att mobilen har Wear OS-
eller Pixel Watch-appen, som bara finns i Play Butik och kräver inloggning med ett Google-konto. Det gör inte
min byggagent. Lösning för testet: en brygga som bara finns i debug-bygget. Klockan exporterar nästa batch
exakt som den annars skickas över Bluetooth, adb flyttar den till mobilen, mobilen sparar den med samma kod
som tar emot riktiga batchar och skriver en kvittens, och först då raderar klockan raderna. Allt utom själva
Bluetooth-hoppet är alltså testat. Data från emulatorn märks `watch-emulator` hela vägen och visas som
"testdata från emulator" i appen. Det riktiga Bluetooth-hoppet testas på min Pixel Watch.

**Kedjan testad på emulatorer (syntetisk data från Health Services testläge):** klockan registrerade 13
passiva datatyper (puls, steg, kalorier, våningar, sträcka, höjdmeter, aktivitetsläge, falldetektering m.fl.,
men varken HRV eller SpO2: de finns inte passivt i Health Services, bara via Health Connect). 855 punkter gick
klocka till mobil till server. Sedan stängde jag av mobilens nät: 360 nya punkter låg kvar i mobilens kö, servern
stod still på 855. Nätet på igen: alla 1 215 fanns på servern 2 sekunder senare, utan dubbletter. Sedan stängde
jag av servern, skickade 180 punkter till och startade om mobilen: efter omstart och server uppe igen kom de
fram efter 40 sekunder. Träningspass med ExerciseClient startade och avslutades och puls kom varje sekund.

**Sms-larmet kom 70 sekunder för sent.** Med testlarm och 2 minuters frist gick sms:et först efter drygt
3 minuter. Android 14+ ger inte exakta alarm utan att användaren godkänt det, och då får alarmet ett fönster
på 1,5 minut. Fix: `USE_EXACT_ALARM`, eftersom fristen är en säkerhetsfunktion.

**WHPX.** Windows-funktionen "HypervisorPlatform" stod som avstängd på Lenovon, men emulatorn rapporterade
"WHPX is installed and usable" (Hyper-V och virtualiseringsbaserad säkerhet var redan igång) och båda
emulatorerna startade med hårdvaruacceleration. Ingen omstart behövdes.

**Träningspass till servern och omtest av sms-fristen.** Servern fick `POST /api/ingest/exercise`. Klockan
behöll sitt protokoll (passmarkörer i samma kö med kvittens) och skickar nu passtypen som text, mobilen gör om
markörerna till ett pass och skickar det vid start med `end = null` och igen vid slut med samma id. Mobilens
databas fick en ny tabell med en riktig migrering, inte en destruktiv, så att kön överlever uppdateringen.
Testat på emulatorerna mot testinstansen: passet "promenad" kom in med tomt slut och fick sluttid tre minuter
senare med samma id. Larmtestet kördes om med `USE_EXACT_ALARM`: alarmet stod som exakt (fönster 0) och sms:et
skickades 39 millisekunder efter fristen, i stället för 70 sekunder sent som förra gången.

**Säkerhetshål hittat i granskning.** En separat agent fick granska hela projektet som en skeptisk
forumanvändare. Den verifierade att vem som helst på mitt hemnätverk kunde läsa journalen och skicka in
falsk puls genom att lägga till en påhittad header (`Cf-Access-Authenticated-User-Email`), eftersom
servern litade på den headern utan att kontrollera var den kom ifrån. Med falsk puls 150 i vila hade
man kunnat utlösa akutlarm. Fix: headern ger inte längre någon åtkomst, allt utanför localhost och
Tailscale får 403, Host-headern kontrolleras (DNS rebinding), WebSocket kontrollerar Origin, token
jämförs i konstant tid och syns inte längre i loggen. Mottagningen avvisar orimliga värden (puls 400,
NaN, tidsstämplar i framtiden). Testat: LAN med falsk header 403, tunnel utan token 401, falsk Host 421.

**Vakten kunde inte se data som kom sent.** Samma granskning: alla regler räknade bakåt från "nu",
men SpO2, HRV och hudtemperatur kommer via Health Connect, som Fitbit ofta synkar timmar senare. Larmet
"SpO2 under 88 %" kunde alltså i praktiken aldrig slå till. Vakten utvärderar nu på mätpunkternas egen
tid. Något som hände för mer än 30 minuter sedan blir "upptäckt i efterhand" och aldrig akut, så att
mobilen inte skickar sms om något som redan är över. Baslinjen för puls bygger nu bara på vilominuter
(inga steg, inget träningspass), räknas om var sjätte timme och sparas i databasen (ett varv tog
tidigare tiotals sekunder med 1 Hz-data, nu 0,1 s). Nätter definieras av sömnpassen i stället för
klockan 00-06, som passar dåligt för någon som kodar till två. Nedkylningen överlever omstart.
Källprioriteten (klockappen före Health Connect) gäller per minut i stället för per fönster, så att
historik från innan klockappen installerades inte kastas. Sex nya tester.

**1177-hämtaren litade för mycket på sig själv.** Granskningen visade att inloggningskontrollen var sann
redan före BankID (adressen journalen.1177.se syns direkt), att hämtaren klickade på alla knappar med
aria-expanded (menyer, språkval) och följde alla länkar, och att kontrollen av den lokala modellens
tolkning var trasig: `"" in sidtext` är alltid sant, så en tom analys passerade, och anteckningstexten
kontrollerades inte alls. Ett test jag skrev hittade dessutom att ett felparat provvärde ("Ferritin
141 g/L", där 141 egentligen var Hb) slank igenom. Fix: inloggning kräver en "Logga ut"-knapp,
expandering bara inom huvudinnehållet, bara journallänkar följs, modellens anteckningar måste vara
avskrivna (80 % av orden finns i sidan) med ett datum som står i sidan, och analys och värde måste stå
på samma rad med värdet som ett helt tal. Stabila id så att en ny hämtning inte ger dubbletter, och
två likadana prover samma dag slås inte längre ihop. Tre tester med en fiktiv journalsida.

**Gamla larm kunde väcka sms-kedjan igen.** När mobilen återansluter skickar servern de senaste 300
händelserna, inklusive gamla akutlarm. Omskickade händelser märks nu `replay: true`.

**Granskningen hittade ett hål i sms-kedjan.** Mobilen hade bara en plats för ett väntande sms. Ett andra
akutlarm, till exempel konsiliets bedömning några minuter efter vaktens larm, skrev över det första och flyttade
fristen framåt, så sms:et kunde skjutas upp gång på gång. Dessutom kunde konsiliets larm, alltså en språkmodells
slutsats, starta sms-kedjan. Fix: reglerna bröts ut till en egen klass med enhetstester (8 st). Fristen sätts av
första olösta akutlarmet och flyttas aldrig, senare larm läggs till i samma sms, bara larm med en vaktregel kan
starta sms, larm "upptäckt i efterhand" och larm äldre än 30 minuter ger aldrig sms, och händelser som servern
skickar om vid återanslutning (märkta `replay`) ger varken notis eller sms. Testat mot en separat testinstans:
vaktlarm A, en minut senare vaktlarm B, konsiliets larm C och ett larm i efterhand D. Kedjan fick A och B, fristen
stod kvar på A plus två minuter, C och D gav bara notis, och ett sms om två larm gick 32 millisekunder efter
fristen. Efter omstart av servern skickades historiken om, och inget nytt sms-alarm eller ny notis skapades.

**Omskickad historik: varken missade eller dubbla larm.** Att helt bortse från omskickade händelser gav ett nytt hål:
ett akutlarm som kom under några sekunders avbrott i anslutningen kom bara fram som historik och gav ingen notis alls.
Fix: appen sparar id:n för hanterade händelser (de senaste 500) och deduplicerar allt på id. Omskickade `alert.raise`
yngre än 5 minuter som inte redan hanterats behandlas som live, med sms-fristen räknad från larmets egen tid.
Fem nya enhetstester (totalt 13). Testat mot separat instans: mobilens nät av, akutlarm E publicerat, nät på efter
40 sekunder. Larmet kom fram som historik, gav notis, och fristen blev larmets tid plus två minuter (inte mottagningstid
plus två). Sms:et gick 20 millisekunder efter fristen. Servern startades sedan om medan larmet fortfarande var under
5 minuter gammalt: historiken skickades om men gav ingen ny notis och ingen ny sms-kedja.
