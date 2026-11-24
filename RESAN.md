# Resan

Dagbok över bygget. Skrivs medan det händer, inte i efterhand.

## Bakgrund

Köpte Mac minin (M4, 16 GB) under OpenClaw-trenden i januari 2026 och har kört agenter på den sedan dess.

**Vem som skrev koden.** Koden i repot är skriven av Claude Code-agenter (Claude Opus 5.5) som jag styr:
jag bestämmer vad som ska byggas och hur det ska bete sig, testar, underkänner och ber om om-tag. Agenterna
skriver koden, kör testerna och för den här dagboken medan de arbetar, flera parallellt (webb, klocka och
mobil, konsiliets kvalitet, granskning, presentation). Där det står "jag" nedan är det projektet som talar,
inte ett påstående om att jag skrev varje rad själv. Tokenåtgången redovisas med `tools/tokenredovisning.py`.

**Min roll.** Produktägare och grindvakt. Jag bestämde vad som skulle byggas och underkände resten: under
morgonens idésökning sa jag nej till ett dussintal förslag innan hälsoidén fick fortsätta, och jag krävde att
lösningen skulle vara agentisk från grunden, inte en chatt ovanpå en dashboard. När agenterna började
vänta på "riktig data senare" eller fylla ut med demosiffror styrde jag om: allt ska gå att köra på min egen
data, och varje siffra ska vara uppmätt. Jag valde också namnet.

**Namnet.** Arbetsnamnet var Konsiliet, tills jag såg att "konsilium" på svenska mest betyder kyrkomöte.
Överklockad testades en stund men kunde lika gärna vara namnet på vilket hårdvaruverktyg som helst. Det blev
Kropp64: en sensorpanel som AIDA64 och HWiNFO64, fast för kroppen. Internt heter koden fortfarande konsiliet.

## 2026-11-24

**Falsk start.** Min Discord-agent fick i uppdrag att bygga ett tävlingsbidrag och producerade på en timme
cirka 4 000 rader Python: en hälsoagent på påhittad data, med korrelationsmotor, larmkedja och ett snyggt terminaldemo.
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

**Klockappen klipptes av den runda skärmen.** Listan var en ScalingLazyColumn utan utfyllnad från ScreenScaffold,
så innehåll scrollade in under klockslaget överst och breda knappar och textrader sköts ut över cirkelns kant.
Fix: TransformingLazyColumn med ScreenScaffolds utfyllnad, SurfaceTransformation på knapparna (de krymper mot
kanten), samma krympning på textblocken plus extra sidomarginal, och klockslaget tonas bort så fort listan inte
står högst upp. Klockans skärmbilder är tagna om och maskerade till cirkeln som syns på en rund klocka.

**Serveradressen låg inbyggd i mobilappen.** Standardadressen var Mac minins Tailscale-adress, vilket inte hör
hemma i ett publikt repo. Nu finns ingen inbyggd adress: första gången visas en egen vy där adressen måste anges
och testas (med möjlighet att spara ändå om servern inte svarar just då). Utan adress görs inga anrop alls och
klockdata ligger kvar i kön tills adressen är satt.

**3D-renderingarna: Blender fanns inte längre på Lenovon.** Mappen med Blender 4.5.3 som tidigare projekt
använt var borttagen. Den officiella zip-filen laddades ner igen från blender.org (400 100 678 byte, SHA256
kontrollerad mot blender.org:s summa). Med den nya installationen kompilerades OptiX-kärnorna om: första
bilden i en testrendering tog 160 sekunder, nästa 2,4.

**Första hjältebilden var nästan vit.** Skrivbordet hade bara 3 % reflektans men blev ljusgrått, eftersom
lamporna var dimensionerade för ett rum och inte för en 13 cm stor dator. Exponeringen sänktes 3,2 steg och
aluminiumet fick sina ljusa ytor från två stora reflexskärmar som bara syns i speglingar och bara lyser på
Mac minin (light linking i Cycles), så att skärmarna på klocka och mobil inte bländades ut.

**Klockglaset blev ett förstoringsglas.** Den välvda glaskupan var modellerad som en massiv kropp med
brytningsindex 1,52, så urtavlan förstorades och förvrängdes som genom en lins. På riktigt är glaset tunt.
Lösning: glas utan brytning med ett klarlackslager för reflexerna.

**Rendertider på RTX 5050 (OptiX, denoising på GPU, adaptiv sampling, upp till 512 sampel):** hjältebild
1920x1080 55,1 s, 1080x1350 44,6 s, dataflödet 30,4 s, 16 GB-bilden 47,9 s. Skärmarna i hjältebilden är
en illustration med exempelvärden, inte uppmätt data.

**Röster i kontoret.** Läkarna i pixelkontoret kan nu höras, av som standard med en ljudknapp. Kravet var
lokalt och svenskt, utan att svälta språkmodellen (Qwen 3.5 9B tar runt 9 av 16 GB).
Första försöket var Piper (VITS på CPU) med de tre svenska rösterna i rhasspy/piper-voices (nst, lisa, alma,
63 MB styck) plus macOS Alva. Uppmätt på Mac minin: ren syntes RTF 0,03 (en sekund tal på 0,03 s), med
kodning och ljudnivå 0,05-0,10, Alva via `say` 0,3. Minne 90 MB per laddad röst, toppen i serverprocessen
340 MB med en röst i taget. Fonemdumpen visade att espeak (som Piper bygger på) läser "muskel" med sj-ljud och
"EKG" som ett ord, så normaliseringen fick rättelser. Men det finns bara en svensk mansröst i Piper, och tre
läkare på samma röst med flyttad tonhöjd lät som samma person också för en lyssnare utifrån.
Bytt till samma röster som ägaren använder i andra projekt: Parambe (Chatterbox Multilingual med svenska vikter)
som klonar röster ur en röstbank med 34 referensklipp, uppmätt 97 % rätt ord på svenska. Referensklippen i
röstbanken gjordes ursprungligen med ElevenLabs (syntetiska röster, gratisplan, icke-kommersiellt). Själva
syntesen sker lokalt, men rösterna är alltså inte "egna" och ska göras om innan något används kommersiellt.
Rösterna valdes ur bankens roller och mättes med Chatterbox röstavtryck (cosinuslikhet mellan klippen): Jan
(Trådstartaren), Melanie, Petra, Martin, Louise, Christopher, Kille-UGC2 (Trollet, kaxig) och Adam (Moderatorn,
torr radioröst). Inget par över 0,79. Lea, som låg närmast till hands för stressläkaren, låg på 0,82 mot Melanie
och Elin 0,77, så de valdes bort.

**Var rösterna görs.** Chatterbox på Mac minins MPS samtidigt som Qwen riskerar swap, så syntesen görs på
Lenovons RTX 5050 i en liten tjänst (`drift/rost_tjanst.py`). Uppmätt där: laddning 30-37 s, högst 5,3 GB
grafikminne, och tyvärr långsammare än realtid: RTF 1,6-3,6 när modellen är varm (en replik på 7 s tar 14-25 s).
En replik tog en gång 179 s för 8,6 s ljud, troligen för att grafikkortet delas med skrivbordet (1,7 GB) och
gick över till delat minne. Därför genereras nya repliker i bakgrunden så fort de hamnar i loggen (när någon
lyssnar), webben väntar högst 8 s på att ljudet ska börja och hoppar annars över rösten, och live hoppas rösten
över när händelserna ligger efter. Demon är förgenererad. Mac minins MPS är reserv bara när Qwen inte är laddad
och minst 45 % minne är ledigt, som en engångsprocess som avslutas efteråt. Den reserven är inte uppmätt: Qwen
var laddad under hela arbetet och jag ville inte lasta ur den mitt i en annan körning. Piper är sista reserv.

**Klonade röster är en missbruksrisk.** Första versionen av `/api/rost` tog `?agent=..&text=..`, vilket betyder
att vem som helst med åtkomst kunde få en klonad röst att säga vad som helst. Nu finns bara
`GET /api/rost/{event_id}`: servern slår upp en agent.say-händelse i händelseloggen och läser upp dess text med
den agentens röst, med samma behörighet som resten av API:t och högst 40 anrop i minuten per klient. Den publika
demon kör aldrig talsyntes: demomanusets 13 repliker är förgenererade till `web/public/demo-rost/<nr>.ogg`
(Opus) och demon har ingen `/api/rost`. Rösttjänsten på Lenovon lyssnar bara på Tailscale-adressen, svarar
bara Mac minins adress, kräver en delad hemlighet (fil utanför repot på båda datorerna), tar högst 600 tecken per
anrop och 3 jobb i kö. Tester i `server/tests/test_rost.py` visar att fri text avvisas och att det alltid är
loggens text som läses upp.

**Ett misstag i testningen.** Uppspelningen testades först med en Playwright-Chromium utan `--mute-audio`, och
den spelade rösterna i Mac minins högtalare. Ägaren hörde dem. All testning och inspelning görs nu ljudlöst:
`--mute-audio`, och ljudspåret i demofilmen mixas från filerna, inte från datorns ljudutgång.

**Ruta, komplikationer och widget: tre saker som inte fungerade som dokumentationen antyder.** Mobilen lägger
headroom och trådens läge som ett dataobjekt i Data Layer, klockan visar det i en ruta (tile) och två
komplikationer, och mobilen har en hemskärmswidget. Testat på emulatorerna mot en separat testserver med egen
databas (port 8798, aldrig 8790).
- *Data Layer på mobilemulatorn:* `putDataItem` gav `API_UNAVAILABLE` (Wear OS-appen saknas, samma orsak som
  att emulatorerna inte går att parkoppla), och en gång svarade anropet inte alls. Det hände i en
  BroadcastReceiver, så ett hängande anrop hade gett ANR. Fix: tidsgräns på 10 sekunder. Statusen flyttas i
  testet med `statusbrygga.ps1` (mobilen skriver exakt den JSON som lades i Data Layer, klockan lämnar den till
  samma kod som `onDataChanged`). Bluetooth-hoppet testas på riktig Pixel Watch.
- *Egen vibration med USAGE_NOTIFICATION släpps inte igenom av Wear OS.* `dumpsys vibrator_manager` visade
  `ignored_app_ops` för varje påminnelse och kvittens, medan akutmönstret (USAGE_ALARM) spelades i 4,3 s.
  Fix: rörelse- och kvittensmönstret ligger på notiskanalerna (nya kanal-id, eftersom kanaler inte kan ändras)
  och spelas av systemet. Verifierat i samma dump: 90-160-90 ms för AFK-påminnelsen och 280-140-70 ms för
  "Tråden löst", spelade av Wear-systemet. Dessutom: medan klockan laddar spelas inga notisvibrationer alls.
  Det såg först ut som att även kanalmönstren var trasiga, tills batteriet kopplades ur (`dumpsys battery unplug`).
- *`requestUpdate` för rutan gav ingen ny rendering* på klockemulatorn, varken direkt eller efter flera minuter.
  Rutan visade gammal status, och "Synkad nyss" stod kvar fast det var 20 minuter sedan. Fix: klockslag i
  stället för "nyss" (en ruta kan visas långt efter att den ritades), färskhetsintervall 5 minuter (då hämtar
  systemet en ny när rutan visas, verifierat: "Tråd pågår" kom fram efter intervallet), och en ny begäran när
  rutan visas med äldre data än senaste statusen (den händelsen sågs aldrig på emulatorn, så den är inte verifierad). Komplikationerna uppdaterades direkt.
- *Testskriptet körde inte alls en stund:* `timeout` finns inte på macOS, så mina anrop av bryggan föll tyst
  och jag letade fel i rutan. Lärdom: kontrollera att teststeget faktiskt kördes innan felet söks i appen.

**Tunneln gav 403 på allt.** När kropp64.se väl pekade på Cloudflare svarade app och demo "Ej tillgänglig".
Orsak: uvicorn litar som standard på X-Forwarded-For från localhost, och cloudflared sätter den headern, så
servern såg besökarens riktiga IP i stället för tunnelns 127.0.0.1 och blockerade det som "utifrån". Fix:
`--no-proxy-headers`. Tunneltrafik känns fortfarande igen säkert, eftersom bara anslutningar från localhost
släpps in och de kräver token när Cloudflares header finns. Matris efteråt: sajten 200, demo 200, app-API utan
token 401, med token 200, LAN 403.

## Landningssidan, andra försöket: "ser AI ut"

Ägaren tyckte att första versionen av kropp64.se såg ut som en mall: stor sansrubrik, två knappar, en
skärmbildsruta, mörkgrått. Det stämde. Allt på sidan kunde ha handlat om vad som helst. Omgjord så att
formspråket kommer ur projektets egen värld, hårdvarumonitorn och kroppen:

- **En egen bild i stället för en produktbild.** `render/sajt/` renderar ett kretskort i makro i Blender på
  Lenovon (Cycles, OptiX, 86 s för 2400x1600 i 384 sampel): en guldpläterad ledare formad som ett EKG går in i
  en processor som är lasergraverad Kropp64, lysdioden D7 sitter bredvid och fläktkontakten heter J4 Andning.
  Texturerna (lödmask, koppar, silkscreen, gravyr) ritas med PIL ur en gemensam layoutfil så att 3D-delarna
  hamnar på sina lödytor. Siffrorna på processorn är exempelvärden och står som det i bildtexten.
- **Värmekameran** är en AOV ("heat") i samma rendering, där varje material skriver ett värmevärde och kortet
  svalnar med avståndet från processorn. Den läggs genom en ironbow-palett, skalas ner till 320 px bred och
  tillbaka som en riktig värmekamera. Bildtexten säger att det är falsk färg, inte en mätning.
- **Typsnitt:** Familjen Grotesk (svensk, från byrån Familjen) och Martian Mono med smal bredd för
  avläsningar, båda självhostade, 59 kB tillsammans.
- **Ljust läge är ett datablad** (papper, millimeterrutor, korn), mörkt läge är lödmask. En accentfärg,
  signalorange. Akutavsnittet är ett rent block utan rutor, korn eller skämt.
- **Detaljerna:** POST-skärmen skrivs ut en gång per besök, sensortabellen tickar med syntetiska värden,
  lysdioden på bilden blinkar i 67 BPM, fläkten snurrar ett varv per andetag i demodatan, staplarna i
  "Uppmätt" ser ut som ett hårdvarutest, och läkarteamet visas som en riktig forumtråd ur demons manus med
  moderatorns strykning. Allt respekterar prefers-reduced-motion.
- **Vikt:** site/dist är 1,1 MB, varav kontorsfilmen 576 kB som laddas först när den syns. Första vyn är
  ungefär 200 kB. Ingen horisontell scroll på 375 px.

Riggvyn (three.js) var inte klar när sidan byggdes. Hjältebilden har en tydlig plats (`#riggvyn-plats`) där
vyn kan ersätta renderingen. Skärmbilder: `docs/skarmbilder/sajt-*.png`.

Ett misstag på vägen: första provrenderingen var kraftigt överexponerad, eftersom ljusstyrkorna från
hjältebilden (skrivbordsskala, 0,6 m) återanvändes i makroskala (0,2 m). Exponeringen sänktes 5 steg och en
reflexskärm som bara når processorlocket (light linking) gjorde gravyren läsbar utan att bränna ut kortet.
