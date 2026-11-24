# API-önskemål från mobil- och klockappen

Saker som apparna (wear/, android/) behöver eller skulle ha nytta av i servern. Apparna fungerar
med dagens API; punkterna nedan är förbättringar eller luckor som just nu löses på klientsidan.

## 1. Nya mätvärdesnamn som skickas till /api/ingest

| metric | källa | betydelse |
|---|---|---|
| `hr` | watch, health_connect | puls, slag/min |
| `steps` | watch, health_connect | steg i intervallet som slutar vid ts (delta, inte dygnssumma) |
| `steps_daily`, `calories_daily`, `floors_daily`, `distance_daily` | watch | dygnssumma enligt klockan |
| `calories`, `floors`, `distance`, `elevation_gain` | watch | delta per intervall (kcal, våningar, meter, meter) |
| `activity_state` | watch | 0 okänt, 1 vardag, 2 träning, 3 sover (ändringstidpunkt) |
| `fall_detected` | watch | 1 när klockans falldetektering slår till |
| `exercise` | watch | träningspass: ExerciseType-id vid start, 0 vid slut |
| `exercise_calories` | watch | total förbrukning för passet, vid slut |
| `hrv_rmssd` | health_connect | ms |
| `hr_resting` | health_connect | vilopuls |
| `spo2` | health_connect | procent |
| `resp_rate` | health_connect | andetag/min |
| `skin_temp` / `skin_temp_delta` | health_connect | absolut °C om baslinje finns, annars avvikelse mot baslinje. Blandas aldrig. |
| `exercise_minutes`, `exercise_type_hc` | health_connect | träningspass som Fitbit/Pixel skrivit |
| `hs_*` | watch | övriga typer klockan erbjuder passivt (framtidssäkring) |

Sömnpass från Health Connect skickas till `/api/ingest/sleep` med `id` = `hc-<Health Connect-id>`.
Utöver `awake, light, deep, rem` kan `stage` vara `sleeping` (sover, fas okänd) och `unknown`.

## 2. Testdata från emulator: källan `watch-emulator`

Klockappen märker all data från en emulator med `source = "watch-emulator"` (Health Services
testläge ger syntetiska värden). Önskemål: vakten och baslinjen ska hoppa över källor som innehåller
`emulator`, eller servern ska vägra dem när den kör skarpt. Under utvecklingen har jag testat mot en
separat serverinstans med egen databas (`KONSILIET_DB=~/.konsiliet/emulator-test.db`, port 8797) så att
den riktiga databasen inte fått syntetiska punkter.

## 3. Avduplicering mellan källor

Samma puls och samma steg kan komma både från klockappen (`watch`) och från Health Connect
(`health_connect`, skrivet av Fitbit-appen). Primärnyckeln (metric, ts, source) gör att båda sparas.
`vakt._resting()` summerar steg över alla källor, så steg räknas dubbelt där båda finns. Förslag:
källprioritet per mätvärde (watch före health_connect för hr/steps när båda täcker samma minut),
eller filtrera på källa i `_window()`.

## 4. Behörighet för WebSocket och webbvyn

- `/ws` har ingen `auth`. REST kräver `X-Device-Token` men live-strömmen (med larm och samtal) gör det inte.
  Förslag: acceptera token som query-parameter `?token=` på `/ws` (webbläsare kan inte sätta egna headers på WebSocket).
- Mobilappen visar pixelkontoret i en WebView. `X-Device-Token` följer bara med på första sidladdningen,
  inte på webbappens egna anrop (`/api/...`, `/ws`, JS/CSS). Via Cloudflare Tunnel utan Access-cookie
  kommer kontoret därför inte åt datan. Förslag: `GET /?token=...` som sätter en httpOnly-cookie som `auth` också godtar.

## 5. Träningspass som egen typ

Pass skickas i dag som mätvärden (`exercise`, `exercise_calories`, `exercise_minutes`). Ett eget
`POST /api/ingest/exercise` med (id, start, end, typ, källa) vore tydligare och låter vakten bortse från
hög puls under pass utan att gissa via steg.

## 6. Falldetektering som akut regel

`fall_detected` kommer in som mätvärde (värde 1). Förslag: vaktregel som larmar `akut` direkt när en
sådan punkt kommer in, utan att vänta på nästa vaktvarv.

## 7. Port

Port 8787 på Mac minin används av ett annat projekt. Appen har nu `http://100.69.247.16:8790` som standard.
