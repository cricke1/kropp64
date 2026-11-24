# Skärmbilder

Utvecklingsbilder från bygget, tagna före namnbytet till Kropp64 (gränssnittet hette då Konsiliet). Ingen av dem visar riktig hälsodata: allt är syntetiskt, demo eller emulator. Bilderna till tävlingsbidraget finns i docs/bidrag-bilder.
Varje bild har samma märkning i en remsa i nederkanten (gjord med `tools/etikett.py`).

| Bild | Märkning | Vad det är |
|---|---|---|
| [fraga.png](fraga.png) | Syntetisk testdata | Testserver med egen databas, mätpunkterna kommer från web/dev/ingest.mjs (källa dev-syntetisk). |
| [klocka-app-kropp64.png](klocka-app-kropp64.png) | Syntetisk testdata från emulator | Klockappen med Kropp64-termer (Klockfrekvens, Headroom, trådens läge). Health Services testläge, syntetisk status från testservern. Inte en människa. |
| [klocka-komplikationer.png](klocka-komplikationer.png) | Syntetisk testdata från emulator | Urtavlan Everyday med Kropp64:s komplikationer: Headroom som båge (vänster) och Supporttråden överst. Klock- och mobilemulator mot en separat testserver med egen databas. Headroom från syntetiska nätter (dev-syntetisk), trådarna infogade för hand, puls och steg från Health Services testläge. Inte en människa. |
| [klocka-pass-pagar.png](klocka-pass-pagar.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [klocka-puls-syntetisk.png](klocka-puls-syntetisk.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [klocka-ruta-headroom.png](klocka-ruta-headroom.png) | Syntetisk testdata från emulator | Rutan (tile) Kropp64: headroom, klockfrekvens, trådens läge, senast synkad. Klock- och mobilemulator mot en separat testserver med egen databas. Headroom från syntetiska nätter (dev-syntetisk), trådarna infogade för hand, puls och steg från Health Services testläge. Inte en människa. |
| [klocka-val-av-pass.png](klocka-val-av-pass.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [konsilier.png](konsilier.png) | Syntetisk testdata, riktiga lokala modeller | Tidiga körningar mot testdatabas. Bedömningen överst är den misslyckade körningen som beskrivs i RESAN.md. |
| [kontoret-demo-bedomning.png](kontoret-demo-bedomning.png) | Demo - syntetisk data | Demoläget i webben: ett manus, inga uppmätta värden och ingen språkmodell. |
| [kontoret-demo-strykning.png](kontoret-demo-strykning.png) | Demo - syntetisk data | Demoläget i webben: ett manus, inga uppmätta värden och ingen språkmodell. |
| [kontoret-ljust.png](kontoret-ljust.png) | Demo - syntetisk data | Demoläget i webben: ett manus, inga uppmätta värden och ingen språkmodell. |
| [kontoret-mobil.png](kontoret-mobil.png) | Demo - syntetisk data | Demoläget i webben: ett manus, inga uppmätta värden och ingen språkmodell. |
| [kontoret-uppspelning.png](kontoret-uppspelning.png) | Syntetisk testdata, riktiga lokala modeller | Konsilierna kördes av qwen3.5:9b på Mac minin mot en testdatabas med syntetisk puls. |
| [mobil-akut-larm-test.png](mobil-akut-larm-test.png) | Testlarm på emulator | Larmet är infogat för hand i testdatabasen för att prova larmkedjan. Ingen riktig mätning. |
| [mobil-forsta-start-kropp64.png](mobil-forsta-start-kropp64.png) | Emulator, första start | Förstastartsvyn med namnet Kropp64. Ingen serveradress är inbyggd i appen. Inga mätvärden visas. |
| [mobil-forsta-start.png](mobil-forsta-start.png) | Emulator, första start | Ingen serveradress är inbyggd i appen. Inga mätvärden visas. |
| [mobil-fraga.png](mobil-fraga.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [mobil-idag-morkt.png](mobil-idag-morkt.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [mobil-idag-testdata.png](mobil-idag-testdata.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [mobil-idag-utan-nat.png](mobil-idag-utan-nat.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [mobil-installningar-kropp64.png](mobil-installningar-kropp64.png) | Emulator mot testserver | Inställningar med sms påslaget för testet. Serveradressen är suddad, testkontakten är emulatorns eget nummer. |
| [mobil-installningar.png](mobil-installningar.png) | Emulator mot testserver | Serveradressen är suddad. |
| [mobil-jag-mar-bra-test.png](mobil-jag-mar-bra-test.png) | Testlarm på emulator | Akutlarm med knappen "Jag mår bra". Larmet publicerades för hand på en separat testserver. Knappen trycktes och sms-alarmet avbröts, inget sms skickades. |
| [mobil-konsiliet-kontoret.png](mobil-konsiliet-kontoret.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [mobil-lank-ko-utan-nat.png](mobil-lank-ko-utan-nat.png) | Syntetisk testdata från emulator | Klock- och mobilemulator mot en testserver, Health Services testläge. Inte en människa. |
| [mobil-ny-trad.png](mobil-ny-trad.png) | Syntetisk testdata | Fliken Ny tråd. Mobilemulator mot en separat testserver med egen databas (källa syntetisk-vecka). Inte en människa. |
| [mobil-sensorer.png](mobil-sensorer.png) | Syntetisk testdata | Fliken Sensorer (tidigare Idag) med Kropp64-termer. Mobilemulator mot en separat testserver med egen databas (källa syntetisk-vecka). Inte en människa. |
| [mobil-sms-exakt-alarm-test.png](mobil-sms-exakt-alarm-test.png) | Testlarm på emulator | Larmet är infogat för hand i testdatabasen för att prova larmkedjan. Ingen riktig mätning. |
| [mobil-sms-skickat-test.png](mobil-sms-skickat-test.png) | Testlarm på emulator | Larmet är infogat för hand i testdatabasen för att prova larmkedjan. Ingen riktig mätning. |
| [mobil-tidslinje-kropp64.png](mobil-tidslinje-kropp64.png) | Syntetisk testdata | Tidslinjen med POST-skärmen. Mobilemulator mot en separat testserver med egen databas (källa syntetisk-vecka). Inte en människa. |
| [mobil-tidslinje-morkt.png](mobil-tidslinje-morkt.png) | Testlarm på emulator | Larmet är infogat för hand i testdatabasen för att prova larmkedjan. Ingen riktig mätning. |
| [mobil-widget.png](mobil-widget.png) | Syntetisk testdata från emulator | Hemskärmswidgeten: headroom med delar, steg, senaste lösningen. Klock- och mobilemulator mot en separat testserver med egen databas. Headroom från syntetiska nätter (dev-syntetisk), trådarna infogade för hand, puls och steg från Health Services testläge. Inte en människa. |
| [oversikt-ljust.png](oversikt-ljust.png) | Syntetisk testdata | Testserver med egen databas, mätpunkterna kommer från web/dev/ingest.mjs (källa dev-syntetisk). |
| [oversikt-mobil.png](oversikt-mobil.png) | Syntetisk testdata | Testserver med egen databas, mätpunkterna kommer från web/dev/ingest.mjs (källa dev-syntetisk). |
| [oversikt.png](oversikt.png) | Syntetisk testdata | Testserver med egen databas, mätpunkterna kommer från web/dev/ingest.mjs (källa dev-syntetisk). |
| [systemet.png](systemet.png) | Syntetisk testdata | Testserver med egen databas, mätpunkterna kommer från web/dev/ingest.mjs (källa dev-syntetisk). |

`konsilium-detalj.png` är borttagen. Den visade den första misslyckade körningen med nivån "Kontakta vården nu"
trots att inget påstående godkänts av granskaren, och såg ut som ett resultat. Den körningen beskrivs i RESAN.md.

## Användbarhetstestet (anv-*)

Bilderna med prefixet `anv-` är från användbarhetstestet i [docs/ANVANDBARHET.md](../ANVANDBARHET.md): en
påhittad 18-åring under en simulerad vecka, syntetisk testdata (källa `syntetisk-vecka`) på en separat
testserver, mobil- och klockemulatorer på Lenovon och webben i Chromium headless. `anv-fore-*` visar läget före
ändringarna. Varje bild är märkt i en remsa i nederkanten. Inget är uppmätt på en människa.
