# Resan

Dagbok över bygget. Skrivs medan det händer, inte i efterhand.

## Bakgrund

Köpte Mac minin (M4, 16 GB) under OpenClaw-trenden i januari 2026 och har kört agenter på den sedan dess.

## 2026-11-24

**Falsk start.** Min Discord-agent fick i uppdrag att bygga ett tävlingsbidrag och producerade på en timme
cirka 4 000 rader Python: en "diabetesagent" med korrelationsmotor, larmkedja och ett snyggt terminaldemo.
Problemet: allt kördes på syntetisk exempeldata, journalformatet var påhittat, och demot innehöll siffror
som ingen hade mätt. Det såg imponerande ut men var en kuliss. Jag slängde storyn och började om här,
med kravet att allt ska köras på min riktiga data och att varje siffra ska vara uppmätt.

Lärdom: en agent som får "gör det imponerande" som mål optimerar för att det ska *se* imponerande ut.

**Arkitektur bestämd.** Egen Wear OS-app på klockan för realtid (Fitbit-synken kommer bara var 15:e minut),
Android-app som brygga, Mac minin som server bakom Cloudflare Tunnel, lokala modeller via Ollama.

**Port upptagen.** Servern skulle köra på 8787, men den porten hade ett annat av mina projekt (en node-server
som stått igång i 17 timmar). Flyttade till 8790.

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
