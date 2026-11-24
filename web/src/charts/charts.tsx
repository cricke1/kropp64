// Diagram. Tidslinjen använder uPlot (litet och snabbt), resten är handritad SVG.

import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'
import { hm, dayMonth } from '../format'

export function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** Tunnar ut till min och max per hink så att toppar inte försvinner. */
export function downsample(pts: [number, number][], buckets: number): [number[], number[]] {
  if (pts.length <= buckets * 2) return [pts.map((p) => p[0]), pts.map((p) => p[1])]
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0]
  const w = (t1 - t0) / buckets
  const xs: number[] = [], ys: number[] = []
  let i = 0
  for (let b = 0; b < buckets; b++) {
    const end = t0 + (b + 1) * w
    let lo: [number, number] | null = null, hi: [number, number] | null = null
    while (i < pts.length && pts[i][0] <= end) {
      const p = pts[i]
      if (!lo || p[1] < lo[1]) lo = p
      if (!hi || p[1] > hi[1]) hi = p
      i++
    }
    if (lo && hi) {
      const [a, c] = lo[0] <= hi[0] ? [lo, hi] : [hi, lo]
      xs.push(a[0]); ys.push(a[1])
      if (c !== a) { xs.push(c[0]); ys.push(c[1]) }
    }
  }
  return [xs, ys]
}

function useThemeKey() {
  const [k, setK] = useState(document.documentElement.dataset.theme)
  useEffect(() => {
    const mo = new MutationObserver(() => setK(document.documentElement.dataset.theme))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return k
}

export interface Band { from: number; to: number; label: string }
export interface Marker { ts: number; label: string; kind: 'journal' | 'lab' }

/** Tidslinje med avvikelser som band och journal/provsvar som markeringar på samma tidsaxel. */
export function Timeline({ points, color, unit, from, to, bands, markers, digits = 0, height = 240, gapSec = 600 }: {
  points: [number, number][]; color: string; unit: string; from: number; to: number; bands: Band[]; markers: Marker[]; digits?: number; height?: number; gapSec?: number
}) {
  const host = useRef<HTMLDivElement>(null)
  const plot = useRef<uPlot | null>(null)
  const theme = useThemeKey()
  const [hover, setHover] = useState<{ x: number; t: number; v: number | null } | null>(null)

  useLayoutEffect(() => {
    const el = host.current
    if (!el) return
    const width = el.clientWidth || 600
    const [xs0, ys0] = downsample(points, Math.max(200, Math.floor(width)))
    // bryt linjen vid luckor i mätningen i stället för att dra raka streck över dem
    const xs: number[] = [], ys: (number | null)[] = []
    for (let i = 0; i < xs0.length; i++) {
      if (i > 0 && xs0[i] - xs0[i - 1] > gapSec) { xs.push((xs0[i] + xs0[i - 1]) / 2); ys.push(null) }
      xs.push(xs0[i]); ys.push(ys0[i])
    }
    const col = cssVar(color.replace(/^var\((.*)\)$/, '$1')) || color
    const grid = cssVar('--line'), text = cssVar('--text-3'), danger = cssVar('--danger'), spo2 = cssVar('--spo2'), resp = cssVar('--resp')
    const font = `11px ${cssVar('--mono').split(',')[0]}`
    const span = to - from
    const opts: uPlot.Options = {
      width, height,
      padding: [12, 24, 0, 0],
      legend: { show: false },
      cursor: { y: false, points: { size: 6, fill: col, stroke: col }, drag: { x: false, y: false } },
      scales: { x: { time: true, min: from, max: to }, y: { range: (_u, lo, hi) => { const p = Math.max(1, (hi - lo) * 0.12); return [Math.floor(lo - p), Math.ceil(hi + p)] } } },
      axes: [
        {
          stroke: text, font, grid: { stroke: grid, width: 1 }, ticks: { stroke: grid, width: 1, size: 4 }, gap: 6,
          values: (_u, vals) => vals.map((v) => span > 2 * 86400 ? `${dayMonth(v)}` : hm(v)),
        },
        { stroke: text, font, grid: { stroke: grid, width: 1 }, ticks: { show: false }, size: 42, gap: 6, values: (_u, vals) => vals.map((v) => v.toFixed(digits)) },
      ],
      series: [{}, { stroke: col, width: 1.25, points: { show: false }, spanGaps: false }],
      hooks: {
        drawClear: [(u) => {
          const c = u.ctx
          c.save()
          for (const b of bands) {
            const x0 = u.valToPos(Math.max(b.from, from), 'x', true), x1 = u.valToPos(Math.min(b.to, to), 'x', true)
            const w = Math.max(2 * devicePixelRatio, x1 - x0)
            c.fillStyle = danger + '22'
            c.fillRect(x0, u.bbox.top, w, u.bbox.height)
            c.fillStyle = danger
            c.fillRect(x0, u.bbox.top, w, 2 * devicePixelRatio)
          }
          c.restore()
        }],
        draw: [(u) => {
          const c = u.ctx
          c.save()
          for (const m of markers) {
            if (m.ts < from || m.ts > to) continue
            const x = Math.round(u.valToPos(m.ts, 'x', true))
            c.strokeStyle = m.kind === 'journal' ? spo2 : resp
            c.setLineDash([3 * devicePixelRatio, 3 * devicePixelRatio])
            c.lineWidth = devicePixelRatio
            c.beginPath(); c.moveTo(x + 0.5, u.bbox.top); c.lineTo(x + 0.5, u.bbox.top + u.bbox.height); c.stroke()
            c.setLineDash([])
            c.fillStyle = m.kind === 'journal' ? spo2 : resp
            c.fillRect(x - 3 * devicePixelRatio, u.bbox.top, 6 * devicePixelRatio, 6 * devicePixelRatio)
          }
          c.restore()
        }],
        setCursor: [(u) => {
          const i = u.cursor.idx
          if (i == null || u.cursor.left == null || u.cursor.left < 0) { setHover(null); return }
          setHover({ x: u.cursor.left, t: u.data[0][i], v: u.data[1][i] as number | null })
        }],
      },
    }
    plot.current?.destroy()
    plot.current = new uPlot(opts, [xs, ys], el)
    const ro = new ResizeObserver(() => { if (plot.current && el.clientWidth && Math.abs(el.clientWidth - plot.current.width) > 2) plot.current.setSize({ width: el.clientWidth, height }) })
    ro.observe(el)
    return () => { ro.disconnect(); plot.current?.destroy(); plot.current = null }
  }, [points, color, from, to, bands, markers, theme, height])

  return (
    <div class="timeline">
      <div ref={host} />
      {hover && hover.v != null && (
        <div class="tl-hover num" style={{ left: `${hover.x + 42}px` }}>
          <span class="faint">{span(hover.t, to - from)}</span> <b>{hover.v.toFixed(digits)}</b> <span class="faint">{unit}</span>
        </div>
      )}
    </div>
  )
}

function span(t: number, range: number) {
  return range > 86400 ? `${dayMonth(t)} ${hm(t)}` : hm(t)
}

/** Liten kurva utan axlar, för mätartavlorna. */
/** Liten kurva. Med band ritas hinkarnas min-max som en ljus yta bakom medianen. */
export function Spark({ points, color, height = 28, band }: { points: [number, number][]; color: string; height?: number; band?: [number, number, number][] | null }) {
  if (points.length < 2) return <svg class="spark" height={height} />
  const W = 120
  const [xs, ys] = downsample(points, 60)
  const t0 = xs[0], t1 = xs[xs.length - 1] || t0 + 1
  const bd = (band ?? []).filter((b) => b[0] >= t0 && b[0] <= t1)
  let lo = Math.min(...ys, ...bd.map((b) => b[1])), hi = Math.max(...ys, ...bd.map((b) => b[2]))
  if (hi - lo < 1e-6) { hi += 1; lo -= 1 }
  const X = (x: number) => (((x - t0) / (t1 - t0)) * W).toFixed(1)
  const Y = (v: number) => (height - 2 - ((v - lo) / (hi - lo)) * (height - 4)).toFixed(1)
  const d = xs.map((x, i) => `${i ? 'L' : 'M'}${X(x)},${Y(ys[i])}`).join('')
  const area = bd.length > 1 ? `M${bd.map((b) => `${X(b[0])},${Y(b[2])}`).join('L')}L${[...bd].reverse().map((b) => `${X(b[0])},${Y(b[1])}`).join('L')}Z` : ''
  return (
    <svg class="spark" viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" height={height}>
      {area && <path d={area} fill={color} opacity="0.18" stroke="none" />}
      <path d={d} fill="none" stroke={color} stroke-width="1.25" vector-effect="non-scaling-stroke" />
    </svg>
  )
}

// ------------------------------------------------------------ sömn

const STAGES: { key: string; label: string; color: string }[] = [
  { key: 'awake', label: 'Vaken', color: 'var(--hrv)' },
  { key: 'rem', label: 'REM', color: 'var(--spo2)' },
  { key: 'light', label: 'Lätt', color: '#6f8fd8' },
  { key: 'deep', label: 'Djup', color: '#3d5aa8' },
]

export function normStage(s: string) {
  const k = s.toLowerCase()
  if (/wake|awake|vaken/.test(k)) return 'awake'
  if (/rem/.test(k)) return 'rem'
  if (/deep|djup/.test(k)) return 'deep'
  return 'light'
}

export function Hypnogram({ stages, start, end }: { stages: { start: number; end: number; stage: string }[]; start: number; end: number }) {
  const W = 600, rowH = 22, H = rowH * 4 + 18
  const x = (t: number) => ((t - start) / (end - start)) * W
  const row = (k: string) => STAGES.findIndex((s) => s.key === k)
  const ticks: number[] = []
  const first = new Date(start * 1000); first.setMinutes(0, 0, 0)
  for (let t = first.getTime() / 1000 + 3600; t < end; t += 3600) ticks.push(t)
  const sorted = [...stages].sort((a, b) => a.start - b.start)
  return (
    <svg class="hypno" viewBox={`0 0 ${W + 44} ${H}`} role="img" aria-label="Sömnfaser under natten">
      {STAGES.map((s, i) => (
        <g>
          <text x="0" y={i * rowH + rowH / 2 + 4} class="hy-l">{s.label}</text>
          <line x1="44" x2={W + 44} y1={i * rowH + rowH} y2={i * rowH + rowH} class="hy-grid" />
        </g>
      ))}
      {ticks.map((t) => (
        <g>
          <line x1={44 + x(t)} x2={44 + x(t)} y1="0" y2={rowH * 4} class="hy-grid" />
          <text x={44 + x(t)} y={H - 2} class="hy-t" text-anchor="middle">{hm(t)}</text>
        </g>
      ))}
      {sorted.map((s, i) => {
        const k = normStage(s.stage)
        const r = row(k)
        const prev = sorted[i - 1]
        const pr = prev ? row(normStage(prev.stage)) : r
        const x0 = 44 + x(s.start), x1 = 44 + x(s.end)
        return (
          <g>
            {prev && <line x1={x0} x2={x0} y1={Math.min(pr, r) * rowH + rowH / 2} y2={Math.max(pr, r) * rowH + rowH / 2} class="hy-step" />}
            <rect x={x0} y={r * rowH + 4} width={Math.max(1, x1 - x0)} height={rowH - 8} fill={STAGES[r].color} />
          </g>
        )
      })}
    </svg>
  )
}

export { STAGES }
