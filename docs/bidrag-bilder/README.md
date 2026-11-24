# Bilder till tävlingsbidraget

Tio bilder, 1920x1080 PNG, alla under 5 MB. Ingen bild visar riktig hälsodata. Märkningen syns i varje bild.

| Bild | Visar | Data |
|---|---|---|
| 01-kontoret-i-arbete.png | Pixelkontoret mitt i ett konsilium, samtalet till höger | Demo: manus, syntetiskt (banner överst) |
| 02-granskaren-stryker.png | Granskaren stryker kardiologens påstående om hjärtmuskelinflammation | Demo: manus, syntetiskt (banner överst) |
| 03-bedomningen.png | Slutbedömningen med nivå och frågor att ta med till vården | Demo: manus, syntetiskt (banner överst) |
| 04-oversikt.png | Översikten: mätartavlor, återhämtning med öppen formel, tidslinje | Syntetisk testdata från web/dev/ingest.mjs (banner överst) |
| 05-puls-vid-datorn.png | Sömn, nätter, puls per programkategori vid datorn, träningsbelastning | Syntetisk testdata (banner överst) |
| 06-systemet.png | Nördpanelen: unified memory, modeller i minnet, tokens, latens, databas | Minnet och modellerna är Mac minins verkliga värden när bilden togs; mätvärdena i databasen är syntetiska (banner överst) |
| 07-arkitektur.png | Arkitekturen, samma som docs/arkitektur.svg | Diagram |
| 08-mobilappen.png | Mobilappen: Idag, tidslinje, fråga, testlarm | Emulator, syntetisk testdata (märkt under varje skärm) |
| 09-klockappen.png | Klockappen: välja pass, pass pågår, puls. Runda skärmar; på de två första är översta raden mörklagd eftersom innehållet hade scrollat in under klockslaget | Emulator, syntetisk testdata (märkt under varje skärm) |
| 10-kontoret-pa-mobilen.png | Kontoret i mobilformat genom ett helt möte | Demo: manus, syntetiskt (banner i varje ruta) |

01-06 är tagna med Playwright mot den publika demon (`drift/publik-demo.sh`), viewport 1680x945 med skalfaktor 8/7.
08-09 är sammansatta av märkta skärmbilder från docs/skarmbilder. 10 är bildrutor ur docs/video (9:16).

Saknas fortfarande: en bild från ett riktigt konsilium på riktig data. Den läggs till när systemet har gått
på ägarens egen klocka en tid, och märks då "riktig data".
