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
