// Riggen: kroppen som PC-chassi i helskärm, med förklaring av vilken komponent som visar vilken sensor.

import { Riggvyn } from '../rigg/Riggvyn'
import { go } from '../store'

const RADER: [string, string, string, string][] = [
  ['Processor med tornkylare', 'Hjärtat', 'Klockfrekvens (puls), BPM', 'Slår i pulsens takt. Glödlisten lyser upp vid varje slag.'],
  ['Två fläktar', 'Lungorna', 'Andningsfrekvens, andetag/min', 'Varvar med andningen och ökar vid varje inandning. Vänster lunga är mindre, som i kroppen.'],
  ['Kylflänsar och chassi', 'Revbenen och huden', 'Hudtemperatur, °C, och termisk strypning', 'Färgen går från kall stålblå till varm bärnsten när pulsen i vila ligger över Idle-klock.'],
  ['Nätaggregat', 'Återhämtningen', 'Headroom, av 100', 'Mätaren på aggregatet. Beräknas en gång per dygn.'],
  ['Belysning och fläktar', 'Sömnen', 'Viloläge', 'På natten i vila dämpas ljuset, fläktarna går ner i varv och strömlampan andas.'],
]

export function Riggen({ query }: { query: URLSearchParams }) {
  const demo = __PUBLIK_DEMO__ || query.get('demo') === '1'
  return (
    <div class="riggen">
      <div class="pagehead">
        <h1>Riggen</h1>
        <p>Kroppen byggd som ett PC-chassi, styrd av sensorerna i realtid.</p>
        <span style="flex:1" />
        {!__PUBLIK_DEMO__ && (
          <div class="seg" role="group" aria-label="Datakälla">
            <button aria-pressed={!demo} onClick={() => go('riggen')}>Live</button>
            <button aria-pressed={demo} onClick={() => go('riggen?demo=1')}>Demo</button>
          </div>
        )}
      </div>
      <Riggvyn lage="full" demo={demo} />
      <section class="panel">
        <header><h2>Komponenterna</h2><span class="meta">Dra för att vrida, scrolla för att zooma</span></header>
        <table class="data rigg-tabell">
          <thead><tr><th>Komponent</th><th>I kroppen</th><th>Sensor</th><th>Så syns det</th></tr></thead>
          <tbody>{RADER.map((r) => <tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td class="muted">{r[3]}</td></tr>)}</tbody>
        </table>
        <div class="body muted rigg-not">
          När en tråd startar om ett mätvärde får komponenten en kontur och kameran glider dit. När tråden är markerad
          som löst glider den tillbaka. Vid ett akut larm står kameran still, komponenten får en röd kontur och larmet
          visas som en textrad.
          {demo && ' Demoläget spelar upp ett manus med syntetiska värden: pulsen stiger i vila, en tråd startar om hjärtat och efter lösningen går riggen i viloläge.'}
        </div>
      </section>
    </div>
  )
}
