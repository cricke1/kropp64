# Klocka och mobil: bygga, installera, testa

## Delarna

- `wear/` Pixel Watch-appen. Health Services (passiv övervakning + träningspass), Room-kö på klockan,
  skickar batchar till mobilen med `MessageClient.sendRequest` och raderar först när mobilen kvitterat.
- `android/` Mobilappen. Tar emot batcharna (`WatchListenerService`), sparar i Room, laddar upp till
  `POST /api/ingest` med WorkManager, håller en förgrundstjänst med WebSocket mot `/ws` för larm och live,
  läser Health Connect (bakåt i tiden och sedan inkrementellt), skickar sms till anhöriga om användaren slagit på det.

Båda apparna har `applicationId = "se.konsiliet"`. Det måste vara samma, och båda måste vara signerade
med samma nyckel, annars levererar Wearable Data Layer ingenting mellan dem. Bygg därför alltid båda på
samma dator (samma debug-nyckel).

## Bygga

```
cd wear    && ./gradlew assembleDebug    # wear/app/build/outputs/apk/debug/app-debug.apk
cd android && ./gradlew assembleDebug    # android/app/build/outputs/apk/debug/app-debug.apk
```

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
2. Öppna Konsiliet på mobilen. Under Inställningar: serveradress (standard `http://100.69.247.16:8790`, Tailscale måste vara på i mobilen),
   enhetstoken (samma som `KONSILIET_DEVICE_TOKENS` på servern), "Spara och testa".
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

## Testa med emulatorer

Se avsnittet om emulatorer i [RESAN.md](../RESAN.md) för vad som fungerade och inte. Syntetisk data från
klockemulatorn märks `watch-emulator` och visas som "testdata från emulator" i mobilappen.
