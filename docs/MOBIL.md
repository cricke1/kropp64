# Klocka och mobil: bygga, installera, testa

## Delarna

- `wear/` Pixel Watch-appen. Health Services (passiv övervakning + träningspass), Room-kö på klockan,
  skickar batchar till mobilen med `MessageClient.sendRequest` och raderar först när mobilen kvitterat.
- `android/` Mobilappen. Tar emot batcharna (`WatchListenerService`), sparar i Room, laddar upp till
  `POST /api/ingest` med WorkManager, håller en förgrundstjänst med WebSocket mot `/ws` för larm och live,
  läser Health Connect (bakåt i tiden och sedan inkrementellt), skickar träningspass till
  `POST /api/ingest/exercise` (vid start och igen vid slut med samma id), skickar sms till anhöriga om användaren slagit på det.

Båda apparna har `applicationId = "se.konsiliet"`. Det måste vara samma, och båda måste vara signerade
med samma nyckel, annars levererar Wearable Data Layer ingenting mellan dem. Bygg därför alltid båda på
samma dator (samma debug-nyckel).

## Bygga

```
cd wear    && ./gradlew assembleDebug    # wear/app/build/outputs/apk/debug/app-debug.apk
cd android && ./gradlew assembleDebug    # android/app/build/outputs/apk/debug/app-debug.apk
```

De färdiga APK-filerna från Lenovon (byggda 2026-11-25) och debug-nyckeln som signerade dem ligger utanför repot i
`~/konsiliet-lenovo/android/` på Mac minin: `kropp64-mobil-debug.apk`, `kropp64-klocka-debug.apk` och
`debug.keystore` (SHA-256 börjar `e6bd925d`). Bygger du om på en annan dator: lägg nyckeln i `~/.android/debug.keystore`
först, annars får appen en annan signatur och måste avinstalleras (med sin lokala kö) innan den nya går att installera.

Kräver JDK 17 eller senare och Android SDK (platform 36). `local.properties` med `sdk.dir` skapas per dator.

## Installera på riktig Pixel-mobil och Pixel Watch

Mobilen:
1. Inställningar > Om telefonen > tryck sju gånger på Versionsnummer.
2. Inställningar > System > Utvecklaralternativ > Trådlös felsökning: på. Välj "Parkoppla enhet med kopplingskod".
3. På datorn: `adb pair <ip>:<parkopplingsport>` och ange koden, sedan `adb connect <ip>:<port>` (porten som visas överst under Trådlös felsökning).
4. `adb -s <ip>:<port> install -r android/app/build/outputs/apk/debug/app-debug.apk`

Klockan:
1. Inställningar > System > Om > tryck sju gånger på Versionsnummer.
2. Inställningar > Utvecklaralternativ > ADB-felsökning: på, och Trådlös felsökning: på. Klockan och datorn måste vara på samma wifi.
3. Trådlös felsökning > Parkoppla ny enhet: `adb pair <ip>:<port>` med koden, sedan `adb connect <ip>:<port>`.
4. `adb -s <klockans ip>:<port> install -r wear/app/build/outputs/apk/debug/app-debug.apk`

Första start:
1. Öppna Konsiliet på klockan och ge behörigheterna (puls, fysisk aktivitet, aviseringar, och sedan puls i bakgrunden "Tillåt alltid").
2. Öppna Konsiliet på mobilen. Första gången visas en startvy där serveradressen måste anges och testas,
   till exempel `http://<mac-minins-tailscale-ip>:8790` (Tailscale måste vara på i mobilen). Ingen adress är
   inbyggd i appen. Enhetstoken behövs bara via Cloudflare Tunnel (finns i `~/.konsiliet/device_tokens` på servern).
3. Health Connect: "Ge behörighet" och tillåt allt, inklusive "historik" och "i bakgrunden".
4. Stäng av batterioptimering för Konsiliet (knapp i Inställningar). Utan det kan Android pausa länken i viloläge.
5. Sms till anhöriga är avstängt. Slå på det själv, lägg till kontakter och välj väntetid.

## Felfall som är hanterade

| Händelse | Vad som händer |
|---|---|
| Mobilen utom räckhåll för klockan | Klockans kö växer (Room). När mobilen syns igen (`CAPABILITY_CHANGED`) töms kön direkt. Rensas efter 30 dagar. |
| Överföringen bryts mitt i en batch | Klockan har inte fått kvittens, raderna ligger kvar och skickas igen. Mobilen avduplicerar på (metric, ts, source). |
| Mobilen saknar nät | Raderna ligger i mobilens kö. WorkManager väntar på nät, nätverksåteruppringning startar uppladdning direkt när nätet kommer. |
| Servern nere, 5xx, 401, 429 | Försök igen med exponentiell backoff, plus en kontroll var 60:e sekund och ett periodiskt jobb var 15:e minut. Inget slängs. |
| Servern svarar 400/422 | Batchen delas tills den felande raden hittas. Den markeras avvisad (sparas lokalt), resten går igenom. |
| Svaret från servern tappas efter att den sparat | Batchen skickas igen. Servern gör INSERT OR REPLACE på (metric, ts, source), så inga dubbletter. |
| Processen dödas | Room är på disk, WorkManager-jobb överlever, förgrundstjänsten är START_STICKY. |
| Omstart av mobil | `BootReceiver` startar förgrundstjänsten, schemalägger uppladdning och Health Connect-synk, och lägger tillbaka ett väntande sms-alarm. |
| Omstart av klocka | `BootReceiver` registrerar om passiv övervakning (registreringen överlever inte omstart). |
| Doze | Förgrundstjänst av typen connectedDevice, och användaren kan undanta appen från batterioptimering. Sms-alarmet använder `setExactAndAllowWhileIdle`. |
| WebSocket dör tyst | OkHttp pingar var 25:e sekund. Återanslutning 1, 2, 4 ... 60 s, direkt vid nätbyte. Servern skickar de 300 senaste händelserna vid anslutning, så larm som kom under avbrottet missas inte (id-kontroll hindrar dubbelnotiser). |
| Health Connect-token går ut | De senaste 30 dagarna läses om och en ny token hämtas. |

## Ruta, komplikationer, widget och vibrationer (Kropp64)

Appnamnet i launchern är Kropp64 (applicationId är fortfarande `se.konsiliet`).

**Mobilen bygger en sammanfattning** (`android/.../widget/Summary.kt`): headroom (återhämtningspoängen från
`GET /api/aterhamtning`) med delarna, supporttrådens läge (pågående tråd och senaste lösningen ur
`GET /api/consults?limit=5`) och dagens steg mot målet (lokalt, samma regel som Idag-vyn). Den hämtas om
- några sekunder efter `consult.start`, `consult.verdict` och `brief.morgon` på live-länken (flera händelser i rad, t.ex.
  historiken vid anslutning, blir en hämtning),
- när appen öppnas,
- var 30:e minut med WorkManager (ingen nätverksvillkor: stegen räknas om även utan nät, serverdelen behålls
  och märks som gammal).

**Hemskärmswidget** (Glance, `KonsilietWidget`): Headroom 0-100 med Timing (HRV), Idle-klock (vilopuls) och
Viloläge (sömn), steg mot målet med stapel, och "Tråd pågår" eller "Markerad som lösning: ..." med
sammanfattningen. "Ta upp med vården" och "Kontakta vården nu" skrivs sakligt i bärnsten respektive rött.
Steg från emulatorn märks "testdata". `updatePeriodMillis` är 0, widgeten ritar bara det sparade och gör
inga egna nätverksanrop. Tryck öppnar appen.

**Mobil till klocka** (`WatchSync`): sammanfattningen läggs som dataobjekt `/konsiliet/status` med
`DataClient.putDataItem` (urgent). Data Layer synkar dataobjekt när klockan kommer inom räckhåll igen, så en
ändring under ett avbrott kommer fram efteråt och bara senaste läget skickas. Klockan cachar det
(`PhoneStatus`), läser det också direkt ur Data Layer när processen startar, och ignorerar underlag som är
äldre än det den har. Akuta larm och rörelsepåminnelser går som meddelanden (`/konsiliet/alert`,
`/konsiliet/nudge`).

**Ruta på klockan** (tile "Kropp64"): ring och siffra för headroom, Klockfrekvens i BPM, trådens läge och
"Synkad HH:MM" (bärnsten om mer än två timmar gammalt). Tryck öppnar klockappen. Läser bara cachen.
- Klockfrekvensen är ett dynamiskt värde (`PlatformHealthSources.heartRateBpm`) som rendraren uppdaterar
  själv, utan att rutan hämtas om.
- Ny status ritar om rutan direkt. `Surfaces.requestTile` binder till systemets uppdateringstjänst
  (`androidx.wear.tiles.action.BIND_UPDATE_REQUESTER` i hemskärmens paket) och skickar begäran, eftersom
  `TileService.getUpdater().requestUpdate()` inte gjorde något på Wear OS 6-emulatorn (biblioteket är reserv).
  Den väntar högst 3 s på anslutningen utanför huvudtråden, så att processen inte fryses innan begäran gått.
- Uppmätt på emulatorn: omritning 0,05 s efter ny status när rutan inte syns, 1,1-1,8 s när den syns, och
  högst 20 s när systemets strypning (en omritning per 20 s) slår till.
- Färskhetsintervallet är bara skyddsnät: 1 minut medan en tråd pågår, annars 15 minuter.
- I testet ska rutan läggas till via rutväljaren på klockan (håll på en ruta, plus). `DEBUG_SURFACE add-tile`
  fungerar för att visa den men användes inte för mätningarna.

**Komplikationer**: "Headroom" (RANGED_VALUE 0-100, SHORT_TEXT som reserv, mätarikon i stället för titel)
och "Supporttråden" (SHORT_TEXT "Pågår", "Bevaka", "Ta upp", "Vård nu", samt LONG_TEXT). Uppdateras när
statusen ändras, inte på timer.

**Vibrationer på klockan** (`alerts/Haptics.kt`):

| Händelse | Mönster (ms) | Hur |
|---|---|---|
| Akut larm (`alert.raise` nivå akut) | 3 x 500 på, 150 av, paus 600, igen; full styrka, ca 4 s | Vibrator, USAGE_ALARM, går igenom Stör ej |
| AFK för länge (`nudge.move`) | 90 på, 160 av, 90 på | mönster på notiskanalen |
| Tråden löst (ny lösning, högst 30 min gammal) | 280 på, 140 av, 70 på | mönster på notiskanalen |

Wear OS spelar inte notisvibrationer medan klockan laddar.

**Testa på emulatorerna** (ingen parkoppling, se RESAN.md): `android/tools/statusbrygga.ps1` låter mobilen
hämta sammanfattningen och lägga den i Data Layer som vanligt, och flyttar exakt samma JSON till klockan med
adb, där den går in i samma kod som `onDataChanged`. `-Meddelande` flyttar också senaste meddelandet
(påminnelse eller akut larm). Rutan kan också läggas till med
`am broadcast -a com.google.android.wearable.app.DEBUG_SURFACE --es operation add-tile --ecn component se.konsiliet/se.konsiliet.wear.tile.KonsilietTile`
och komplikationer med `--es operation set-complication ... --ei slot N --ei type 5` (RANGED_VALUE) eller 3 (SHORT_TEXT).

## Regler för sms till anhöriga

Reglerna ligger i `android/app/src/main/java/se/konsiliet/app/alerts/SmsPolicy.kt` och testas i `SmsPolicyTest`.

- Bara vaktens regler kan starta sms: `alert.raise` med nivå `akut` och fältet `rule`. Konsiliets bedömningar
  (har `consult_id`) ger notis men aldrig sms. En språkmodell ska aldrig kunna skicka sms.
- Larm "upptäckt i efterhand" och larm äldre än 30 minuter ger aldrig sms.
- Varje händelse hanteras högst en gång: appen sparar id:n för de senaste 500 hanterade händelserna, live som omskickade.
- Händelser som servern skickar om vid WebSocket-anslutning (`replay: true`) visas bara i listorna, med ett undantag:
  `alert.raise` yngre än 5 minuter (räknat på händelsens egen tid) som appen inte redan hanterat behandlas som live.
  Då ger ett kort avbrott i anslutningen inte ett missat larm.
- Fristen räknas från larmets egen tid, inte från när mobilen tog emot det.
- Fristen sätts av det första olösta akutlarmet och flyttas aldrig fram. Senare akutlarm läggs till i samma sms.
- "Jag mår bra" på något av larmen i kedjan stoppar hela kedjan.

## Testa med emulatorer

Se avsnittet om emulatorer i [RESAN.md](../RESAN.md) för vad som fungerade och inte. Syntetisk data från
klockemulatorn märks `watch-emulator` och visas som "testdata från emulator" i mobilappen.
