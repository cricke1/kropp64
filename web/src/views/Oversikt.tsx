import { useEffect, useMemo, useState } from 'preact/hooks'
import { api, live, type Ev, type Series, type SleepSession } from '../api'
import { Hypnogram, normStage, Spark, STAGES, Timeline, type Band, type Marker } from '../charts/charts'
import { dayMonth, duration, fmtNum, hm, metricMeta, ymd } from '../format'
import { anomalies, useAsync, useLive } from '../store'
import { BriefPanel, DatornPanel, DatorStrip, RecoveryScore, Sync1177 } from './Halsa'

const TILES = ['hr', 'hrv_rmssd', 'spo2', 'resp_rate', 'steps', 'skin_temp']
const RANGES: [number, string][] = [[6, '6 h'], [24, '24 h'], [72, '3 d'], [168, '7 d']]

function ago(ts: number) {
  const s = Date.now() / 1000 - ts
  if (s < 60) return `${Math.max(0, Math.round(s))} s sedan`
  if (s < 3600) return `${Math.round(s / 60)} min sedan`
  if (s < 86400) return `${Math.round(s / 3600)} h sedan`
  return dayMonth(ts)
}

function startOfDay() { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime() / 1000 }

export function Oversikt() {
  const l = useLive()
  const [tick, setTick] = useState(0)
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), 30000); return () => clearInterval(t) }, [])
  // de senaste timmarna per mätvärde, för mätartavlorna
  const recent = useAsync(async () => {
    const out: Record<string, Series> = {}
    await Promise.all(TILES.map(async (m) => {
      try { out[m] = await api.series(m, m === 'steps' || m === 'hrv_rmssd' ? 24 : 2, 30) } catch { out[m] = { metric: m, points: [], band: null } }
    }))
    return out
  }, [tick])
  const metrics = useAsync(() => api.metrics(), [])

  return (
    <div class="oversikt">
      <div class="pagehead">
        <h1>Översikt</h1>
        <p>{metrics.data?.length ? `${metrics.data.reduce((a, m) => a + m.n, 0).toLocaleString('sv-SE')} mätpunkter i databasen` : metrics.error ? 'Ingen kontakt med servern' : ''}</p>
        <span style="flex:1" />
        <Sync1177 />
      </div>
      <div class="tiles">
        {TILES.map((m) => <Tile metric={m} pts={recent.data?.[m]?.points ?? []} band={recent.data?.[m]?.band ?? null} latest={l.latest.get(m)} />)}
      </div>
      <div class="grid two">
        <RecoveryScore />
        <BriefPanel />
      </div>
      <TimelinePanel />
      <div class="grid two">
        <SleepPanel />
        <RecoveryPanel />
      </div>
      <div class="grid two">
        <DatornPanel />
        <LoadPanel />
      </div>
    </div>
  )
}

function Tile({ metric, pts, band, latest }: { metric: string; pts: [number, number][]; band: [number, number, number][] | null; latest?: { ts: number; value: number } }) {
  const meta = metricMeta(metric)
  const merged = useMemo(() => {
    if (!latest) return pts
    const last = pts[pts.length - 1]
    return !last || latest.ts > last[0] ? [...pts, [latest.ts, latest.value] as [number, number]] : pts
  }, [pts, latest?.ts])
  let value: number | null = null, ts: number | null = null, sub = ''
  if (metric === 'steps') {
    const sod = startOfDay()
    const today = merged.filter((p) => p[0] >= sod)
    value = today.length ? today.reduce((a, p) => a + p[1], 0) : null
    ts = today.length ? today[today.length - 1][0] : null
    sub = 'i dag'
  } else if (merged.length) {
    const last = merged[merged.length - 1]
    value = last[1]; ts = last[0]
    // spann senaste timmen: hinkarnas riktiga min och max om servern tunnat ut, annars punkterna
    const cut = Date.now() / 1000 - 3600
    const lo = band ? band.filter((b) => b[0] > cut).map((b) => b[1]) : merged.filter((p) => p[0] > cut).map((p) => p[1])
    const hi = band ? band.filter((b) => b[0] > cut).map((b) => b[2]) : lo
    if (lo.length > 2) sub = `${fmtNum(Math.min(...lo), meta.digits)}-${fmtNum(Math.max(...hi), meta.digits)} senaste timmen`
  }
  const stale = ts != null && Date.now() / 1000 - ts > 900
  return (
    <div class={`panel tile ${stale ? 'stale' : ''}`} style={{ '--c': meta.color }}>
      <div class="tile-top"><span>{meta.label}</span>{ts != null && <span class="faint num">{ago(ts)}</span>}</div>
      <div class="tile-val num"><b>{value == null ? '-' : fmtNum(value, metric === 'steps' ? 0 : meta.digits)}</b><span>{meta.unit}</span></div>
      <div class="tile-sub faint">{value == null ? 'Ingen data än' : sub || ' '}</div>
      {metric !== 'steps' && <Spark points={merged.slice(-400)} band={band} color={meta.color} />}
    </div>
  )
}

function TimelinePanel() {
  const [metric, setMetric] = useState('hr')
  const [hours, setHours] = useState(24)
  const [nonce, setNonce] = useState(0)
  const meta = metricMeta(metric)
  const step = hours <= 6 ? 0 : hours <= 24 ? 30 : hours <= 72 ? 120 : 300
  const series = useAsync(() => api.series(metric, hours, step), [metric, hours, nonce])
  const journal = useAsync(() => api.journal(), [])
  const events = useAsync(() => api.events(1000), [nonce])
  // ny livepunkt: läs om var 60:e sekund på kort skala
  useEffect(() => {
    if (hours > 24) return
    const t = setInterval(() => setNonce((n) => n + 1), 60000)
    return () => clearInterval(t)
  }, [hours])

  const to = Date.now() / 1000, from = to - hours * 3600
  const points = useMemo(() => {
    const p = series.data?.points ?? []
    const l = live.latest.get(metric)
    return l && (!p.length || l.ts > p[p.length - 1][0]) ? [...p, [l.ts, l.value] as [number, number]] : p
  }, [series.data])

  const anomalyEvents: Ev[] = useMemo(() => {
    const seen = new Set<number>()
    return [...(events.data ?? []).filter((e) => e.kind === 'vakt.anomaly'), ...anomalies].filter((e) => {
      if (e.id != null) { if (seen.has(e.id)) return false; seen.add(e.id) }
      return true
    })
  }, [events.data, anomalies.length])

  const bands: Band[] = useMemo(() => anomalyEvents
    .filter((e) => !e.payload.metric || e.payload.metric === metric)
    .map((e) => {
      const w = e.payload.window
      const a = Array.isArray(w) ? w[0] : (e.ts ?? 0) - 600, b = Array.isArray(w) ? w[1] : e.ts ?? 0
      return { from: a, to: b, label: e.payload.title ?? 'Avvikelse' }
    })
    .filter((b) => b.to >= from), [anomalyEvents, metric, from])

  const markers: Marker[] = useMemo(() => {
    const j = journal.data
    if (!j) return []
    const toTs = (d: string) => Date.parse(d + 'T12:00:00') / 1000
    return [
      ...j.journal.map((r) => ({ ts: toTs(r.date), label: r.title ?? r.kind ?? 'Journal', kind: 'journal' as const })),
      ...j.labs.map((r) => ({ ts: toTs(r.date), label: `${r.analyte} ${r.value_raw}`, kind: 'lab' as const })),
    ].filter((m) => m.ts >= from && m.ts <= to)
  }, [journal.data, from])

  const inRange = anomalyEvents.filter((e) => (e.ts ?? 0) >= from)

  return (
    <section class="panel tl-panel">
      <header>
        <h2>Tidslinje</h2>
        <div class="tl-controls">
          <div class="seg" role="group" aria-label="Mätvärde">
            {['hr', 'hrv_rmssd', 'spo2', 'resp_rate', 'skin_temp', 'steps'].map((m) => <button aria-pressed={metric === m} onClick={() => setMetric(m)}>{metricMeta(m).short}</button>)}
          </div>
          <div class="seg" role="group" aria-label="Tidsperiod">
            {RANGES.map(([h, label]) => <button aria-pressed={hours === h} onClick={() => setHours(h)}>{label}</button>)}
          </div>
        </div>
      </header>
      <div class="body">
        <div class="tl-meta">
          <span><i class="sw" style={{ background: meta.color }} />{meta.label} <span class="faint">{meta.unit}</span></span>
          <span><i class="sw band" />Avvikelse från vakten</span>
          <span><i class="sw journal" />Journal</span>
          <span><i class="sw lab" />Provsvar</span>
          <span class="faint num">{points.length.toLocaleString('sv-SE')} punkter</span>
        </div>
        {series.error ? <div class="empty">Kunde inte hämta tidsserien ({series.error}).</div>
          : points.length < 2 && !series.loading ? <div class="empty">Ingen data för {meta.label.toLowerCase()} de senaste {hours} timmarna.</div>
          : <Timeline points={points} color={meta.color} unit={meta.unit} from={from} to={to} bands={bands} markers={markers} digits={meta.digits} gapSec={Math.max(600, step * 4)} />}
        <DatorStrip from={from} to={to} nonce={nonce} />
        {(inRange.length > 0 || markers.length > 0) && (
          <ul class="tl-list">
            {inRange.slice(-6).reverse().map((e) => (
              <li><span class="tag danger">{e.payload.level === 'akut' ? 'Akut' : 'Avvikelse'}</span><span class="num faint">{e.ts ? `${dayMonth(e.ts)} ${hm(e.ts)}` : ''}</span><span>{e.payload.title}</span><span class="muted">{e.payload.detail}</span></li>
            ))}
            {markers.slice(0, 6).map((m) => (
              <li><span class={`tag ${m.kind === 'journal' ? '' : 'warn'}`}>{m.kind === 'journal' ? 'Journal' : 'Prov'}</span><span class="num faint">{ymd(m.ts)}</span><span>{m.label}</span></li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

function SleepPanel() {
  const sleep = useAsync(() => api.sleep(14), [])
  const last: SleepSession | undefined = sleep.data?.[sleep.data.length - 1]
  const totals = useMemo(() => {
    const t: Record<string, number> = { awake: 0, rem: 0, light: 0, deep: 0 }
    for (const s of last?.stages ?? []) t[normStage(s.stage)] += s.end - s.start
    return t
  }, [last])
  const asleep = totals.rem + totals.light + totals.deep
  return (
    <section class="panel">
      <header><h2>Sömn i natt</h2>{last && <span class="meta num">{hm(last.start)}-{hm(last.end)}</span>}</header>
      <div class="body">
        {!last ? <div class="empty">{sleep.error ? 'Kunde inte hämta sömndata.' : 'Inget sömnpass registrerat de senaste två veckorna.'}</div> : (
          <>
            <div class="sleep-sum">
              <div><span class="faint">Sömn</span><b class="num">{duration(asleep)}</b></div>
              {STAGES.map((s) => <div><span class="faint"><i class="sw" style={{ background: s.color }} />{s.label}</span><b class="num">{duration(totals[s.key])}</b></div>)}
            </div>
            <Hypnogram stages={last.stages} start={last.start} end={last.end} />
          </>
        )}
      </div>
    </section>
  )
}

/** Nattlig median (00-06) per natt. Visar ingenting som inte är uppmätt. */
function nightly(points: [number, number][], nights: number) {
  const by = new Map<string, number[]>()
  for (const [ts, v] of points) {
    const d = new Date(ts * 1000)
    if (d.getHours() >= 6) continue
    const k = ymd(ts)
    if (!by.has(k)) by.set(k, [])
    by.get(k)!.push(v)
  }
  const out: { day: string; median: number; n: number }[] = []
  for (const [day, vs] of [...by.entries()].sort()) {
    if (vs.length < 10) continue
    vs.sort((a, b) => a - b)
    out.push({ day, median: vs[Math.floor(vs.length / 2)], n: vs.length })
  }
  return out.slice(-nights)
}

function RecoveryPanel() {
  const data = useAsync(async () => {
    const [hrv, hr] = await Promise.all([api.series('hrv_rmssd', 14 * 24, 300), api.series('hr', 14 * 24, 300)])
    return { hrv: nightly(hrv.points, 14), hr: nightly(hr.points, 14) }
  }, [])
  const d = data.data
  return (
    <section class="panel">
      <header><h2>Nätterna</h2><span class="meta">Median 00-06, senaste 14 nätterna</span></header>
      <div class="body">
        {!d || (!d.hrv.length && !d.hr.length) ? <div class="empty">{data.loading ? 'Hämtar.' : 'För lite nattdata än. Kräver minst tio mätpunkter per natt.'}</div> : (
          <div class="recov">
            <NightBars rows={d.hrv} label="HRV" unit="ms" color="var(--hrv)" />
            <NightBars rows={d.hr} label="Vilopuls" unit="slag/min" color="var(--hr)" />
          </div>
        )}
      </div>
    </section>
  )
}

function NightBars({ rows, label, unit, color }: { rows: { day: string; median: number }[]; label: string; unit: string; color: string }) {
  if (!rows.length) return <div class="nb"><div class="nb-h"><span>{label}</span></div><div class="empty">Ingen data</div></div>
  const vals = rows.map((r) => r.median)
  const lo = Math.min(...vals), hi = Math.max(...vals)
  const sorted = [...vals].sort((a, b) => a - b)
  const med = sorted[Math.floor(sorted.length / 2)]
  const H = 64
  const y = (v: number) => H - 6 - ((v - lo) / Math.max(1e-6, hi - lo)) * (H - 14)
  const last = rows[rows.length - 1]
  return (
    <div class="nb">
      <div class="nb-h"><span>{label}</span><span class="num"><b style={{ color }}>{fmtNum(last.median)}</b> <span class="faint">{unit}, senaste natten</span></span></div>
      <svg viewBox={`0 0 ${rows.length * 14} ${H}`} preserveAspectRatio="none" class="nb-svg">
        <line x1="0" x2={rows.length * 14} y1={y(med)} y2={y(med)} class="nb-med" />
        {rows.map((r, i) => <rect x={i * 14 + 3} y={y(r.median)} width="8" height={H - y(r.median)} fill={color} opacity={i === rows.length - 1 ? 1 : 0.45} />)}
      </svg>
      <div class="nb-axis faint num"><span>{rows[0].day.slice(5)}</span><span>median {fmtNum(med)}</span><span>{last.day.slice(5)}</span></div>
    </div>
  )
}

const ZONES: [number, number, string][] = [[100, 120, '100-119'], [120, 140, '120-139'], [140, 160, '140-159'], [160, 999, '160+']]
const ZONE_COLORS = ['#7d9a8c', 'var(--resp)', 'var(--hrv)', 'var(--danger)']

function LoadPanel() {
  const data = useAsync(async () => {
    const r = await api.series('hr', 7 * 24, 30)
    const days = new Map<string, number[]>()
    const pts = r.points
    for (let i = 0; i < pts.length; i++) {
      const [ts, v] = pts[i]
      const dt = Math.min(300, i + 1 < pts.length ? pts[i + 1][0] - ts : 30)
      const z = ZONES.findIndex(([a, b]) => v >= a && v < b)
      if (z < 0) continue
      const k = ymd(ts)
      if (!days.has(k)) days.set(k, [0, 0, 0, 0])
      days.get(k)![z] += dt / 60
    }
    const out: { day: string; mins: number[] }[] = []
    for (let i = 6; i >= 0; i--) {
      const k = ymd(Date.now() / 1000 - i * 86400)
      out.push({ day: k, mins: days.get(k) ?? [0, 0, 0, 0] })
    }
    return out
  }, [])
  const rows = data.data ?? []
  const max = Math.max(30, ...rows.map((r) => r.mins.reduce((a, b) => a + b, 0)))
  const total = rows.reduce((a, r) => a + r.mins.reduce((x, y) => x + y, 0), 0)
  return (
    <section class="panel">
      <header><h2>Träningsbelastning</h2><span class="meta">Minuter per dag i pulszon, fasta gränser i slag/min</span></header>
      <div class="body">
        {!rows.length || total < 1 ? <div class="empty">{data.loading ? 'Hämtar.' : 'Ingen tid med puls över 100 de senaste sju dagarna.'}</div> : (
          <div class="load">
            <div class="load-legend">{ZONES.map((z, i) => <span><i class="sw" style={{ background: ZONE_COLORS[i] }} />{z[2]}</span>)}</div>
            <div class="load-rows">
              {rows.map((r) => {
                const sum = r.mins.reduce((a, b) => a + b, 0)
                return (
                  <div class="load-row">
                    <span class="faint num">{dayMonth(Date.parse(r.day + 'T12:00:00') / 1000)}</span>
                    <div class="load-bar">{r.mins.map((m, i) => m > 0 && <i style={{ width: `${(m / max) * 100}%`, background: ZONE_COLORS[i] }} title={`${ZONES[i][2]}: ${Math.round(m)} min`} />)}</div>
                    <span class="num">{Math.round(sum)} min</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
