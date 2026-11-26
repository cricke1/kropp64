# Foruminlägg, utkast

Kort, fem rader, två bilder och en länk. Bifoga 04-oversikt.png (sensorpanelen) och 02-granskaren-stryker.png.

---

**Rubrik:** Kropp64 - HWiNFO för kroppen, med ett lokalt AI-läkarteam på en Mac mini 16 GB

Byggde en sensorpanel för kroppen: Pixel Watch in, Min/Max/Medel per sensor ut, och klockfrekvensen under varje kod- och spelpass.
När något avviker startar en supporttråd där lokala agenter (qwen3.5:9b i Ollama) svarar, och en moderator i ren Python stryker varje påstående som inte finns i datan.
Akuta larm går aldrig via en språkmodell, och ingen hälsodata lämnar Mac minin.
Allt som gick fel, inklusive tokens med och utan cache, står i repot.
Demo (syntetisk data): https://demo.kropp64.se  Kod: [FYLLS I: github.com/cricke1/kropp64]
