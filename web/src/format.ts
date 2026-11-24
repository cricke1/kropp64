// Formattering av tider, mätvärden och källhänvisningar.

export const METRICS: Record<string, { label: string; short: string; unit: string; color: string; digits: number }> = {
  hr: { label: 'Klockfrekvens', short: 'Puls', unit: 'BPM', color: 'var(--hr)', digits: 0 },
  hrv_rmssd: { label: 'Timingmarginal (HRV)', short: 'HRV', unit: 'ms', color: 'var(--hrv)', digits: 0 },
  spo2: { label: 'Syremättnad', short: 'SpO2', unit: '%', color: 'var(--spo2)', digits: 0 },
  resp_rate: { label: 'Andningsfrekvens', short: 'Andn', unit: '/min', color: 'var(--resp)', digits: 1 },
  dator_kod: { label: 'Kod', short: 'Kod', unit: 'min', color: 'var(--spo2)', digits: 0 },
  dator_spel: { label: 'Spel', short: 'Spel', unit: 'min', color: 'var(--hrv)', digits: 0 },
  dator_chatt: { label: 'Chatt', short: 'Chatt', unit: 'min', color: 'var(--resp)', digits: 0 },
  dator_webb: { label: 'Webb', short: 'Webb', unit: 'min', color: 'var(--steps)', digits: 0 },
  steps: { label: 'Steg', short: 'Steg', unit: 'steg', color: 'var(--steps)', digits: 0 },
  skin_temp: { label: 'Hudtemperatur', short: 'Temp', unit: '°C', color: 'var(--temp)', digits: 2 },
}

export function metricMeta(m: string) {
  return METRICS[m] ?? { label: m, short: m, unit: '', color: 'var(--text-2)', digits: 1 }
}

const pad = (n: number) => String(n).padStart(2, '0')

export function hm(ts: number) {
  const d = new Date(ts * 1000)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}
export function hms(ts: number) {
  const d = new Date(ts * 1000)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
export function ymd(ts: number) {
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
export function dateTime(ts: number) {
  const d = new Date(ts * 1000)
  const today = ymd(Date.now() / 1000) === ymd(ts)
  return today ? `i dag ${hm(ts)}` : `${d.getDate()} ${MONTHS[d.getMonth()]} ${hm(ts)}`
}
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']
export function dayMonth(ts: number) {
  const d = new Date(ts * 1000)
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`
}
export function duration(sec: number) {
  if (!isFinite(sec)) return '-'
  if (sec <= 0) return '0 min'
  if (sec < 60) return `${fmtNum(sec, sec < 10 ? 1 : 0)} s`
  const m = Math.floor(sec / 60), s = Math.round(sec % 60)
  if (m < 60) return s && m < 10 ? `${m} min ${s} s` : `${Math.round(sec / 60)} min`
  return m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${Math.floor(m / 60)} h`
}
export function fmtNum(v: number | null | undefined, digits = 0) {
  if (v == null || !isFinite(v)) return '-'
  return v.toLocaleString('sv-SE', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

// ------------------------------------------------------------------ källor

export type CiteKind = 'series' | 'journal' | 'lab' | 'sleep' | 'source'
export interface Cite { kind: CiteKind; label: string; title: string }

function toTs(v: any): number | null {
  if (typeof v === 'number') return v > 1e12 ? v / 1000 : v
  if (typeof v === 'string') {
    const t = Date.parse(v)
    return isNaN(t) ? null : t / 1000
  }
  return null
}

/** Gör om en källhänvisning (sträng eller objekt i okänt men rimligt format) till en chip. */
// Uppslag för serverns korta referenser (J:id, L:id, N:id). Fylls när journalen och sömnen hämtats.
export const refLookup = {
  journal: new Map<string, { date: string; title?: string; unit?: string }>(),
  labs: new Map<string, { date: string; analyte: string; value_raw?: string; unit?: string }>(),
  sleep: new Map<string, { start: number; end: number }>(),
}

export function cite(c: any): Cite {
  if (c == null) return { kind: 'source', label: '?', title: '' }
  if (typeof c === 'string') {
    const s = c.trim()
    // Serverns format: S:metric:start-end, N:sömnid, J:journalid, L:labbid
    let m = s.match(/^S:([\w-]+):(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$/)
    if (m) return cite({ kind: 'series', metric: m[1], start: Number(m[2]), end: Number(m[3]) })
    m = s.match(/^([JLNB]):(.+)$/)
    if (m) {
      const id = m[2]
      if (m[1] === 'J') {
        const j = refLookup.journal.get(id)
        return { kind: 'journal', label: j ? `Journal ${j.date}` : 'Journal', title: j ? [j.date, j.unit, j.title].filter(Boolean).join(', ') : s }
      }
      if (m[1] === 'L') {
        const l = refLookup.labs.get(id)
        return { kind: 'lab', label: l ? `${l.analyte} ${l.date}` : 'Provsvar', title: l ? `${l.analyte} ${l.date}: ${l.value_raw ?? ''} ${l.unit ?? ''}` : s }
      }
      if (m[1] === 'N') {
        const n = refLookup.sleep.get(id)
        return { kind: 'sleep', label: n ? `Sömn ${dayMonth(n.start)}` : 'Sömnpass', title: n ? `Sömnpass ${dateTime(n.start)} till ${dateTime(n.end)}` : s }
      }
      return { kind: 'series', label: 'Baslinje', title: s }
    }
    const kind: CiteKind = /^journal|^1177/i.test(s) ? 'journal' : /^(lab|prov)/i.test(s) ? 'lab'
      : /^(sömn|somn|sleep)/i.test(s) ? 'sleep' : /^(hr|puls|hrv|spo2|andn|resp|steg|temp)/i.test(s) ? 'series' : 'source'
    return { kind, label: s, title: s }
  }
  if (c.label && typeof c.label === 'string') {
    const k = String(c.kind ?? c.type ?? 'source')
    return { kind: normKind(k), label: c.label, title: c.title ?? c.detail ?? c.label }
  }
  const k = normKind(String(c.kind ?? c.type ?? (c.metric ? 'series' : c.analyte ? 'lab' : c.date ? 'journal' : 'source')))
  if (k === 'series') {
    const m = String(c.metric ?? '')
    const meta = metricMeta(m)
    const a = toTs(c.start ?? c.from ?? c.t0 ?? (Array.isArray(c.window) ? c.window[0] : null))
    const b = toTs(c.end ?? c.to ?? c.t1 ?? (Array.isArray(c.window) ? c.window[1] : null))
    let span = ''
    if (a != null && b != null) span = ymd(a) === ymd(Date.now() / 1000) || ymd(a) === ymd(b) && b - a < 86400 ? `${hm(a)}-${hm(b)}` : `${dayMonth(a)}-${dayMonth(b)}`
    else if (a != null) span = hm(a)
    return { kind: 'series', label: `${meta.short} ${span}`.trim(), title: `${meta.label} ${a != null ? dateTime(a) : ''}${b != null ? ' till ' + dateTime(b) : ''}` }
  }
  if (k === 'lab') {
    const label = `${c.analyte ?? 'Prov'} ${c.date ?? ''}`.trim()
    return { kind: 'lab', label, title: `${label}${c.value_raw ? ': ' + c.value_raw + ' ' + (c.unit ?? '') : ''}` }
  }
  if (k === 'journal') {
    const label = `Journal ${c.date ?? ''}`.trim()
    return { kind: 'journal', label, title: [c.date, c.unit, c.title].filter(Boolean).join(', ') || label }
  }
  if (k === 'sleep') {
    const a = toTs(c.start ?? c.date)
    const label = `Sömn ${a != null ? dayMonth(a) : c.id ?? ''}`.trim()
    return { kind: 'sleep', label, title: label }
  }
  const label = String(c.title ?? c.name ?? c.ref ?? c.url ?? c.id ?? 'Källa')
  return { kind: 'source', label: label.length > 34 ? label.slice(0, Math.max(10, label.lastIndexOf(' ', 32))).trimEnd() + '…' : label, title: String(c.url ?? c.title ?? label) }
}

function normKind(k: string): CiteKind {
  k = k.toLowerCase()
  if (/series|sample|metric|hr|puls|data/.test(k)) return 'series'
  if (/journal|1177|note|anteck/.test(k)) return 'journal'
  if (/lab|prov|analys/.test(k)) return 'lab'
  if (/sleep|sömn|somn/.test(k)) return 'sleep'
  return 'source'
}

export function cites(list: any): Cite[] {
  if (!list) return []
  if (!Array.isArray(list)) list = [list]
  return list.map(cite)
}

/** Text ur en slutbedömning i okänt format. */
export function verdictParts(v: any): { summary: string; level?: string; points: string[]; questions: string[] } {
  if (v == null) return { summary: '', points: [], questions: [] }
  if (typeof v === 'string') return { summary: v, points: [], questions: [] }
  const summary = String(v.sammanfattning ?? v.summary ?? v.text ?? v.bedomning ?? v.bedömning ?? '')
  const list = (x: any) => (Array.isArray(x) ? x.map((y) => (typeof y === 'string' ? y : y.text ?? y.claim ?? JSON.stringify(y))) : [])
  return {
    summary,
    level: v.bradska ?? v.level ?? v.niva ?? v.urgency,
    points: list(v.rad ?? v.points ?? v.findings ?? v.fynd),
    questions: list(v.fragor_till_varden ?? v.questions ?? v.fragor ?? v.frågor),
  }
}

export const LEVELS: Record<string, { label: string; cls: string }> = {
  akut: { label: 'Akut', cls: 'danger' },
  kontakta_vard_nu: { label: 'Kontakta vården nu', cls: 'danger' },
  ta_upp_med_varden: { label: 'Ta upp med vården', cls: 'warn' },
  kontakta: { label: 'Kontakta vården', cls: 'warn' },
  bevaka: { label: 'Bevaka', cls: 'warn' },
  ingen: { label: 'Ingen åtgärd', cls: '' },
  info: { label: 'Information', cls: '' },
}

/** Hårt mellanslag mellan tal och enhet (och mellan tal i följd), så att "7 h 10 min" aldrig bryts mitt i. */
export function bindUnits(s: string): string {
  return s.replace(/(\d) (?=(h|min|s|ms|%|d|dygn|nätter|natt|slag|steg|kcal|°C|\d)\b)/g, '$1\u00a0')
    .replace(/\b(h|min) (?=\d)/g, '$1\u00a0')
}
