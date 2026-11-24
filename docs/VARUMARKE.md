# Kropp64 - stilguide

Projektet heter **Kropp64** (skrivs alltid så: versal K, siffrorna ihop). Domän: kropp64.se.
Tagline: **Sensorpanelen för din viktigaste rigg: dig själv.** Förklaring i en mening där det behövs:
"Som AIDA64 och HWiNFO64, fast för kroppen, och med ett lokalt läkarteam av AI-agenter som läser sensorerna."

Namnhistorik (för RESAN): arbetsnamnet Konsiliet byttes när vi såg att "konsilium" på svenska främst betyder
kyrkomöte; "Överklockad" testades men kunde betyda vilket hårdvaruverktyg som helst. Kropp64 säger både kropp och
hårdvarumonitor direkt.

Idén: kroppen är riggen, jag är hårdvaran, översikten ser ut och känns som en sensorpanel (HWiNFO-känsla: tät
tabell med Aktuellt / Min / Max / Medel per sensor, värden i tabulära siffror), och läkarteamet är en supporttråd
på forumet. Humorn talar SweClockers-språk. Ordet "överklockad" får användas i texter ("överklockad utan last").
Nämn AIDA64/HWiNFO bara som jämförelse i text, aldrig som logga eller i namn på funktioner. Aldrig em dash (—),
använd bindestreck (-).

## Sensorpanelen (översikten)
Rubriker i HWiNFO-stil: Sensor | Aktuellt | Min | Max | Medel, grupperat som hårdvara:
"Hjärta (Pixel Watch)": Klockfrekvens, Idle-klock, Timingmarginal (HRV); "Andning": Andningsfrekvens, SpO2;
"Kylning": Hudtemperatur, Headroom; "Last": Steg, Stresstest (träning), Uptime vid datorn.

## Grundregel: akut är aldrig skämt

Akutlarm, sms till anhöriga, brådskegrad "kontakta vården" och allt som rör att söka vård skrivs rakt,
sakligt och utan ordlekar: "Mycket hög puls i vila, 151 slag/min. Svarar du inte inom 5 minuter skickas
sms till ...". Humorn hör hemma i vardagen, varumärket och kontoret, aldrig där det gäller.

## Läkarteamet = supporttråden

| Intern id | Roll i UI | Kort beskrivning |
|---|---|---|
| ordforande | Trådstartaren (allmänläkare) | öppnar tråden, kallar in specialister, markerar lösningen |
| kardiolog | Kardiologen | svarar i tråden om puls och hjärta |
| somn | Sömnläkaren | |
| idrott | Idrottsläkaren | |
| stress | Stressläkaren | |
| labb | Labbet | provsvar |
| advokat | Trollet (djävulens advokat) | "har du testat att dra åt armbandet?" Ifrågasätter alltid, vardagliga förklaringar |
| granskare | Moderatorn | stryker inlägg: "Strukit av moderator. Anledning: saknar källa." |

Händelsetexter: "Kardiologen svarade i tråden", "Moderatorn strök ett påstående", "Trådstartaren markerade
tråden som löst". Slutbedömningen visas som **Markerad som lösning**. Konsilium heter **tråd** i UI.

## Kroppen som hårdvara (översikt och vardag)

| Mätvärde/funktion | Term i UI | Exempel |
|---|---|---|
| puls | Klockfrekvens | "Klockfrekvens 67 BPM (beats, inte MHz)" |
| vilopuls | Idle-klock | |
| hög puls i vila (avvikelse, ej akut) | Överklockad utan last | |
| HRV | Timingmarginal (HRV) | högre är bättre, som minnes-timings med marginal |
| stress | Termisk strypning | "Lätt strypning under kodpasset 21-23" |
| återhämtning | Headroom | "Headroom 72/100" |
| sömn | Viloläge | djupsömn = "nattlig defrag" |
| träning | Stresstest | "Dagens stresstest: 25 min intervaller" |
| stillasittande | AFK för länge | knuffen: "AFK i 90 min. Fem minuter räcker." |
| datortid | Uptime | "Uptime vid datorn: 6 h, varav 4 h kod" |
| morgonbrief | POST-skärmen | börjar "POST: OK" eller "POST: varning, headroom 41" |
| besöksunderlag | Felrapporten (till vårdcentralen) | PDF:ens titel får vara saklig: "Besöksunderlag" |
| systemet/nördpanel | Systemet (rigg nr 2: Mac minin) | Mac minin är också på gränsen: 9,1 av 16 GB |

Mätvärden visas alltid med riktig enhet bredvid skämtet (BPM, ms, %), så att det går att lita på siffrorna.

## Ton
Torr, nördig, självironisk. Som en kunnig forumanvändare, inte som en reklambyrå. Max ett skämt per vy,
resten är rak information. Inga emojis, inga utropstecken i rad, inga versaler som underrubriker.
