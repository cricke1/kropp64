# Foruminlägg, utkast

Tråd i tävlingsforumet på SweClockers. Kort, konkret, inga säljord. Ersätt det inom hakparentes.

---

**Rubrik:** Konsiliet - lokalt läkarteam av AI-agenter som vaktar klockdatan, på en Mac mini M4 16 GB

Tja!

Köpte en Mac mini M4 (16 GB) när OpenClaw-hypen drog igång i januari och har kört agenter på den sen dess. Jag sitter
inne alldeles för mycket och vill börja träna, så jag byggde något som faktiskt tittar på datan klockan samlar in.

Kort:

- Pixel Watch -> mobil -> Mac mini, egen Wear OS-app och Android-app med köer som klarar nätavbrott
- En vakt med vanliga regler larmar direkt vid akuta grejer (puls 140+ i vila, SpO2 under 88, fall). Ingen LLM i den vägen.
- Vid avvikelser mot min egen baslinje kallas ett "konsilium" in: ordförande, 2-4 specialister, djävulens advokat.
  qwen3.5:9b i Ollama, allt lokalt.
- Varje påstående måste peka på en mätpunkt, journalrad eller ett provsvar. En granskare i ren Python stryker allt
  som inte matchar källdatan. Skrev specialisten "baslinje 73,2" när källan sa 72,5 så åkte det.
- Mötet visas som ett pixelkontor i webben där läkarna går runt, slår upp grejer och får sina meningar överstrukna live.

Lite siffror från bygget, för er som gillar sånt:

- 9B-modellen läser prompten i ca 75 tok/s och skriver i 17 tok/s på M4:an. Det är promptläsningen som dödar,
  inte genereringen.
- Med 16k kontext och Ollamas parallella läge tog en 6,6 GB-modell 14,7 GB och maskinen swappade. 8k kontext,
  KV-cache i q8_0, flash attention och en request åt gången: 9,1 GB och ett konsilium på ca 250 s i stället för 563.
- Första riktiga konsiliet: 278 s, 47 656 prompttokens och ingen bedömning alls. Agenterna hämtade samma data om och om igen.
- Första utvärderingen gav rätt brådska i 1 av 3 scenarier. Ja, dåligt. Det är därför akuta larm aldrig går via modellen.
  [FYLLS I: senaste siffran från eval/RESULTAT.md]

Koden är byggd med Claude Code, flera agenter parallellt som jag styrt. Allt som gick åt skogen står i en dagbok i repot
(launchd som inte fick läsa Skrivbordet, PowerShell 5.1 som gör stderr till fel, ett säkerhetshål där vem som helst på
LAN:et kunde skicka in falsk puls, osv). Tokens för både moln och lokalt räknas fram ur loggarna med ett skript, inga
uppskattningar.

Vad den hittat i min egen data: [FYLLS I, eller skriv ärligt att den inte gått tillräckligt länge än]

Demo (syntetisk data, tydligt märkt): [FYLLS I: länk]
Kod: [FYLLS I: GitHub-länk]
Film: [FYLLS I: YouTube-länk]

Det är inte en medicinteknisk produkt och ställer inga diagnoser, den ger underlag och frågor att ta med till vården.

Kör gärna sönder demon eller säg vad ni skulle mäta härnäst. Funderar själv på [FYLLS I: nästa steg].
