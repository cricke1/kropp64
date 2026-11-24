# Användbarhet: en vecka som 18-åring som vill börja träna

Syftet var att Kropp64 ska vara något man öppnar varje dag och gör något av, inte bara en tekniskt komplett
sensorpanel. Jag spelade användaren under en simulerad vecka: 18 år, sitter mycket inne och bygger saker med AI,
kodar på eftermiddagen, spelar på kvällen, sover för lite och vill börja träna. Fokus: sömn, stress och träning.

**Allt här bygger på syntetisk testdata.** Ingen siffra i det här dokumentet är uppmätt på en människa.

## Hur det testades

- **Person och data:** `tools/syntetisk_person.py`. 28 dygn vardag utan träning (baslinjen, som Health Connect
  läser bakåt vid första installationen) och sedan testveckan mån 16 - sön 22 november, minut för minut: sömn,
  puls (var 5:e sekund under pass), HRV, SpO2, steg, datortid per kategori, tre pass och en sjuk natt. Källan
  heter `syntetisk-vecka` och märks som testdata i appen och webben.
- **Testserver:** en egen instans på port 8801 med egen databas (`tools/fyll_testserver.py`), aldrig den
  riktiga på 8790. Språkmodellen är den riktiga (qwen3.5:9b i Ollama på Mac minin).
- **Mobil och klocka:** de delade emulatorerna på Lenovon (Android 16 och Wear OS), med mobilappen pekad mot
  testservern under testet och tillbaka till den andra sessionens server efteråt. Klockans svar till mobilen
  flyttades med `android/tools/svarsbrygga.ps1` och mobilens status till klockan med `statusbrygga.ps1`,
  eftersom emulatorerna inte kan parkopplas (se RESAN.md).
- **Webben:** Vite mot testservern, skärmbilder med Chromium headless.
- **Notiser per dag:** `tools/simulera_vecka.py` kör vakten och alla knuffar minut för minut genom testveckan i
  en engångsdatabas, med reglerna före (vakten och AFK-knuffen ur git, mobilens notisregler som de var) och
  efter. Personens svar på knuffarna är manus (en snooze måndag, fokusläge tisdag kväll).

## Veckan, ögonblick för ögonblick

| Ögonblick | Före | Hittat | Ändrat |
|---|---|---|---|
| Första installationen | Serveradressen, sedan Sensorer med tom pulskurva och "ingen data" för sömnen fast servern hade den. 30 dagars historik gav direkt en tråd om en lägre vilopuls **2026-10-25** (en sovmorgon), med tre notiser. | Inget säger vad som behövs (Health Connect, klockan, batterioptimering, en natt). Historik och lägre puls än vanligt blev larm. | "Kom igång" med fyra steg på Idag så länge ingen natt finns. Vakten startar ingen tråd för historik äldre än ett dygn och larmar inte för lägre puls än baslinjen (utom under 40 BPM). |
| Morgonen | Ingen rad svarar på "ska jag träna i dag?". POST-skärmen ligger längst ned på Sensorer, två svep ned, och skrevs kl. 07:30 oavsett om man sov: i testveckan 4 av 7 morgnar medan personen sov, på en halv natt. Svaret kom sist i fyra meningar från språkmodellen. Headroom räknades på 00-06, som för den som spelar till två är vaken tid. | Fem sekunder räckte inte. Siffran 51 sa inget om vad man skulle göra. | **Idag** först i appen och webben: "Ta det lugnt i dag", "Promenad 30 min, under 117 BPM", varför på en rad med siffror och enheter. Beslutet tas av regler i koden (`vardag.idag`), idrottsläkaren skriver bara förklaringen inom gränser koden sätter. POST-skärmen skrivs när natten är slut. Headroom på sömnpassets fönster. Dygnet byter vid 04. |
| Kodpass 13-17 | AFK-knuff var 90:e minut, samma text, ingen knapp. Även mitt i en match. 33 AFK-knuffar på veckan, varje till mobil och klocka. | Blir brus efter en dag. Ingen väg att säga "inte nu". | Knappar: Om 30 min, Mitt i ett pass (2 h), Inte i dag (mobil och klocka). Under spel väntar knuffen på en paus (högst 30 min). Två ignorerade i rad: var tredje timme. Budget 6 knuffar per dag (två platser sparas åt läggdags och pass), tysta timmar 23-08. |
| Sen spelkväll | Ingenting. | Hög puls vid datorn syntes bara i Uptime-tabellen dagen efter. Läggdags fanns inte. | Stressknuff när pulsen är 20 BPM över samma timmes vilopuls i 10 min vid datorn: "Termisk strypning: hög puls vid datorn" med siffrorna i klartext och "Andas 60 s på klockan". Läggdagsknuff 30 min före, bara om man sitter vid datorn, med kvällens speltid och sömnskulden. |
| Träningspass | "Starta stresstest", välj typ, sedan bara "Stresstest pågår, N min". Ingen zon, inget efteråt. | Den som börjar träna vet inte hur hårt det ska vara. | "Starta pass" med dagens plan (ett tryck), live: puls, zon med namn, målzon i BPM och "Över målzonen, sakta ner". Efteråt på klockan direkt (även utan mobil) och som notis: tid, medel och max, minuter per zon, andel i målzon, råd om återhämtning, "Pass 2 av 3 den här veckan". Progressiv plan, 3 pass i veckan, nivån höjs när två blev av. |
| Dålig natt (3 h 50 min) | Headroom 18 i tabellen. | Ingen slutsats. | "Vila i dag: Headroom bara 18 av 100, 3 h 50 min sömn". Sömnskuld och läggdags syns på Idag. |
| Avvikelse (sjuk natt) | Tre notiser per avvikelse (avvikelsen, "Ny tråd startad", lösningen) och ofta fler trådar för samma natt (3 på lördagen). Pushen sa "Konsiliet har en bedömning". | Notisfloden kom när man var som tröttast. Lösningen slutade utan något att göra. | En notis per tråd som uppdateras på plats: "Vakten såg något" med snabbsvaret från regelverket efter ca 1 s, sedan lösningen med första åtgärden. Högst en tråd från vakten per natt (akuta undantagna). Lösningen slutar med 1-3 åtgärder ("Gör så här"). Rubriken vid brådska är saklig: "Ta upp med vården (inte akut)". |
| "Varför är jag så trött i dag?" | Ny tråd: fliken, fältet, skriva, Starta. Sedan tomt i 247 s tills lösningen kom, och notisen "Ny tråd startad" om ens egen fråga. | Fyra minuter utan svar. | Färdiga frågor startar med ett tryck. Snabbsvaret ur datan (sömn, sömnskuld, sena nätter, Headroom) syns direkt, teamets svar efter 188 s. Ingen notis om att ens egen tråd startat. |
| Veckan | Söndag 19:00 en hel tråd med språkmodellen och två notiser. | Lång och utan siffror man känner igen. | Kort sammanfattning med ärliga siffror: pass mot mål, minuter i zon, sömn i snitt, sena nätter, Headroom, hur många AFK-knuffar som följdes, och vad nästa vecka gäller. Veckotråden körs fortfarande men är tyst om den inte hittar något för vården. |
| Inför vårdcentralen | PDF:en fanns på servern men inget i appen eller webben länkade dit. | Död ände. | "Öppna besöksunderlaget (PDF)" i mobilens Inställningar (öppnas i telefonens PDF-visare via FileProvider) och på webbens Idag. Åtgärden vid "ta upp med vården" pekar dit. |
| Inställningar och integritet | Server, Health Connect, sms, stegmål. | Inget om plan, väckning, tysta timmar eller hur många notiser. | "Plan och knuffar": passdagar, passtid, väckning vardag och helg, tysta timmar, knuffar per dag (3/6/10) och av/på per sorts knuff. Sparas på servern. |
| Mobilen utan nät | "Servern svarar inte" i Headroom-raden. | Dagens svar försvann. | Senaste Idag-svaret sparas och visas med "Ingen kontakt med servern. Visar svaret från ...". Klockan har planen i sin status och sammanfattar passet lokalt. |
| Tillgänglighet | Flikraden klipptes vid 130 % textstorlek. Fliken hette "Tråden" och "Ny tråd". Termerna saknade förklaring. | | Flikarnas text växer högst till 115 % (resten av appen följer systemets textstorlek, verifierat vid 130 %), beslutskortet läses som en mening av TalkBack, passrutorna har "2 av 3 pass den här veckan" som beskrivning, flikar har roll och vald-status. "Vad betyder Headroom och zon?" ett tryck bort på Idag, med alla regler. |

## Före och efter, i siffror

| Mått | Före | Efter | Hur det mättes |
|---|---|---|---|
| Tid till svar på "ska jag träna i dag?" | Inget direkt svar. POST-skärmen: språkmodellen 44,7 s (uppmätt mot testservern), skrevs 07:30 även när man sov | Beslutet räknas på 14-20 ms (`/api/idag`, fem anrop), ligger överst i appen, i notisen, widgeten och klockans ruta | curl mot testservern; emulatorn |
| Appstart till beslutet synligt (emulator) | - | Kallstart 7,6 s, varmstart 0,14 s (`am start -W`), beslutet på första skärmen | Lenovons emulator med mjukvarugrafik och ont om minne |
| Ord att läsa till beslutet | Cirka 60 (fyra meningar, beslutet sist) | 4 ("Ta det lugnt i dag") | Räknat |
| Tryck: morgonsvaret | 1 tryck + 2 svep (om POST-skärmen fanns) | 0 (notisens rubrik, widget, klockans ruta) eller 1 (öppna appen) | Emulatorn |
| Tryck: "inte nu" på AFK | Gick inte | 1 | Emulatorn, mobil och klocka |
| Tryck: "jag är mitt i ett pass" | Gick inte | 1 (notisen eller Idag) | Emulatorn |
| Tryck: starta dagens pass på klockan | 3 (öppna, Starta stresstest, välj typ) | 2 (öppna, Starta pass), eller 2 från passpåminnelsen (fäll ut, Starta pass) | Klockemulatorn |
| Tryck: fråga teamet "varför trött" | 3 tryck + skriva 30 tecken | 1 tryck (efter ett svep på Idag) | Emulatorn |
| Första svaret på en fråga | 247 s (teamets lösning) | Snabbsvar ca 1 s, lösningen 188 s | Händelseloggen på testservern |
| Besöksunderlaget (PDF) | Ingen väg i appen | 2 tryck (Inställningar, Öppna) | Emulatorn |
| Notiser på mobilen, testveckan | 59 (6, 8, 8, 8, 4, 17, 8 per dag) | 34 (5, 4, 6, 4, 3, 6, 6) | `tools/simulera_vecka.py` |
| varav AFK-knuffar | 33 (alla även på klockan) | 16 | samma |
| varav om trådar (avvikelse, start, lösning) | 19 | 3 (+ en tyst veckotråd) | samma |
| Nya, efterfrågade notiser | - | läggdags 6, efter passet 2, veckan 1 | samma |
| POST-skärmen medan personen sov | 4 av 7 morgnar | 0 (skrivs när natten är slut) | samma |
| Trådar vid första installationen (30 dagars historik) | 1 tråd, 3 notiser, om en sovmorgon för en månad sedan | 0 | Testservern, före och efter ändringen i vakten |

Efter-veckan stoppade budget och tysta timmar 4 knuffar till (de räknas inte ovan). Stressknuffen syns inte i
simuleringen eftersom personen tryckte "mitt i ett pass" just den kvällen; den provades live på testservern
(puls 105 BPM vid datorn mot vilopuls 78 vid samma timme) och på emulatorerna hela vägen till andningen på klockan.

## Det som inte är löst eller inte verifierat

- **Bluetooth-hoppet** för klockans svarsknappar (`/konsiliet/svar`) och "Andas 60 s" (`/konsiliet/andas`) är
  testat med adb-bryggan, inte med en parkopplad klocka. Samma kod tar emot dem.
- **Teamets svar på "varför är jag så trött"** missade sömnskulden (7 h 24 min) och de sena nätterna, och sa
  att sömnen var god. Snabbsvaret visar dem, men faktabladet till teamet saknar sömnskuld och datorn efter
  midnatt. Det ligger i `fakta.py`, som en annan session äger; önskemålet står här i stället för som en ändring.
- **Headroom under hela veckan låg under 55** för personen (sömnen var 7,2 h i snitt), så planen sa aldrig
  "träna" på en passdag och passpåminnelsen skickades aldrig i simuleringen. Det är regeln som den är skriven
  (50 + 8 x (sömn - 7,5)), men för någon som sover 7 timmar blir det nästan aldrig grönt. Värt att se över när
  det finns riktig data.
- **Startsidan i den publika demon** är fortfarande kontoret: demon kör utan vardag-rutinerna.
- Riktiga användare har inte provat något av detta. Allt ovan är en agent som spelar en användare.

## Skärmbilder

I `docs/skarmbilder/`, alla märkta i bilden med en remsa (`tools/etikett.py`). Mobil och klocka är emulatorer
mot testservern, webben är Chromium headless mot samma server.

| Bild | Vad den visar |
|---|---|
| [anv-fore-mobil-sensorer.png](skarmbilder/anv-fore-mobil-sensorer.png) | Före: första skärmen efter installationen. Ingen rad om träning, tom pulskurva. |
| [anv-fore-mobil-post-langt-ned.png](skarmbilder/anv-fore-mobil-post-langt-ned.png) | Före: POST-skärmen två svep ned. |
| [anv-mobil-idag.png](skarmbilder/anv-mobil-idag.png) | Idag: beslutet, planen, varför, veckans pass och sömnen. |
| [anv-mobil-stressknuff.png](skarmbilder/anv-mobil-stressknuff.png) | Stressknuffen med Andas 60 s och Inte nu. |
| [anv-mobil-snabbsvar.png](skarmbilder/anv-mobil-snabbsvar.png) | Snabbsvaret i tråden några sekunder efter frågan. |
| [anv-mobil-utan-nat.png](skarmbilder/anv-mobil-utan-nat.png) | Idag utan nät: senaste svaret med en rad om att servern inte nås. |
| [anv-mobil-plan-och-knuffar.png](skarmbilder/anv-mobil-plan-och-knuffar.png) | Inställningar: passdagar, tider, tysta timmar, budget, knuffar av/på. |
| [anv-mobil-besoksunderlag.png](skarmbilder/anv-mobil-besoksunderlag.png) | Besöksunderlaget öppnat från Inställningar. |
| [anv-klocka-idag.png](skarmbilder/anv-klocka-idag.png) | Klockans startsida med dagens beslut och plan. |
| [anv-klocka-ruta.png](skarmbilder/anv-klocka-ruta.png) | Rutan med Headroom och dagens beslut. |
| [anv-klocka-pass-live.png](skarmbilder/anv-klocka-pass-live.png) | Under passet: puls, zon och målzon i BPM. |
| [anv-klocka-pass-klart.png](skarmbilder/anv-klocka-pass-klart.png) | Sammanfattningen direkt efter passet. |
| [anv-klocka-passdag.png](skarmbilder/anv-klocka-passdag.png) | Passpåminnelsen på klockan med Starta pass, Om 1 h, Inte i dag. |
| [anv-klocka-andas.png](skarmbilder/anv-klocka-andas.png), [anv-klocka-andas-klar.png](skarmbilder/anv-klocka-andas-klar.png) | 60 sekunders andning och pulsen efteråt. |
| [anv-webb-idag.png](skarmbilder/anv-webb-idag.png) | Webbens Idag med förklaringarna utfällda. |
| [anv-webb-trad.png](skarmbilder/anv-webb-trad.png) | En tråd med Gör så här överst. |
