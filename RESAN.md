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
1920x1080 55,1 s, 1080x1350 44,6 s, dataflödet 30,4 s, 16 GB-bilden 47,9 s. Animationen (8 s, 240 bilder i 1920x1080)
tog 61 minuter, 15,3 s per bild i snitt; bilderna med klocka och mobil i oskärpa var långsammast (upp till
40 s). Skärmarna i hjältebilden är
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
Lenovons RTX 5050 i en liten tjänst (`drift/rost_tjanst.py`). Uppmätt där med Lenovon i övrigt ledig: laddning
25-37 s, högst 5,3 GB grafikminne, och långsammare än realtid: RTF 1,6-3,6 (en replik på 7 s tar 14-25 s).
Modellen samplar runt 13 taltoken i sekunden på det här kortet, och 25 token blir en sekund tal.
Problem på vägen:
- En replik på 7 s tog 119 s. Chatterbox tillåter alltid 1000 taltoken, och ibland hittar modellen inget slut.
  Tjänsten sätter nu ett tak efter textens längd (25 token per sekund, svenska runt 14 tecken per sekund,
  dubbel marginal).
- Tjänsten dog tyst vid start, gång på gång. Med `-X faulthandler` syntes "access violation" när safetensors
  läste den minnesmappade viktfilen, och sedan "The paging file is too small". Lenovon delas med andra jobb
  (tre Android-emulatorer, Blender och en Whisper-tjänst som reserverat 18 GB), och sidfilen tog slut.
  Fix: modellerna byggs direkt på grafikkortet och vikterna läses tensor för tensor med vanliga filläsningar
  (kontrollerat mot safetensors egen läsare: alla 2 798 tensorer lika). Tjänsten startas av en .bat som
  försöker igen efter 60 s om den ändå faller.
- När Lenovon var hårt belastad av de andra jobben blev RTF 15-30 (en replik på 3,6 s tog 91 s).
- Mellan meningarna lade tjänsten först in 0,22 s digital tystnad. Ägarens egna erfarenheter med samma röster
  (i en annan skill) är att digital tystnad hörs som konstiga pauser. Nu 0,17 s brus på nivå med tagningens
  eget brusgolv, och demons repliker är omgjorda.
Därför genereras rösterna i förväg: nya repliker så fort de hamnar i loggen (när någon lyssnar), och när ett
gammalt konsilium spelas upp resten av dess repliker i tur och ordning. Webben väntar live så länge inget annat
händer (upp till 90 s) och hoppar över rösten så fort nästa händelse väntar, och väntar upp till 40 s i
uppspelning. Demon är förgenererad. Mac minins MPS är reserv bara när Qwen inte är laddad och minst 45 % minne
är ledigt, som en engångsprocess som avslutas efteråt. När jag skulle mäta den reserven startade mätningen i en kort lucka
mellan två utvärderingskörningar, och sedan laddades Qwen igen mitt i: datorn swappade 6 GB innan jag
avbröt. Kontrollen vid start räckte alltså inte. Nu bevakas MPS-jobbet varannan sekund och dödas direkt om
en språkmodell laddas eller minnet sjunker under 20 % (test i test_rost.py). MPS-reservens hastighet är
därför fortfarande inte uppmätt här; ägarens tidigare körningar av samma modell på Macen tog runt en minut
per replik. Piper är sista reserv, och testad: med Lenovon nere
svarade `/api/rost/{id}` med Piper-röst efter 4,3 s (3 s väntan på Lenovon) och sedan direkt i 60 s utan att
fråga Lenovon igen. Kvaliteten kontrollerades genom att en annan modell (Gemini) fick lyssna på demons 13
repliker mot manuset: alla ord och tal rätt, en replik hade en paus mitt i "hjärtmuskelinflammation" och
gjordes om. Före bytet till utskrivna bokstäver lästes "H R V" som "å r v".

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


**Konsiliets kvalitet, kväll och natt 24-25 november.** Allt nedan är uppmätt med eval/ (siffrorna i eval/RESULTAT.md).

**Konsiliet fick ett facit: 15 scenarier med känt rätt svar.** Att konsiliet "verkade mediokert" gick inte att
förbättra utan att mäta. eval/ har nu en syntetisk person (minutupplöst simulering av 28 dygn: sömn, gång,
löppass, datoranvändning styr puls, HRV, SpO2, hudtemperatur och andning) och 15 scenarier: äkta pulsrusning i
vila, löppass, isolerade sensorspikar, löst sittande klocka, HRV-fall före förkylning, kort sömn av sent spelande,
nattliga syrefall, aktiva mot stillasittande dagar, allt normalt, "varför är jag så trött?", lågt ferritin,
träning eller infektion, lågt syre med astma, återkommande pulshopp och stress under en projektvecka. Varje
scenario har rätt brådska, fynd som måste finnas och påståenden som inte får göras. All data är märkt
`syntetisk`, ligger i slängbara databaser under eval/tmp/ och klockan i testprocessen flyttas till scenariots
tid (03:40 för syrefallen, 21:40 för pulsrusningen). Vakten får själv titta på datan, och dess larm fryses i
eval/utlosare.json så att alla varianter får exakt samma utlösare.

**Baslinjen: 40 procent rätt brådska, 300 sekunder.** Den gamla pipelinen (commit bf2001e) fick godtagbar brådska
i 6 av 15 fall, 6 undertriage och 3 övertriage, 64 % av måste-fynden, median 300 s (max 481) och i snitt 22 474
prompt- och 4 300 utdatatokens per möte. Felen var inte slumpmässiga utan systematiska:
- Pulsrusningen (167 i vila i 14 minuter) blev "ingen": specialisterna läste ett tvåtimmarsfönster där medianen
  72 dränkte episoden.
- Löst sittande klocka blev "kontakta_vard_nu". Advokaten skrev faktiskt att hoppen var fysiologiskt orimliga och
  tydde på mätfel, men ingen lyssnade.
- "Varför är jag så trött?" (5 h 50 min sömn i elva nätter) blev "kontakta_vard_nu", och modellen läste medianen
  per mätpunkt som "105 steg per vecka".
- Lågt ferritin blev "ingen": ingen specialist slog upp provsvaren. Förkylningen blev "ingen": ingen tittade på
  hudtemperaturen.
Sju av baslinjescenarierna kördes om senare utan swap (se nedan), och det nya scenariot om spelkvällar lades till:
då blev det 9 av 16 godtagbara (56 %), median 290 s. Samma scenario kunde dessutom ge olika brådska vid omkörning
(pulsrusningen blev "kontakta_vard_nu" andra gången, sensorspikarna "kontakta_vard_nu" i stället för
"ta_upp_med_varden"): den gamla pipelinen var inte bara fel utan slumpmässig.

**Faktablad före språkmodellen.** fakta.py räknar allt deterministiskt innan någon modell läser: observerat_*
mot baslinje_* och skillnad_* (så att 65 inte kan kallas baslinje när baslinjen är 73,4), kvalitetskontroller
(isolerade spikar, hopp över 25 slag mellan minuter, saknade minuter), träningspass som överlappar, pulsepisoder i
vila idag, sju nätter mot 21 tidigare (HRV, nattpuls, hudtemperatur, andning, syrefall per timme), dygn med steg
och datorminuter efter 23, senaste provsvar mot referens och journal. Varje del är en källa (F:larm, F:natter ...)
och källorna i modellens svar är låsta till mötets ref:ar med JSON-schema, så att påhittade ref:ar inte längre går
att skriva. Samma systemprompt (regler + faktablad) i alla anrop gör att Ollama kan återanvända prefixen.
Resultat (v2): 15 av 15 godtagbar brådska, 87 % exakt, täckning 78 %, median 138 s.

**Granskaren blev skarpare, och då syntes nya fel.** Ref-strängar och unix-tider räknas inte längre som belägg
(tidigare godkändes i princip varje tiosiffrigt tal), siffror matchas mot rätt mätvärde ("HRV 65 ms" med en
pulskälla stryks), talet efter ordet "baslinje" måste vara ett baslinjevärde, små tal kontrolleras, medicinska
slutsatser ("tyder på infektion", "järnbrist") kräver en källa av rätt typ, och slutbedömningens egen text
granskas. Första körningen strök 26 % av påståendena, och mycket av det var granskarens fel: gränser i fältnamn
(minuter_over_140), "13 148" lästes som 13 och 148, "51-55" som -55, "72,5" efter ordet baslinje klipptes till 72,
och "4525 minuter vid datorn" slapp igenom för att minuter räknades som en period. Det sista var ett riktigt
modellfel: 4525 var dagens steg. Varje fel fick ett test (granskaren har nu 29 tester, regelverket 12). Ett nytt riktigt fel som
fångades: källan sa att HRV var 4,3 ms HÖGRE, specialisten skrev "sjunkit med 4,3". Nu kontrolleras tecknet.

**Brådskan efter öppna regler, med larmspärr.** fakta.regelbradska har uttryckliga tumregler (puls i vila över
140 utan pass, steg eller mätfel; SpO2 under 90; provsvar utanför referens; minst 5 syrefall per timme flera
nätter; HRV-fall; medelsömn under 6 h). Bara en akut vaktregel kan leda till kontakta_vard_nu, och utan belagda
påståenden blir det minst bevaka. Ärligt: reglerna skrevs av samma hand som scenarierna, så de 100 procenten säger
mer om att reglerna täcker mina scenarier än om verkligheten. Därför skrevs fem holdout-scenarier EFTER att
reglerna frystes (se nedan). Och mätningen visade något oväntat: med faktabladet fick teamet rätt brådska i 15 av
15 även när det valde fritt (v3-fri) eller när regeln bestämde helt (v3-regel). Det såg ut som att faktabladet gjorde
hela jobbet, men det var fel slutsats: även v3-fri såg regelverkets tolkning, som en rad (F:tolkning) i
faktabladet. När den raden också togs bort (v4-utan-regler) föll godtagbar brådska till 11 av 15 med 4
undertriage: pulsrusningen i vila blev "bevaka", syrefallen och det låga ferritinet blev "bevaka",
förkylningen "ingen". Täckningen av fynden var nästan densamma (85 % mot 86 %). Språkmodellen hittar alltså rätt
fynd ur faktabladet men väger dem för lågt; reglerna är det som gör brådskan rätt.

**Kortare svar, färre specialister: 117 sekunder.** Tiden går nästan helt åt till att skriva: Qwen läser
promptar i cirka 390 tokens/s men skriver i cirka 22. Ordföranden ombads välja helst två specialister och skriva
uppdrag på högst 20 ord, specialisterna en mening och högst tre påståenden. v3: median 117 s (från 300), 1 760
utdatatokens (från 4 300), 5,7 modellanrop (från 9,9), fortfarande 15 av 15.

**Qwen växte till 15 GiB och datorn swappade.** Mitt i baslinjekörningen gick mötena från 224 till 481 sekunder.
`ollama ps` visade qwen3.5:9b på 15,4 GiB med 8k kontext, mot 8,3 GiB direkt efter laddning, och 12 GB swap.
Efter urladdning sjönk swappen till 3,8 GB. Utvärderingen laddar nu ur modellen före varje scenario så att
tiderna går att jämföra; de fem första baslinjescenarierna kördes innan dess och deras tider är därför för höga.
I drift laddar konsiliet nu ur modellen efter ett möte om den
vuxit över 11 GiB (llm.lasta_ur_om_for_stor); nästa möte laddar den ren på några sekunder i stället för att datorn
swappar i minuter.

**Diskussionen gav ingenting mätbart.** Specialisterna bemöter nu advokaten (en replikrunda där teamet håller med
eller pekar på fältet som motsäger). Utan rundan: samma 15 av 15, täckning 77 % mot 76 %, och 9 sekunder snabbare.
Den finns kvar för att den gör mötet begripligt i kontoret, inte för att den höjer kvaliteten.

**Tänkande i slutbedömningen gjorde det sämre.** Med think på för ordföranden tog slutbedömningen 2 500 tokens
(taket) och 100 sekunder, mötet 210 s, och exakt brådska sjönk från 5 av 5 till 3 av 5 på samma scenarier: modellen
resonerade sig till "bevaka" för ett löppass och för enstaka sensorspikar. Avbröts efter fem scenarier.

**Inget gemma4 på den här datorn i dag.** gemma4:12b (8 GB) laddades ner till 90 % när disken tog slut: 1,6 GB
ledigt, eftersom swappen åt resten. Tre baslinjescenarier kraschade med "No space left on device". Nedladdningen
avbröts och 6,6 GB halvfärdiga block raderades. gemma4:e4b visade sig vara 9,5 GB och avbröts också. Jämförelsen
mellan modeller får vänta på mer disk och minne; som domare används i stället medgemma:4b, en annan modell än den
som kör mötet.

**Modelljämförelsen, dagen efter med 22 GB ledig disk.** Samma v8 och samma 16 holdout-scenarier, bara modellen
utbytt. gemma4:12b: 16 av 16 godtagbar brådska (14 exakta mot qwens 16; ett cykelpass och en morgonlöpning blev
"bevaka"), 98 % av fynden mot 94 %, och granskaren strök bara 5 % av påståendena mot 16 %, alltså bättre
källdisciplin. Men 156 s mot 118 s och 12,3 GiB i Ollama mot 8,4. Swappen gick till 10,8 GB och disken ner till 8 GB
ledigt; minnesvakten avbröt den första körningen när swappen växte 3 GB och fick köras om med bara disk- och
minnesgräns. gemma4:e4b klipptes mitt i JSON-svaren med samma tak och fick 2,5 gånger större tak, men skrev ändå
6 752 utdatatokens per möte mot 1 806, fick i snitt 0,5 belagda påståenden och lade nästan allt på "bevaka":
12 av 16 godtagbara, 4 övertriage, 69 % av fynden. qwen3.5:9b är kvar, eftersom datorn delas med röst, webb och
vakt och 120-sekundersmålet redan är på gränsen. gemma4:12b är det första bytet om minnet blir större. Båda
gemma-modellerna är borttagna igen.

**MedGemma gjorde ingen nytta och är avstängd.** I den gamla pipelinen anropades MedGemma aldrig i de riktiga
körningarna. Med Ollamas en-modell-i-taget kostar varje anrop dessutom ett modellbyte. Jag gav den en tydligare
roll: en gång per möte skriver den bakgrundskunskap (vanliga och allvarliga orsaker, varningstecken) som läggs i
faktabladet. Resultat: samma 15 av 15 godtagbar brådska men exakt brådska 80 % mot 87 %, strykandel 26 % mot 19 %
och 11 sekunder långsammare (128 mot 117 s). Bakgrundstexten fick teamet att skriva fler allmänna påståenden som
granskaren strök. MedGemma är nu av som standard (KONSILIET_LAGE_MEDGEMMA=1 slår på den) och finns inte längre i
någon specialists verktygslåda.

**Granskaren rättar källan i stället för att stryka.** Det vanligaste skälet till strykning var inte påhittade
siffror utan fel rad: HRV-skillnaden -11 ms citerad från F:somnskuld i stället för F:natter. I feberfallet ströks
på det sättet både temperatur och nattpuls, och slutbedömningen nämnde ingen av dem. Nu provar granskaren om
påståendet håller helt med en annan faktabladsrad; finns exakt en sådan läggs den till som källa (markerat
kalla_tillagd_av_granskaren). Garantin är densamma: varje siffra finns i en angiven källa av rätt mätvärde. En
påhittad siffra räddas inte. Strykandelen sjönk från 15 % (v4) till 10 % (v6) och feberfallet fick full täckning.

**Teamet fick sänka brådskan, och sänkte bara fel.** Hybridläget lät teamet flytta regelverkets nivå ett steg åt
båda håll. I alla körningar sänkte teamet bara när det var fel: löst sittande klocka och HRV-fall efter träning
blev "ingen" i stället för "bevaka", och i holdout 5 blev en vilopuls på 106 i soffan i en timme "ingen" fast
teamets egen sammanfattning skrev att regelverket sa bevaka. Nu är regelverket golvet: teamet får höja ett steg
men aldrig sänka.

**En egen verktygsrunda per specialist: bättre täckning, för långsamt.** När varje specialist fick hämta något
eget utöver faktabladet (en runda) steg täckningen av måste-fynd från 78 % till 89 % på samma åtta scenarier, med
samma brådska, men mötet tog 185 s mot 116 s. Det är över målet på 120 sekunder, så standard är noll extra rundor.
Med mer minne (två modeller laddade, eller parallella förfrågningar) är det den första knappen jag vrider på.
Avbröts efter åtta scenarier.

**Domaren som gav alla 5 av 5.** Som LLM-domare användes medgemma:4b (en annan modell än Qwen som kör mötet).
Med frågan "betygsätt 1-5 mot facit" gav den 5/5 till nästan allt, också till baslinjens "kontakta vården nu" för
någon som bara sover för lite. Den fick i stället konkreta ja/nej-frågor (nämns huvudfyndet, finns en slutsats som
motsäger facit, finns ett skadligt råd) och poängen räknas ut av svaren. Då skilde den åtminstone på löst sittande
klocka i baslinjen (1) och i v4 (5), men den sa fortfarande att baslinjen "nämnde ferritin" i ett svar där ordet
inte förekommer. Domaren redovisas därför bara bredvid de deterministiska måtten, aldrig i stället för dem.

**Holdout: fel hittade, rättade generellt, mätt på nya fall.** Holdout 1 (fem scenarier skrivna efter att reglerna
frystes: pulsrusning 02:10 vid datorspel, cykelpass utan steg, blodbrist i provsvaren, låg nattpuls som är normal,
ett enda syrefall) gav v4 5 av 5 rätt brådska mot 3 av 5 för den gamla pipelinen (som lugnade pulsrusningen med
"ingen" och tog blodbristen som "bevaka"). Ett fel fanns ändå: det enda syrefallet fick rätt brådska men förklarades
inte som troligt mätfel. Orsaken var att faktabladet saknade en tolkning för enstaka fall, så den lades till
generellt (en till två fall en natt: vanligen tryck mot klockan eller sovställning, inte andningsuppehåll), och
två nya scenarier skrevs (holdout 3) för att se att rättningen håller på fall den aldrig sett. Holdout 2 (fem
scenarier skrivna innan holdout 1 kördes: morgonlöpning, snarkning med syrefall, feber, lågt TSH, spel med bra
sömn) gav v4 5 av 5 mot 1 av 5 för den gamla pipelinen.

**Användbarhetstestet: tröttheten missade sömnskulden.** På frågan "varför är jag så trött?" nämnde teamet inte
sömnskulden, eftersom faktabladet inte hade den. Nu finns F:somnskuld (samma räkning som appens sömnskuld i
vardag.somn: summa av behov minus sömn de senaste sju morgnarna, plus jämförelse mot egen baslinje), F:kvallar
(minuter vid datorn efter 23 per kväll och sista minuten) och F:belastning (träningspass och minuter i hög
pulszon). Ett nytt scenario, "trött efter sena spelkvällar", kräver att sömnskuld och sena kvällar nämns. Den
gamla pipelinen nämnde ingen av dem. Samma körning visade ännu ett granskarfel: "sömnskulden är 21 timmar" passerade
eftersom 21 timmar räknades som en tidsram. Nu räknas ett tal bara som ram med ett ramord ("senaste", "under",
"i rad", "sedan"). Och vid trötthetsfrågor kallas nu klinisk kemist in även när provsvaren är normala, eftersom
teamet annars aldrig sa att proverna var normala.

**En röstmodell i minnet störde tiderna.** Runt 01:50-02:10 låg en annan agents röstmodell (Chatterbox på GPU:n)
i minnet samtidigt som Qwen, med upp till 5,9 GB swap. Baslinjens körning av det nya scenariot tog då 382 s och
fyra v5-möten låg på 117-131 s. Baslinjens körning gjordes om och slutvarianterna (v6, v8) kördes efter att
röstmodellen fått en spärr mot att laddas samtidigt som en språkmodell; v5:s fyra första tider är märkta som störda.

**Holdout 4 och 5: två fel till, två rättningar till.** Holdout 1 i v6 visade att låg nattpuls (48, samma som
baslinjen) besvarades med att den låg "under den generella gränsen för vuxna" i stället för att den är normal.
Kardiologen fick en tumregel om låg puls hos unga, och holdout 4 skrevs (låg dagpuls hos en vältränad, förhöjd
puls efter energidrycker). Där svarade teamet på frågan "pulsen är 85 nu" med ett maxvärde från morgonen, för att
faktabladet bara hade pulsen nu men inte pulsen nu mot baslinjen. Det lades till (plus senaste fem minuterna och
senaste timmen), personens egen fråga blev en källa för det personen själv skrivit, och holdout 5 skrevs. Där
upptäckte jag i faktabladet, innan teamet körts, att regelverket inte reagerade på en vilopuls på 106 i en timme
när det var en fråga och inte ett vaktlarm; regeln lades till (samma sak som vaktens baslinjeregel), så holdout 5
är delvis förorenad och märkt så i RESULTAT.md.

**Slutsiffran (v8).** På de 16 tränade scenarierna: 16 av 16 godtagbar brådska (88 % exakt), 92 % av måste-fynden,
median 123 s (max 166), 1 866 utdatatokens per möte. På de 16 holdout-scenarierna: 16 av 16 (100 % exakt), 94 %
av fynden, median 118 s. Den gamla pipelinen på samma 16 holdout: 9 av 16, 3 övertriage och 4 undertriage, 67 %
av fynden, 226 s. Tiderna inkluderar en kall modellstart och är något över målet på 120 s. Det som fortfarande är
svagt: ett par fynd faller bort mellan körningar (förklaringen "troligen mätfel" till ett enstaka syrefall, ordet
"spel" i svaret om spelande), domaren går inte att lita på, och allt är syntetiskt och skrivet av samma hand som
reglerna. Riktig data på min egen klocka är nästa prov.

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

**Rutan ritas nu om direkt, och "Jag mår bra" är testat på riktigt.** Det som stod ovan om rutan var en
nödlösning. Felsökningen med tidsstämplar i loggen: `TileService.getUpdater().requestUpdate()` (tiles 1.5
och 1.6) gav ingen omritning på 20 försök, inte heller med huvudtråden fri och processen hållen vaken. När
klockappen själv band till systemets uppdateringstjänst (`androidx.wear.tiles.action.BIND_UPDATE_REQUESTER`
i hemskärmens paket) och skickade samma begäran kom `onTileRequest` 11 ms senare. Det är nu vägen
(`Surfaces.requestTile`, biblioteket som reserv). Uppmätt på klockemulatorn: när rutan inte syns 51 ms från
status till omritning, när den syns 1,8 s och 1,1 s, och en begäran 9 s efter förra omritningen väntade till
nästa 20-sekundersfönster (15 s). En fälla i testet: min första testserie skapade en ny bedömning per steg, och
notisen "Tråden är löst" lade sig över rutan så att den inte syntes. Mätningarna gjordes med rutan tillagd
via rutväljaren på klockan. Klockfrekvensen är nu ett dynamiskt
värde som rendraren uppdaterar själv: 150, 100 och 145 BPM avlästa med 9 sekunders mellanrum utan någon
omritning däremellan.

Sms-kedjans "Jag mår bra" hade bara testats i enhetstester. Riktigt test på mobilemulatorn mot den separata
testinstansen, sms påslaget med en testkontakt och 2 minuters frist: akutlarm med vaktregel publicerat
23:11:40, sms-alarmet stod i AlarmManager till 23:13:40. Knappen "Jag mår bra, skicka inget sms" trycktes i
notisen 23:11:58. AlarmManager loggade `alarm_cancelled` samma sekund, den sparade kedjan var borta, och efter
fristen (kontroll 23:14:21) fanns inget nytt sms i skickat-mappen och ingen sms-notis. Under testet visade
det sig att en annan session samtidigt använde samma mobilemulator mot en egen testserver (port 8801) och
bytte serveradress i appen. Emulatorerna delas, så tester på dem ska samordnas.

**Egen andra mobilemulator, och "Jag mår bra" igen på det omdöpta bygget.** För att inte krocka med
användbarhetstestet skapades en andra telefon-AVD på Lenovon (Pixel_8_Kropp64_B, samma systemavbild, 1,5 GB
RAM i stället för 2 GB eftersom bara 2,7 av 16 GB var lediga med två emulatorer igång). Första starten dog
utan felmeddelande efter några minuter, och nästa start vägrade med "Another emulator instance is running"
på grund av kvarlämnade låsfiler i AVD-mappen. Låsfilerna togs bort och den startade. Serveradressen
skrevs in i förstastartsvyn, sms slogs på och testkontakten lades till via Inställningar (knappen kräver
minst sex siffror i numret, och `adb input text` tappade tecken på den långsamma emulatorn, så texten fick
skrivas i bitar). Akutlarm 23:46:11, sms-alarm satt till 23:48:11, "Jag mår bra" tryckt i notisen 23:46:33,
`alarm_cancelled` samma sekund, ingen kedja kvar, och efter fristen (kontroll 23:48:44) var skickat-mappen tom.

## Riggvyn: kroppen som PC-chassi i 3D (2026-11-24)

Överkroppen byggd som ett chassi i borstad aluminium med härdat glas: processorn med tornkylare är hjärtat och
slår i pulsen, två fläktar är lungorna (vänster lunga 120 mm, höger 140 mm, eftersom vänster lunga är mindre),
revbenen är kylflänsar med värmerör, mellangärdet ett välvt PSU-skydd och nätaggregatet i buken visar headroom.
Modellen skrivs som ett bpy-skript (`render/rigg/rigg.py`) och byggs på Lenovon med `render/rigg/kor.sh`.
Webben: `web/src/rigg/` (three.js 0.187.0, låst), överst på Översikt och som egen vy Riggen.

**Mätt.**
- Bygget på Lenovon (Blender 4.5.3, RTX 5050): geometri 2 s, AO-bakning 27 s (chassit, 2048 px) och 6 s
  (kylflänsarna, 1024 px), glb-export med Draco 27 s, reservbilden 2400x1200 i 384 samples 88 s. Totalt 188 s
  när laptopen hade ont om minne; första provbygget tog 35 s.
- Storlek: `kropp64-rigg.glb` 652 kB (Draco, AO som WebP), reservbilden 43 kB. Three.js och motorn ligger i en
  egen bit (690 kB, 173 kB gzip) som laddas först när riggen syns. Huvudbundeln är oförändrad, cirka 206 kB.
- Bildtakt på Mac minin (M4, Chromium headless med Metal): 61 fps (skärmens tak) på Riggen och Översikt i
  1440x900, pixeltäthet 1,75 (duk 2446x1186). Närbilden under en tråd, utan tak: 64 fps. Mobilformat
  412x915 med pixeltäthet 2,625 och CPU strypt 4 gånger: 61 fps (men med Macens GPU).
- Android-emulatorn på Lenovon (konsiliet_phone, Chrome 133) kör WebGL i mjukvara (SwiftShader): 1-11 fps även
  på lägsta kvalitet. Riggen märker det och visar då reservbilden och mätvärdena som text. En egen emulator med
  GPU gick inte att få igång: Lenovon hade 0,2-0,9 GB ledigt av 16 GB med två emulatorer, talsyntesen och
  Blender igång, och första försöket dog på minnesbrist, det andra kraschade efter start. Någon siffra för en
  mellanklassmobil med riktig GPU finns alltså inte än.

**Problem på vägen.**
- Första versionen gav 15-18 fps i närbild. Tre orsaker, mätta en i taget: kylaren är 30 fenor rakt bakom
  varandra i en enda mesh, så varje pixel skuggades upp till 30 gånger (djupförpass för kylaren, revbenen och
  fläktbladen: 17 till 43 fps); glaset var ett PBR-material över hela bilden (MeshBasic med miljökarta och
  additiv blandning: halverade kostnaden); OutlinePass ritar scenen tre gånger plus skuggkartan varje gång.
  Den ersattes med en egen kontur: bara den markerade komponenten ritas som mask i halv upplösning och en
  helskärmsruta lägger linjen utanför maskens kant. Skuggkartan ritas en gång per bild, 1024 px i stället för 2048.
- Three 0.187 har tagit bort PCFSoftShadowMap (PCF används) och buntar Draco-avkodaren själv; den egna kopian i
  public/ togs bort.
- Meshar med flera material blir en grupp med barn (`kylflans_1`, `kylflans_2`) i glTF, så den termiska
  färgkartan fastnade först inte på revbenen. Nu används närmaste namngivna förälder.
- Den automatiska kvalitetssänkningen gick först på riggens egen klocka, som nästan står still när det går
  trögt. Nu räknas väggklockan, och ett enstaka hack (shaderkompilering) räknas inte.
- Delade emulatorer: en annan session hade Pixel_8_Kropp64_B igång när jag försökte starta den, och adb-servern
  startades om flera gånger under mätningen. Emulatorer ska samordnas.

**Bilder och film.** `docs/bidrag-bilder/11-riggen-demo.png`, `12-riggen-trad-demo.png` och
`docs/video/riggen-demo-1920x1080.mp4` (14 s, inte i git). Inspelningsläget (`?capture=1`) stegar tiden exakt,
så filmen blir jämn oavsett dator.

**Riggen på landningssidan (2026-11-25).** Platsen `#riggvyn-plats` i hjälten på kropp64.se visar nu riggen i
demoläge (syntetiska värden ur manuset, "Demo - syntetisk data" i vyn och i bildtexten). Den byggs separat
(`web/src/rigg/sajt.ts`, `web/vite.sajt.config.ts`, anropas av `site/bygg.sh`) och laddas först när besökaren
klickar "Starta riggen", eller av sig själv efter sidladdningen när bilden syns på en dator med mus, WebGL2,
minst 4 kärnor och 4 GB, utan datasparläge och utan reducerad rörelse. Knappen växlar tillbaka till
renderingen av kretskortet. Utan WebGL visas riggens stillbild med en saklig bildtext.
Uppmätt med headless Chromium mot `site/dist`: första skärmen (allt till load) är 181 kB i 7 filer, samma som
före riggen så när som på 3 kB knapp och skript. Av de 181 kB är 50 kB kontorsfilmens affischbild
(`bilder/kontoret.webp`) långt ner på sidan, som laddas direkt; med `loading="lazy"` där skulle första skärmen
bli cirka 130 kB. Riggen hämtar sedan 1,7 MB okomprimerat (rigg.js 665 kB, 174 kB med gzip, modellen 637 kB,
typsnitt 46 kB, stillbild 42 kB). 61 fps i 1440x900 och i 375x812 på Mac minin, ingen horisontell scroll.

**Referens: Chrome på Lenovon.** Chrome 158 headless, startad över ssh med `--use-angle=d3d11`, fick RTX 5050
(D3D11): 61 fps i median i översikten på full kvalitet i 1440x900, men ojämnt (enstaka sekunder 20-37 fps) och
36 fps i median i närbilden. GPU:n var 5 % belastad och processorn 66 % av annat arbete, så det som begränsar
är processorn och bildtakten i ett fönster utan skärm, inte grafiken. Ett synligt Chrome-fönster på
skrivbordet valde Intel-grafiken (Optimus) och fick `visibilityState: hidden` eftersom skärmen var avstängd,
så där ritades ingenting och någon skrivbordssiffra finns inte.

## 2026-11-24/25: en vecka som användare

**Varför.** Allt fungerade tekniskt, men skulle jag öppna appen varje dag? En agent fick spela en påhittad
18-åring under en simulerad vecka (kodpass, sena spelkvällar, en dålig natt, en sjuk natt, tre pass, en fråga
till teamet) på syntetisk data, på en separat testserver (port 8801, egen databas) och de delade emulatorerna.
Hela genomgången, före och efter, står i [docs/ANVANDBARHET.md](docs/ANVANDBARHET.md).

**Det första som hände vid installationen.** Health Connect läser 30 dagar bakåt, vakten gick igenom historiken
och startade direkt en tråd om att vilopulsen var *lägre* än vanligt en söndag en månad tidigare (personen sov
länge en timme då han brukar spela). Tre notiser om något som inte gick att göra något åt. Vakten startar nu
ingen tråd för historik äldre än ett dygn och larmar inte för lägre puls än baslinjen. Samma test hittade att
pulsen vid datorn kl. 02 jämfördes med sovpulsen för den timmen, och att den sjuka natten gav tre trådar.

**Morgonfrågan hade inget svar.** "Ska jag träna i dag?" fanns inte som rad någonstans. POST-skärmen låg två svep
ned, skrevs 07:30 även när personen sov (4 av 7 morgnar i testveckan) och beslutet stod sist i fyra meningar från
språkmodellen, som tog 44,7 s att skriva. Headroom räknades på 00-06, vilket för den som spelar till två är vaken
tid vid datorn. Nu finns `vardag.py`: beslutet (träna, ta det lugnt, vila) med plan och varför räknas i koden på
14-20 ms och står först i appen, webben, notisen, widgeten och klockans ruta. Idrottsläkaren förklarar bara, inom
gränser som koden sätter för minuter och puls. POST-skärmen skrivs när natten är slut.

**Knuffarna var brus.** 33 AFK-knuffar på veckan, utan knappar, även mitt i en match. Varje avvikelse gav tre notiser.
Efter: budget per dag, tysta timmar, snooze, "mitt i ett pass", AFK väntar på en paus i spelet, en notis per tråd
som uppdateras på plats. Simulerad vecka: 59 notiser blev 34, och bland de 34 finns nya som efterfrågades
(läggdags, efter passet, veckan).

**Frågan "varför är jag så trött?"** gav fyra minuter tom skärm. Snabbsvaret ur regelverket kommer nu på en
sekund, lösningen efter tre minuter och slutar med 1-3 åtgärder. Teamets lösning missade dock sömnskulden, som
inte finns i faktabladet; det är noterat för den som äger konsiliets kvalitet.

**Problem på vägen.**
- *En annan session committade mitt halvfärdiga arbete.* Commit e767610 ("Kropp64-termer i mobilen och klockan")
  tog med mina nya mobilfiler (Idag.kt, notiserna, snabbsvaret) eftersom den lade till hela katalogen. Ingen skada,
  men commit-meddelandet beskriver inte de ändringarna. Mina egna commits lägger nu bara till namngivna filer, och
  i delade filer bara mina hunkar (`git apply --cached` på ett filtrerat diff).
- *Två Vite-servrar på samma port.* Min dev-server och en annan sessions lyssnade båda på 5181 (en på IPv6, en på
  IPv4), så första skärmbilden visade den andra sessionens databas. Upptäcktes på att bannern sa `dev-syntetisk`.
- *Emulatorerna delas.* Jag tömde mobilappens data för att testa första starten, och därmed den andra sessionens
  serveradress; den återställdes. En egen emulator dog direkt av minnesbrist (Lenovon hade 0,3-0,8 GB ledigt med
  tre emulatorer, talsyntes, Blender och Gradle). Gradle fick köras med `-Xmx1500m --no-daemon`. Senare blev båda
  delade emulatorerna offline och svarade inte, och adb-servern dog när ssh-sessionen stängdes. De startades om
  med samma AVD, port och flaggor via schemalagda uppgifter (så att de inte hör till ssh-sessionen), och en
  anteckning lades i `_lenovo/EMULATOR-ANVANDS.txt`.
- *`input text` på emulatorn* tappar första tecknen om fältet inte hunnit få fokus, och klarar inte å, ä, ö.
- *Wear OS fäller ut en notis vid första trycket.* "Ett tryck från passpåminnelsen" blev två: fäll ut, Starta pass.
- *Bakgrundsstart av en skärm på klockan* stoppas av systemet, så "Andas 60 s" från mobilen blir en notis på
  klockan som öppnar andningen.

**Android med hårdvaru-GPU: emulatorn kan inte mäta riggen.** Efter att ha väntat på minne (kontroll var 10:e
minut, 2,2-2,8 GB ledigt tills 00:32 då 4,5 GB var ledigt) startades en egen skrivskyddad instans av
Pixel_8_Kropp64_B utan fönster.
- `-gpu host`: hårdvaru-GPU, SurfaceFlinger rapporterar "Android Emulator OpenGL ES Translator (NVIDIA GeForce
  RTX 5050 Laptop GPU)", och WebGL i Chrome 133 och i appens WebView fick samma renderare. Men bildtakten
  pendlade mellan 1-5 och 18-46 fps oavsett upplösning (pixeltäthet 1,5 ned till 0,75 gav samma mönster), och
  riggen gick till slut över till stillbilden. Orsaken är emulatorn, inte riggen: en tom requestAnimationFrame-
  slinga utan 3D fick 29 fps i WebView och 31 fps i Chrome med upp till 0,6-1,4 s långa stopp, och att bara
  tömma en 400x400-duk med WebGL varje bild gav 16-18 fps med 95:e percentilen på 170-200 ms. Emulatorn utan
  fönster levererar alltså bilder ojämnt även när GPU:n inte gör någonting.
- `-gpu angle_indirect`: emulatorn föll tillbaka på SwiftShader (mjukvara), "OpenGL ES 3.0 SwiftShader 4.0.0.1".
  Ingen hårdvaru-GPU.
- Appens WebView mättes genom att låta den skrivskyddade instansen peka på demobygget (sms avstängt i den
  kopian först, eftersom den hade sms till en testkontakt påslaget) och navigera WebView-sidan till Riggen via
  WebView-felsökningen (appen är ett debug-bygge).
Slutsats: det finns ingen trovärdig mobilsiffra från emulatorn. Det som är verifierat för telefoner är
mobillayouten (375-442 px), att riggen sänker kvaliteten i steg och att den går över till stillbilden när
bildtakten inte räcker. En riktig mellanklassmobil behövs för en siffra.

**Rösttjänsten startar av sig själv.** En schemalagd uppgift på Lenovon ("Kropp64 rosttjanst") startar
`rost_tjanst.bat` vid inloggning och startar om den upp till tre gånger om den faller. Tidigare slutade
rösterna fungera efter en omstart av laptopen.

**Reservrösten på Mac minin, uppmätt.** Chatterbox/Parambe på MPS med Qwen urladdad (79 % ledigt minne vid
start): kort replik 30,3 s för 2,1 s tal (RTF 14,3), mellan 32,2 s för 5,8 s (RTF 5,5), lång 44,4 s för 9,4 s
(RTF 4,7). Ungefär 25 s är fast uppstartskostnad per jobb. Långt från realtid, så den duger bara som reserv för
förgenerering när Lenovon är avstängd. Ännu en sak som 16 GB sätter gränsen för.
