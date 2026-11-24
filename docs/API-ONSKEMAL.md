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

## Från webben (web/)

Webben (web/) byggs mot serverns API som det ser ut i server/src/konsiliet/api.py. Här är det som
saknas eller skulle göra webben bättre. Inget av det blockerar: webben fungerar utan, och tar automatiskt
till sig fälten när de finns.

### W1. Nedsampling av tidsserier: `GET /api/series/{metric}?hours=168&step=300`

Sju dygn puls från klockan blir hundratusentals punkter och flera MB JSON, för mycket för mobilen.
Önskan: valfri parameter `step` (sekunder). Servern returnerar då en punkt per hink.
Helst `[ts, min, max, median]` per hink, annars median. Utan `step`: som i dag.

Webben skickar redan `step` (30, 120 eller 300 beroende på period) och tunnar ut till min/max per
pixelkolumn i klienten tills servern gör det.

### W2. Latens per steg i `GET /api/system`

Systemet-panelen har en tabell för latens som i dag visar streck. Önskat fält:

```json
"pipeline": [
  {"step": "Mottagning (ingest)", "p50_ms": 4, "p95_ms": 11, "n": 812},
  {"step": "Vakt, regelkoll", "p50_ms": 9, "p95_ms": 30, "n": 140},
  {"step": "Specialist, per verktygsrunda", "p50_ms": 8200, "p95_ms": 19000, "n": 31},
  {"step": "Granskning", "p50_ms": 2, "p95_ms": 5, "n": 12},
  {"step": "Hela konsiliet", "p50_ms": 94000, "p95_ms": 160000, "n": 3}
]
```

### W3. Ren genereringshastighet per modell

`tokens_sedan_start.per_model` har `output_tokens` och `seconds`, så webben räknar tokens/s som
ut-tokens delat med hela anropstiden (inklusive promptbearbetning). Ollama ger `eval_count`/`eval_duration`
och `prompt_eval_count`/`prompt_eval_duration` per anrop. Önskat per modell:
`{"gen_tokens_per_s": 21.4, "prompt_tokens_per_s": 380}`.

### W4. Läsbara källor

Citat i `agent.say` är korta referenser: `S:hr:start-slut`, `J:id`, `L:id`, `N:id`.
`S:` tolkar webben själv. För `J:`, `L:` och `N:` hämtar webben /api/journal och /api/sleep och slår upp id.
Enklare och robustare vore något av:

- `cites` som objekt: `{"ref": "J:abc", "label": "Journal 2025-03-12", "kind": "journal"}`, eller
- `GET /api/ref/{ref}` som returnerar posten.

Okända referenser (till exempel baslinjejämförelser) visas i dag som "Baslinje".

### W5. Vilket yttrande en strykning gäller

`review.strike` har `target` (agenten) och `claim`. Påståendet är ofta inte ordagrant med i agentens
sammanfattning, så webben kan inte alltid stryka rätt mening i pratbubblan och visar då strykningen som
eget kort ovanför agenten. Önskat: `say_index` eller ett id på det `agent.say` som påståendet hör till,
eller att påståendena skickas med i `agent.say` som `claims: [{text, kallor}]`.

### W6. `members` i `consult.start`

Servern skickar hela teamet, men ordföranden kallar bara in 2-4 specialister. Kontoret låter alla
medlemmar gå till bordet. Önskat: bara de som faktiskt deltar (ordförande, valda specialister, advokat,
granskare), eller ett `agent.move ... to: "bordet"` per deltagare (som redan görs senare i mötet).

### Platser som kontoret förstår i `agent.move`

`bordet`, `skrivbord_<id>` (eller bara `skrivbord`), `arkivet`, `labbet`, `tavlan`, `kaffe`, `dorr`,
eller ett annat agent-id (gå fram till den agenten). Okänt mål tolkas som bordet.

### W7. Behörighet i WebView

Webben anropar `/api/...` och `/ws` med relativa sökvägar och skickar inga egna headers. Punkt 4 ovan (cookie via `?token=`) löser webbens behov också.
