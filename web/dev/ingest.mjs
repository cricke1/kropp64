// TESTDATA för utveckling av webben. Skickar SYNTETISKA mätpunkter till en Konsiliet-server.
// Kör ALDRIG mot servern med din riktiga databas: allt hamnar i samma tabell som klockans data.
// Starta en testserver med egen databas, till exempel:
//   cd server && KONSILIET_DB=/tmp/konsiliet-test.db uv run uvicorn konsiliet.api:app --port 8799
// och kör sedan:
//   node web/dev/ingest.mjs --url http://127.0.0.1:8799 [--backfill 72] [--once]
// Alla punkter får source "dev-syntetisk" så att de går att känna igen och radera.

const args = Object.fromEntries(process.argv.slice(2).map((a, i, all) => a.startsWith('--') ? [a.slice(2), all[i + 1]?.startsWith('--') || all[i + 1] == null ? true : all[i + 1]] : null).filter(Boolean))
if (!args.url || args.url === true) {
  console.error('Ange --url till en TESTSERVER, t.ex. --url http://127.0.0.1:8799. Se kommentaren överst i filen.')
  process.exit(1)
}
const URL = String(args.url).replace(/\/$/, '')
const BACKFILL_H = Number(args.backfill ?? 72)
const SOURCE = 'dev-syntetisk'

let seed = 42
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
const noise = (a) => (rnd() - 0.5) * 2 * a

function hourOf(ts) { return new Date(ts * 1000).getHours() + new Date(ts * 1000).getMinutes() / 60 }
function asleep(h) { return h >= 23.5 || h < 7 }
function training(ts) { const d = new Date(ts * 1000); const h = hourOf(ts); return d.getDay() % 2 === 0 && h >= 18 && h < 19 }

function sampleAt(ts) {
  const h = hourOf(ts)
  const out = []
  let hr
  if (asleep(h)) hr = 54 + 4 * Math.sin(h) + noise(2)
  else if (training(ts)) hr = 128 + 22 * Math.sin((h - 18) * Math.PI) + noise(6)
  else hr = 68 + 6 * Math.sin(h / 3) + noise(5)
  out.push(['hr', Math.round(hr)])
  out.push(['spo2', Math.round(asleep(h) ? 95 + noise(1.5) : 97 + noise(1))])
  out.push(['resp_rate', +(asleep(h) ? 13.5 + noise(1) : 15.5 + noise(1.5)).toFixed(1)])
  return out
}

async function post(path, body) {
  const r = await fetch(URL + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`)
  return r.json()
}

async function backfill() {
  const now = Date.now() / 1000
  const start = now - BACKFILL_H * 3600
  let batch = []
  const flush = async () => { if (batch.length) { await post('/api/ingest', { source: SOURCE, samples: batch }); batch = [] } }
  for (let ts = start; ts < now - 60; ts += 60) {
    for (const [metric, value] of sampleAt(ts)) batch.push({ ts, metric, value })
    const h = hourOf(ts)
    if (asleep(h) && Math.floor(ts / 60) % 5 === 0) batch.push({ ts, metric: 'hrv_rmssd', value: Math.round(48 + noise(10)) })
    if (!asleep(h)) batch.push({ ts, metric: 'steps', value: training(ts) ? Math.round(140 + noise(20)) : Math.max(0, Math.round(rnd() < 0.3 ? 40 + noise(40) : 0)) })
    if (Math.floor(ts / 60) % 10 === 0) batch.push({ ts, metric: 'skin_temp', value: +(asleep(h) ? 34.6 + noise(0.2) : 33.4 + noise(0.3)).toFixed(2) })
    // datortid: kvällar med kod och spel
    if (!asleep(h) && h >= 19.5 && h < 23) batch.push({ ts, metric: h < 21.5 ? 'dator_kod' : 'dator_spel', value: 1 })
    else if (!asleep(h) && h >= 9 && h < 12) batch.push({ ts, metric: rnd() < 0.6 ? 'dator_webb' : 'dator_chatt', value: 1 })
    if (batch.length > 2000) await flush()
  }
  await flush()
  // sömnpass för de senaste nätterna
  for (let n = 0; n < Math.ceil(BACKFILL_H / 24); n++) {
    const d = new Date(); d.setHours(7, 0, 0, 0)
    const end = d.getTime() / 1000 - n * 86400
    const s0 = end - 7.5 * 3600
    if (end > now) continue
    const stages = []
    let t = s0
    const cycle = ['light', 'deep', 'light', 'rem']
    let i = 0
    while (t < end) {
      const stage = rnd() < 0.06 ? 'awake' : cycle[i++ % 4]
      const len = (stage === 'awake' ? 4 : stage === 'deep' ? 25 - i : stage === 'rem' ? 12 + i * 2 : 30) * 60 * (0.7 + rnd() * 0.6)
      stages.push({ start: t, end: Math.min(end, t + Math.max(180, len)), stage })
      t += Math.max(180, len)
    }
    await post('/api/ingest/sleep', { id: `dev-${Math.round(end)}`, start: s0, end, stages, source: SOURCE })
  }
  console.log(`Bakåtfyllt ${BACKFILL_H} h syntetisk testdata till ${URL}`)
}

async function liveLoop() {
  console.log('Skickar syntetiska livepunkter var 2:a sekund. Ctrl+C för att sluta.')
  for (;;) {
    const ts = Date.now() / 1000
    const samples = sampleAt(ts).map(([metric, value]) => ({ ts, metric, value }))
    try { await post('/api/ingest', { source: SOURCE, samples }) } catch (e) { console.error(String(e)) }
    await new Promise((r) => setTimeout(r, 2000))
  }
}

if (BACKFILL_H > 0) await backfill()
if (!args.once) await liveLoop()
