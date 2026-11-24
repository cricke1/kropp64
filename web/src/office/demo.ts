// Demoläge. Ett manus med påhittade händelser så att kontoret kan visas utan språkmodellerna.
// Allt här är syntetiskt och märks "Demo - syntetisk data" i gränssnittet. Inget av det är riktiga mätvärden.

import type { Ev } from '../api'
import type { ScreenData } from './scene'

// En påhittad natt: 23:00 till 07:00 dagen före i dag.
function night() {
  const d = new Date()
  d.setHours(7, 0, 0, 0)
  const end = d.getTime() / 1000
  return { start: end - 8 * 3600, end }
}

function at(h: number, m: number) {
  const { end } = night()
  const d = new Date(end * 1000)
  if (h >= 12) d.setDate(d.getDate() - 1)
  d.setHours(h, m, 0, 0)
  return d.getTime() / 1000
}

export function demoEvents(): Ev[] {
  const cid = 'demo'
  const win: [number, number] = [at(2, 14), at(2, 31)]
  const script: [number, string, Record<string, any>][] = [
    [0, 'consult.start', {
      trigger: { kind: 'anomaly', metric: 'hr', title: 'Överklockad utan last: vilopulsen över baslinjen', detail: 'Demo: vilopuls 71 BPM mot normalt 57 vid den här tiden.', window: win, hours: 12, demo: true },
      members: ['ordforande', 'kardiolog', 'somn', 'idrott', 'stress', 'labb', 'advokat', 'granskare'],
    }],
    [1.0, 'agent.say', { agent: 'ordforande', to: 'alla', text: 'Vakten flaggade att vilopulsen i natt låg klart över baslinjen. Vi tar det i tur och ordning. Kardiologen börjar med pulsen.', cites: [{ kind: 'series', metric: 'hr', start: win[0], end: win[1] }] }],
    [0.5, 'agent.think', { agent: 'kardiolog' }],
    [1.2, 'agent.tool', { agent: 'kardiolog', tool: 'hamta_serie', args: { metric: 'hr', timmar_bakat: 12 } }],
    [1.0, 'agent.say', { agent: 'kardiolog', to: 'alla', text: 'Pulsen låg på 68 till 74 mellan 02:14 och 02:31, mot normalt 57 vid den tiden. Jämn kurva, inga plötsliga hopp.', cites: [{ kind: 'series', metric: 'hr', start: win[0], end: win[1] }, 'Puls baslinje 28 d'] }],
    [0.6, 'agent.say', { agent: 'advokat', to: 'kardiolog', text: 'Har du testat att dra åt armbandet? Klockan kan ha suttit löst.' }],
    [0.4, 'agent.tool', { agent: 'kardiolog', tool: 'hamta_serie', args: { metric: 'spo2', timmar_bakat: 12 } }],
    [0.8, 'agent.say', { agent: 'kardiolog', to: 'advokat', text: 'Syremättnaden mättes utan avbrott under samma period, så klockan verkar ha suttit på.', cites: [{ kind: 'series', metric: 'spo2', start: at(2, 0), end: at(3, 0) }] }],
    [0.5, 'agent.think', { agent: 'somn' }],
    [1.0, 'agent.tool', { agent: 'somn', tool: 'hamta_somn', args: { natter: 1 } }],
    [0.8, 'agent.say', { agent: 'somn', to: 'alla', text: 'Sömnen var kort i natt: 5 h 40 min mot snittet 7 h 10 min. Djupsömnen kom sent och var kortare än vanligt.', cites: [{ kind: 'sleep', start: night().start }] }],
    [0.6, 'agent.tool', { agent: 'idrott', tool: 'hamta_serie', args: { metric: 'hr', timmar_bakat: 24 } }],
    [0.8, 'agent.say', { agent: 'idrott', to: 'alla', text: 'Klockan registrerade ett pass med hög puls i går kväll, 20:05 till 21:10. Hård träning sent ger ofta förhöjd puls natten efter.', cites: [{ kind: 'series', metric: 'hr', start: at(20, 5), end: at(21, 10) }] }],
    [0.5, 'agent.think', { agent: 'labb' }],
    [1.0, 'agent.tool', { agent: 'labb', tool: 'hamta_labb', args: { analyt: 'Hb' } }],
    [0.8, 'agent.say', { agent: 'labb', to: 'ordforande', text: 'De senaste provsvaren förklarar inte det här. Blodvärdet låg inom referensintervallet i mars.', cites: [{ kind: 'lab', analyte: 'Hb', date: '2025-03-12' }] }],
    [0.3, 'agent.handoff', { agent: 'labb', to: 'ordforande', item: 'Provsvar mars' }],
    [0.6, 'agent.tool', { agent: 'stress', tool: 'hamta_serie', args: { metric: 'hrv_rmssd', timmar_bakat: 72 } }],
    [0.8, 'agent.say', { agent: 'stress', to: 'alla', text: 'HRV har legat lågt tre nätter i rad. Det passar med träningsbelastning, sömnbrist eller en infektion på väg. Datan kan inte skilja dem åt.', cites: [{ kind: 'series', metric: 'hrv_rmssd', start: at(0, 0) - 2 * 86400, end: at(6, 0) }] }],
    [0.8, 'agent.say', { agent: 'kardiolog', to: 'alla', text: 'Sammantaget tyder det på en begynnande hjärtmuskelinflammation.' }],
    [0.6, 'agent.think', { agent: 'granskare' }],
    [0.8, 'review.strike', { claim: 'tyder det på en begynnande hjärtmuskelinflammation', reason: 'Inget i datan pekar specifikt mot hjärtmuskelinflammation. Det kräver EKG och blodprover, som saknas.' }],
    [0.4, 'agent.say', { agent: 'granskare', to: 'alla', text: 'Det påståendet stryks. Övriga påståenden har källor.' }],
    [0.4, 'agent.handoff', { agent: 'kardiolog', to: 'ordforande', item: 'Pulsutdrag 02:00-03:00' }],
    [0.6, 'agent.tool', { agent: 'ordforande', tool: 'sok_journal', args: { sokord: 'hjärta' } }],
    [0.8, 'agent.say', { agent: 'ordforande', to: 'alla', text: 'Journalen nämner inga tidigare hjärtbesvär.', cites: [{ kind: 'journal', date: '2025-03-12', title: 'Hälsokontroll' }] }],
    [0.6, 'agent.say', { agent: 'advokat', to: 'alla', text: 'Då är ett sent träningspass plus kort sömn den enklaste förklaringen. Vi ska inte göra mer av det än så.' }],
    [0.8, 'agent.say', { agent: 'ordforande', to: 'alla', text: 'Vi bevakar. Ingen åtgärd nu. Om nattpulsen är hög två nätter till, eller om feber eller bröstsmärta tillkommer, ska vården kontaktas.' }],
    [0.6, 'consult.verdict', { verdict: {
      level: 'bevaka',
      summary: 'Förhöjd nattpuls som bäst förklaras av ett sent träningspass och kort sömn. Inget tyder på akut fara. Bevaka de kommande nätterna.',
      questions: ['Är förhöjd nattpuls efter kvällsträning något att följa upp?', 'Behövs EKG om HRV fortsätter vara låg?'],
    } }],
  ]
  // Som servern: efter arbete vid skrivbordet går agenten tillbaka till bordet.
  const withMoves: typeof script = []
  for (const row of script) {
    withMoves.push(row)
    const [, kind, p] = row
    if (kind === 'agent.tool' && /serie|somn/.test(String(p.tool))) withMoves.push([0.2, 'agent.move', { agent: p.agent, to: 'bordet' }])
  }
  const t0 = Date.now() / 1000 - 600
  let t = t0
  return withMoves.map(([dt, kind, payload], i) => {
    t += dt
    return { id: -1 - i, ts: t, kind, payload: { consult_id: cid, ...payload } }
  })
}

/** Påhittad kurva till skärmväggen i demoläget. */
export function demoScreen(metric: string): ScreenData {
  const { start, end } = night()
  const pts: [number, number][] = []
  let seed = metric.length * 17
  const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280)
  const base = metric === 'hr' ? 57 : metric === 'spo2' ? 96 : metric === 'hrv_rmssd' ? 46 : metric === 'resp_rate' ? 14 : 50
  const s0 = metric === 'hr' ? start - 4 * 3600 : start
  for (let ts = s0; ts <= end; ts += 120) {
    const h = new Date(ts * 1000).getHours() + new Date(ts * 1000).getMinutes() / 60
    let v = base + (rnd() - 0.5) * (metric === 'spo2' ? 0.6 : 3)
    if (metric === 'hr') {
      if (h >= 20 && h < 21.2) v += 55 + rnd() * 30
      if (h >= 2.2 && h < 2.55) v += 13 + rnd() * 3
      if (h >= 23 || h < 6) v -= 3
    }
    if (metric === 'hrv_rmssd') v -= 12
    pts.push([ts, v])
  }
  const win: [number, number] = [at(2, 14), at(2, 31)]
  return { metric, points: pts, window: metric === 'hr' ? win : null }
}
