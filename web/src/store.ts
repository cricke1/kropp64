// Delat tillstånd: live-strömmen, regissören för kontoret och några små hjälpkrokar.

import { useEffect, useState } from 'preact/hooks'
import { api, live, type Ev } from './api'
import { Director } from './office/director'
import { demoScreen } from './office/demo'
import type { ScreenData } from './office/scene'
import { refLookup } from './format'

export const director = new Director()

// Skärmväggen: i demoläget påhittad kurva, annars riktig tidsserie från servern.
director.screenProvider = async (metric, hours, window) => {
  if (director.state.mode === 'demo') return demoScreen(metric)
  const r = await api.series(metric, Math.min(168, Math.max(1, hours)))
  return { metric, points: r.points, window, live: false } as ScreenData
}
director.idleScreen = () => {
  const pts = liveHr.slice(-240)
  return { metric: 'hr', points: pts, live: true }
}

// Livepulsen på skärmväggen när inget möte pågår.
const liveHr: [number, number][] = []
let liveHrLoaded = false
function loadIdleHr() {
  if (liveHrLoaded) return
  liveHrLoaded = true
  api.series('hr', 3).then((r) => {
    liveHr.splice(0, liveHr.length, ...r.points)
    if (!director.state.active && director.state.mode === 'live') director.scene.screen = { metric: 'hr', points: liveHr.slice(-240), live: true }
  }).catch(() => { liveHrLoaded = false })
}

export const anomalies: Ev[] = []

// Senaste morgonbrief, 1177-status och notiser (stillasittande).
export const side = {
  brief: null as Ev | null,
  sync: null as Ev | null,
  toasts: [] as { id: number; title: string; body: string; at: number }[],
}
const sideListeners = new Set<() => void>()
const emitSide = () => sideListeners.forEach((l) => l())
let toastN = 0
export function toast(title: string, body: string) {
  const id = ++toastN
  side.toasts = [...side.toasts.slice(-2), { id, title, body, at: Date.now() }]
  emitSide()
  setTimeout(() => { side.toasts = side.toasts.filter((t) => t.id !== id); emitSide() }, 9000)
}
export function dismissToast(id: number) { side.toasts = side.toasts.filter((t) => t.id !== id); emitSide() }
export function useSide() {
  const [, set] = useState(0)
  useEffect(() => { const f = () => set((n) => n + 1); sideListeners.add(f); return () => { sideListeners.delete(f) } }, [])
  return side
}

// Källreferenser i samtalen (J:id, L:id, N:id) blir läsbara när journal och sömn är hämtade.
let refsLoaded = false
export function loadRefs() {
  if (refsLoaded) return
  refsLoaded = true
  api.journal().then((j) => {
    for (const r of j.journal) refLookup.journal.set(r.id, { date: r.date, title: r.title, unit: r.unit })
    for (const r of j.labs) refLookup.labs.set(r.id, { date: r.date, analyte: r.analyte, value_raw: r.value_raw, unit: r.unit })
    director.bump()
  }).catch(() => { refsLoaded = false })
  api.sleep(120).then((rows) => { for (const r of rows) refLookup.sleep.set(r.id, { start: r.start, end: r.end }); director.bump() }).catch(() => {})
}

live.on((ev, history) => {
  if (ev.kind === 'sample.live' && ev.payload.metric === 'hr') {
    liveHr.push([ev.payload.ts, ev.payload.value])
    if (liveHr.length > 2000) liveHr.splice(0, liveHr.length - 2000)
    if (!director.state.active && director.state.mode === 'live') director.scene.screen = { metric: 'hr', points: liveHr.slice(-240), live: true }
  }
  if (ev.kind === 'vakt.anomaly') anomalies.push(ev)
  if (ev.kind === 'brief.morgon') { side.brief = ev; emitSide() }
  if (ev.kind === 'sync.1177') { side.sync = ev; emitSide() }
  if (ev.kind === 'nudge.move' && !history) toast(String(ev.payload.title ?? 'Påminnelse'), String(ev.payload.body ?? ''))
  director.live(ev, history)
})
live.onState(() => { if (live.state === 'open') { loadIdleHr(); loadRefs() } })

export function useDirector() {
  const [, set] = useState(0)
  useEffect(() => director.on(() => set((n) => n + 1)), [])
  return director
}

export function useLive() {
  const [, set] = useState(0)
  useEffect(() => {
    let raf = 0
    const bump = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; set((n) => n + 1) }) }
    const a = live.on(bump), b = live.onState(bump)
    return () => { a(); b(); cancelAnimationFrame(raf) }
  }, [])
  return live
}

export function useAsync<T>(fn: () => Promise<T>, deps: any[] = []): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true })
  const [n, setN] = useState(0)
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true }))
    fn().then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: String(e?.message ?? e), loading: false }))
    return () => { alive = false }
  }, [...deps, n])
  return { ...state, reload: () => setN((x) => x + 1) }
}

// ------------------------------------------------------------ routing

export function parseHash() {
  const h = location.hash.replace(/^#\/?/, '')
  const [path, q] = h.split('?')
  const parts = path.split('/').filter(Boolean)
  return { view: parts[0] || 'kontoret', arg: parts[1] ? decodeURIComponent(parts[1]) : null, query: new URLSearchParams(q ?? '') }
}

export function useRoute() {
  const [r, setR] = useState(parseHash())
  useEffect(() => {
    const f = () => setR(parseHash())
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [])
  return r
}

export function go(path: string) { location.hash = '#/' + path }
