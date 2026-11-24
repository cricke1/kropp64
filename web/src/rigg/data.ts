// Datakällor för riggvyn. Livekällan läser sensorerna från servern och WebSocket-strömmen,
// demokällan är ett manus med syntetiska värden (märks "Demo - syntetisk data" i vyn).
// Båda svarar på sample(t), där t är riggens klocka i sekunder. Då kan inspelningen stega tiden exakt.

import { api, live, type Ev } from '../api'
import { ymd } from '../format'

export type Komp = 'hjarta' | 'flaktar' | 'kylflans' | 'psu' | 'chassi'

export interface RiggData {
  /** Klockfrekvens, BPM. null = ingen puls de senaste 10 minuterna. */
  hr: number | null
  /** Andningsfrekvens, andetag per minut. */
  resp: number | null
  /** Hudtemperatur och dess baslinje (median senaste dygnet), °C. */
  hud: number | null
  hudBas: number | null
  /** Idle-klock: vilopulsens baslinje (lägsta 10-minutersmedian per natt, median av 14 nätter). */
  idle: number | null
  /** Headroom 0-100 från /api/aterhamtning. */
  headroom: number | null
  /** Termisk strypning 0-1: puls över Idle-klock i vila. 0 när kroppen är under last. */
  strypning: number
  /** Under last (steg senaste 10 min), då räknas förhöjd puls inte som strypning. */
  last: boolean
  /** Viloläge: natt och i vila. */
  vilolage: boolean
  /** Tråd som pågår, med den komponent den handlar om. */
  trad: { komp: Komp; metric: string; titel: string } | null
  /** Akut larm: lugn röd kontur och en saklig textrad. */
  akut: { komp: Komp; titel: string; text: string } | null
}

export interface Kalla {
  readonly demo: boolean
  sample(t: number): RiggData
  start(): void
  stop(): void
  kvitteraAkut(): void
}

export function kompFor(metric: string | null | undefined): Komp {
  const m = String(metric ?? '')
  if (/^hr|puls|hrv|vilopuls/.test(m)) return 'hjarta'
  if (/resp|andning|spo2|syre/.test(m)) return 'flaktar'
  if (/skin|temp|hud|stress/.test(m)) return 'kylflans'
  if (/sleep|somn|aterhamt|headroom|recovery/.test(m)) return 'psu'
  if (/steps|steg/.test(m)) return 'chassi'
  return 'hjarta'
}

const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v))

/** Strypningsindex: hur mycket pulsen i vila ligger över Idle-klock. Vaken vila ligger normalt 10-15 BPM över. */
export function strypningsindex(hr: number | null, idle: number | null, last: boolean) {
  if (hr == null || idle == null || last) return 0
  return clamp((hr - (idle + 15)) / 30)
}

export function strypningsord(s: number, last: boolean) {
  if (last) return 'under last'
  if (s < 0.15) return 'ingen'
  if (s < 0.45) return 'lätt'
  if (s < 0.75) return 'måttlig'
  return 'kraftig'
}

function natt(d = new Date()) {
  const h = d.getHours()
  return h >= 23 || h < 7
}

// ------------------------------------------------------------------ live

export class LiveKalla implements Kalla {
  readonly demo = false
  private d: RiggData = { hr: null, resp: null, hud: null, hudBas: null, idle: null, headroom: null, strypning: 0, last: false, vilolage: false, trad: null, akut: null }
  private hrTs = 0
  private respTs = 0
  private steg: [number, number][] = []
  private av: (() => void)[] = []
  private timers: number[] = []
  private tradId: string | null = null

  start() {
    live.start()
    for (const m of ['hr', 'resp_rate', 'skin_temp']) {
      const l = live.latest.get(m)
      if (l) this.prov(m, l.ts, l.value)
    }
    this.av.push(live.on((ev, history) => this.handelse(ev, history)))
    this.hamta()
    this.timers.push(window.setInterval(() => this.hamta(), 10 * 60 * 1000))
  }

  stop() {
    for (const f of this.av) f()
    for (const t of this.timers) clearInterval(t)
    this.av = []
    this.timers = []
  }

  kvitteraAkut() { this.d.akut = null }

  private prov(metric: string, ts: number, value: number) {
    if (metric === 'hr' && ts >= this.hrTs) { this.d.hr = value; this.hrTs = ts }
    if (metric === 'resp_rate' && ts >= this.respTs) { this.d.resp = value; this.respTs = ts }
    if (metric === 'skin_temp') this.d.hud = value
    if (metric === 'steps') this.steg.push([ts, value])
  }

  private async hamta() {
    const now = Date.now() / 1000
    const [hr, resp, hud, steg, idle, ah] = await Promise.allSettled([
      api.series('hr', 1), api.series('resp_rate', 3), api.series('skin_temp', 24, 600), api.series('steps', 1),
      api.series('hr', 14 * 24, 600), api.aterhamtning(),
    ])
    const last = (r: PromiseSettledResult<{ points: [number, number][] }>) => r.status === 'fulfilled' ? r.value.points[r.value.points.length - 1] : undefined
    const h = last(hr as any); if (h) this.prov('hr', h[0], h[1])
    const r = last(resp as any); if (r) this.prov('resp_rate', r[0], r[1])
    if (hud.status === 'fulfilled' && hud.value.points.length) {
      const v = hud.value.points.map((p) => p[1]).sort((a, b) => a - b)
      this.d.hudBas = v[Math.floor(v.length / 2)]
      const l = hud.value.points[hud.value.points.length - 1]
      if (now - l[0] < 3 * 3600) this.d.hud = l[1]
    }
    if (steg.status === 'fulfilled') this.steg = steg.value.points.slice()
    if (idle.status === 'fulfilled') {
      const per = new Map<string, number>()
      for (const [ts, v] of idle.value.points) {
        if (new Date(ts * 1000).getHours() >= 6) continue
        per.set(ymd(ts), Math.min(per.get(ymd(ts)) ?? Infinity, v))
      }
      const n = [...per.values()].sort((a, b) => a - b)
      if (n.length) this.d.idle = n[Math.floor(n.length / 2)]
    }
    if (ah.status === 'fulfilled') this.d.headroom = typeof ah.value?.poang === 'number' ? ah.value.poang : null
  }

  private handelse(ev: Ev, history: boolean) {
    const p = ev.payload
    if (ev.kind === 'sample.live') { this.prov(p.metric, p.ts, p.value); return }
    if (history) return
    if (ev.kind === 'consult.start') {
      const t = p.trigger ?? {}
      const metric = String(t.metric ?? (t.kind === 'question' ? '' : 'hr'))
      this.tradId = p.consult_id ?? null
      this.d.trad = { komp: kompFor(metric || t.title), metric, titel: String(t.title ?? t.question ?? 'Ny tråd') }
    }
    if (ev.kind === 'consult.verdict' && (!this.tradId || !p.consult_id || p.consult_id === this.tradId)) {
      this.d.trad = null
      this.tradId = null
    }
    if (ev.kind === 'alert.raise' && p.level === 'akut') {
      this.d.akut = { komp: kompFor(p.metric ?? p.rule ?? 'hr'), titel: String(p.title ?? 'Akut larm'), text: String(p.body ?? '') }
    }
  }

  sample(): RiggData {
    const now = Date.now() / 1000
    const d = this.d
    const hr = now - this.hrTs < 600 ? d.hr : null
    const resp = now - this.respTs < 1800 ? d.resp : null
    const stegNu = this.steg.filter((s) => s[0] > now - 600).reduce((a, s) => a + s[1], 0)
    const lastNu = stegNu >= 80 || (hr != null && hr >= 110 && stegNu > 0)
    const vilolage = natt() && stegNu === 0 && (hr == null || d.idle == null || hr <= d.idle + 12)
    return { ...d, hr, resp, last: lastNu, vilolage, strypning: strypningsindex(hr, d.idle, lastNu) }
  }
}

// ------------------------------------------------------------------ demo

/** Nyckelbilder: [sekund, puls, andning, hudtemp]. Varvet är 48 s och börjar om. */
const DEMO_KURVA: [number, number, number, number][] = [
  [0, 63, 14.5, 33.4],
  [6, 64, 14.6, 33.4],
  [10, 82, 16.5, 33.7],
  [14, 96, 18.0, 33.95],
  [20, 98, 18.4, 34.0],
  [25, 90, 17.0, 33.9],
  [30, 70, 15.0, 33.6],
  [33, 58, 13.0, 33.8],
  [37, 54, 12.0, 34.3],
  [42, 55, 12.4, 34.4],
  [45, 62, 14.2, 33.6],
  [48, 63, 14.5, 33.4],
]
export const DEMO_VARV = 48
const DEMO_TRAD: [number, number] = [13, 25]
const DEMO_VILA: [number, number] = [32, 43.5]

function kurva(t: number, k: number) {
  const P = DEMO_KURVA
  for (let i = 0; i < P.length - 1; i++) {
    const [a, b] = [P[i], P[i + 1]]
    if (t >= a[0] && t <= b[0]) {
      const f = (t - a[0]) / (b[0] - a[0])
      const e = f * f * (3 - 2 * f)
      return a[k] + (b[k] - a[k]) * e
    }
  }
  return P[0][k]
}

export class DemoKalla implements Kalla {
  readonly demo = true
  akut = false
  constructor(private offset = 0, akut = false) { this.akut = akut }
  start() { /* ingenting att ansluta */ }
  stop() { /* ingenting att koppla ner */ }
  kvitteraAkut() { this.akut = false }

  sample(t: number): RiggData {
    const tt = (((t + this.offset) % DEMO_VARV) + DEMO_VARV) % DEMO_VARV
    const brus = Math.sin(t * 1.7) * 0.6 + Math.sin(t * 0.43) * 0.5
    const hr = Math.round(kurva(tt, 1) + brus)
    const idle = 57
    const vilolage = tt >= DEMO_VILA[0] && tt < DEMO_VILA[1]
    const trad = tt >= DEMO_TRAD[0] && tt < DEMO_TRAD[1]
    return {
      hr, resp: kurva(tt, 2), hud: kurva(tt, 3), hudBas: 33.5, idle, headroom: vilolage ? 72 + Math.min(6, Math.round((tt - DEMO_VILA[0]) / 2)) : 72,
      strypning: strypningsindex(hr, idle, false), last: false, vilolage,
      trad: trad ? { komp: 'hjarta', metric: 'hr', titel: 'Överklockad utan last: pulsen i vila över baslinjen' } : null,
      akut: this.akut ? { komp: 'hjarta', titel: 'Test av akutlarm', text: 'Så här visas ett akutlarm i riggen. Det här är ett test i demoläget, inget riktigt larm.' } : null,
    }
  }
}
