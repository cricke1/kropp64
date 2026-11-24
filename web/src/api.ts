// Klient mot Konsiliet-servern. REST för historik, WebSocket för allt som händer live.

export type EventKind =
  | 'sample.live' | 'vakt.anomaly' | 'consult.start' | 'agent.move' | 'agent.think' | 'agent.tool'
  | 'agent.say' | 'agent.handoff' | 'review.strike' | 'consult.verdict' | 'alert.raise' | 'sync.1177'
  | (string & {})

export interface Ev {
  id: number | null
  ts: number | null
  kind: EventKind
  payload: Record<string, any>
}

export interface Consult {
  id: string
  started: number
  ended: number | null
  trigger: any
  verdict: any
  stats: any
  transcript?: any[]
}

export interface JournalRow { id: string; date: string; unit?: string; author?: string; kind?: string; title?: string; text: string }
export interface LabRow { id: string; date: string; analyte: string; value: number | null; value_raw: string; unit?: string; ref_low?: number | null; ref_high?: number | null; flag?: string | null }
export interface SleepSession { id: string; start: number; end: number; stages: { start: number; end: number; stage: string }[]; source?: string }

const base = (() => {
  const u = new URL('.', location.href)
  return u.pathname.replace(/\/$/, '')
})()

export class HttpError extends Error {
  constructor(public status: number, msg: string) { super(msg) }
}

export async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(base + path, { headers: { accept: 'application/json' }, ...init })
  if (!r.ok) throw new HttpError(r.status, `${r.status} ${r.statusText}`)
  return r.json() as Promise<T>
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(base + path, {
    method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new HttpError(r.status, `${r.status} ${r.statusText}`)
  return r.json() as Promise<T>
}

export interface Series {
  metric: string
  /** [ts, värde]. Med step: hinkens median. */
  points: [number, number][]
  /** [ts, min, max] per hink, bara när servern tunnat ut (step > 0). */
  band: [number, number, number][] | null
}

// Med step svarar servern med en punkt per hink: [ts, min, max, median] (db.downsample).
// Steg summeras i klienten och ska därför aldrig tunnas ut till median.
async function fetchSeries(metric: string, hours: number, step?: number): Promise<Series> {
  const st = metric === 'steps' ? 0 : step ?? 0
  const r = await getJSON<{ metric: string; points: number[][] }>(`/api/series/${encodeURIComponent(metric)}?hours=${hours}${st ? `&step=${st}` : ''}`)
  const raw = r.points ?? []
  const wide = raw.length > 0 && raw[0].length >= 4
  return {
    metric: r.metric,
    points: raw.map((p) => [p[0], wide ? p[3] : p[1]] as [number, number]),
    band: wide ? raw.map((p) => [p[0], p[1], p[2]] as [number, number, number]) : null,
  }
}

export const api = {
  health: () => getJSON<{ ok: boolean; ts: number }>('/api/health'),
  kallor: () => getJSON<{ source: string; n: number; first: number; last: number; test: boolean }[]>('/api/kallor'),
  metrics: () => getJSON<{ metric: string; n: number; first: number; last: number }[]>('/api/metrics'),
  series: (metric: string, hours: number, step?: number) => fetchSeries(metric, hours, step),
  sleep: (days = 14) => getJSON<SleepSession[]>(`/api/sleep?days=${days}`),
  events: (limit = 500) => getJSON<Ev[]>(`/api/events?limit=${limit}`),
  consults: () => getJSON<Consult[]>('/api/consults'),
  consult: (id: string) => getJSON<Consult>(`/api/consults/${encodeURIComponent(id)}`),
  ask: (question: string, hours: number) => postJSON<{ consult_id: string }>('/api/consult', { question, hours }),
  journal: () => getJSON<{ journal: JournalRow[]; labs: LabRow[] }>('/api/journal'),
  system: () => getJSON<any>('/api/system'),
  aterhamtning: () => getJSON<any>('/api/aterhamtning'),
  brief: () => postJSON<{ datum: string; text: string; fakta: any }>('/api/brief', {}),
  datorn: (hours: number) => getJSON<{ timmar: number; kategorier: Record<string, { minuter: number; puls_median: number | null }> }>(`/api/datorn?hours=${hours}`),
  sync1177: () => postJSON<{ started: boolean }>('/api/sync/1177', {}),
  idag: () => getJSON<any>('/api/idag'),
  vecka: () => getJSON<any>('/api/vecka'),
  pass: (dagar = 14) => getJSON<any[]>(`/api/pass?dagar=${dagar}`),
  notiser: (dagar = 7) => getJSON<any>(`/api/notiser?dagar=${dagar}`),
  knuffSvar: (typ: string, svar: string, minuter?: number) => postJSON<any>('/api/knuff/svar', { typ, svar, minuter }),
}

// ------------------------------------------------------------------ live-ström

type Listener = (ev: Ev, history: boolean) => void
export type ConnState = 'connecting' | 'open' | 'closed'

class Live {
  state: ConnState = 'connecting'
  latest = new Map<string, { ts: number; value: number }>()
  private listeners = new Set<Listener>()
  private stateListeners = new Set<() => void>()
  private retry = 0
  private seen = new Set<number>()
  private arrivals: number[] = []
  started = false

  start() {
    if (this.started) return
    this.started = true
    this.connect()
  }

  private connect() {
    this.setState('connecting')
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    let sock: WebSocket
    try {
      sock = new WebSocket(`${proto}//${location.host}${base}/ws`)
    } catch {
      this.scheduleReconnect()
      return
    }
    // Servern skickar historiken först. Allt som kommer inom den första stunden räknas som historik.
    let historyUntil = performance.now() + 600
    sock.onopen = () => { this.retry = 0; this.setState('open'); historyUntil = performance.now() + 400 }
    sock.onmessage = (m) => {
      let ev: Ev
      try { ev = JSON.parse(m.data) } catch { return }
      if (ev.id != null) {
        if (this.seen.has(ev.id)) return
        this.seen.add(ev.id)
      }
      const history = performance.now() < historyUntil && ev.kind !== 'sample.live'
      if (!history) this.arrivals.push(Date.now())
      if (ev.kind === 'sample.live') {
        const p = ev.payload
        this.latest.set(p.metric, { ts: p.ts, value: p.value })
      }
      for (const l of this.listeners) l(ev, history)
    }
    sock.onclose = () => { this.setState('closed'); this.scheduleReconnect() }
    sock.onerror = () => { try { sock.close() } catch { /* stängd redan */ } }
  }

  private scheduleReconnect() {
    const wait = Math.min(15000, 800 * 2 ** this.retry++)
    setTimeout(() => this.connect(), wait)
  }

  private setState(s: ConnState) {
    this.state = s
    for (const l of this.stateListeners) l()
  }

  on(l: Listener) { this.listeners.add(l); return () => { this.listeners.delete(l) } }
  onState(l: () => void) { this.stateListeners.add(l); return () => { this.stateListeners.delete(l) } }

  /** Händelser per minut, mätt i klienten (sista 60 s). */
  eventsPerMinute() {
    const cut = Date.now() - 60000
    this.arrivals = this.arrivals.filter((t) => t > cut)
    return this.arrivals.length
  }
}

export const live = new Live()
