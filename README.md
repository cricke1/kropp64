# Konsiliet

Ett lokalt läkarteam av AI-agenter som vaktar min hälsodata dygnet runt, på en Mac mini.

Pixel Watch strömmar puls, HRV, SpO2, steg och sömn i realtid. En vakt-agent letar avvikelser mot
min egen baslinje. När den hittar något kallar den in konsiliet: specialistagenter som läser samma
data och journal, diskuterar, och lämnar en gemensam bedömning. En granskare stryker allt som inte
går att peka på en mätpunkt, en journalrad eller en källa. Allt körs lokalt. Ingen hälsodata lämnar huset.

## Delar

| Del | Var | Vad |
|---|---|---|
| `wear/` | Pixel Watch (Wear OS) | Läser sensorer via Health Services, strömmar till mobilen |
| `android/` | Mobilen | Tar emot klockdata, skickar till servern, notiser, sms till anhöriga, appens UI |
| `server/` | Mac mini | API, tidsseriedatabas, vakt, konsiliet, 1177-hämtare, live-ström |
| `web/` | Mac mini, via Cloudflare Tunnel | Tidslinje, pixelkontoret där läkarteamet syns jobba |
| `bench/` | Mac mini | Mätningar av lokala modeller: hastighet, minne, kvalitet |

## Dataflöde

```
Pixel Watch --(Wearable Data Layer)--> Android-app --(HTTPS, Cloudflare Tunnel + Access)--> Mac mini
                                                                                             |
                1177 (BankID-godkänd hämtning) --------------------------------------------->|
                                                                                             v
                                         SQLite tidsserie + journal  ->  Vakt  ->  Konsiliet  ->  Granskare
                                                                                             |
                                    Appen + webben (live via WebSocket) <--------------------+
```

## Principer

- Lokalt först. Språkmodellerna körs på Mac minin. Molnet används bara för att bygga koden.
- Inga påhittade siffror. Varje påstående i en bedömning ska peka på en mätpunkt, journalrad eller källa.
- Systemet ställer inga diagnoser. Det ger underlag och frågor att ta med till vården.

Se [RESAN.md](RESAN.md) för hela bygget, inklusive allt som gick fel.
