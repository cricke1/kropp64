// Sensorpanelen: en tät tabell i stil med en hårdvarumonitor. Aktuellt, min, max och medel per sensor,
// grupperat som hårdvara. Bara uppmätta värden; saknas data står det ett streck.

import { api } from '../api'
import { fmtNum, ymd } from '../format'
import { useAsync } from '../store'

type Rad = { sensor: string; enhet: string; nu: number | null; min: number | null; max: number | null; medel: number | null; digits: number; not?: string }
type Grupp = { namn: string; rader: Rad[] }

function stats(vals: number[]) {
  if (!vals.length) return { min: null, max: null, medel: null }
  return { min: Math.min(...vals), max: Math.max(...vals), medel: vals.reduce((a, b) => a + b, 0) / vals.length }
}

/** 24 h med en punkt per minut: median som kurva, hinkarnas min och max som spann. */
async function sensor(metric: string, sensorNamn: string, enhet: string, digits: number): Promise<Rad> {
  try {
    const r = await api.series(metric, 24, 60)
    const v = r.points.map((p) => p[1])
    const lo = r.band ? r.band.map((b) => b[1]) : v
    const hi = r.band ? r.band.map((b) => b[2]) : v
    return { sensor: sensorNamn, enhet, digits, nu: v.length ? v[v.length - 1] : null,
      min: lo.length ? Math.min(...lo) : null, max: hi.length ? Math.max(...hi) : null, medel: stats(v).medel }
  } catch {
    return { sensor: sensorNamn, enhet, digits, nu: null, min: null, max: null, medel: null }
  }
}

/** Idle-klock: lägsta 10-minutersmedian per natt (00-06), senaste 14 nätterna. Aktuellt = senaste natten. */
async function idleKlock(): Promise<Rad> {
  const base: Rad = { sensor: 'Idle-klock (vilopuls)', enhet: 'BPM', digits: 0, nu: null, min: null, max: null, medel: null, not: 'per natt, 14 nätter' }
  try {
    const r = await api.series('hr', 14 * 24, 600)
    const per = new Map<string, number>()
    for (const [ts, v] of r.points) {
      if (new Date(ts * 1000).getHours() >= 6) continue
      const k = ymd(ts)
      per.set(k, Math.min(per.get(k) ?? Infinity, v))
    }
    const natter = [...per.entries()].sort().map(([, v]) => v)
    if (!natter.length) return base
    return { ...base, nu: natter[natter.length - 1], ...stats(natter) }
  } catch { return base }
}

/** Steg och stresstest per dygn, senaste 7 dygnen. Aktuellt = i dag. */
async function last(): Promise<Rad[]> {
  const dagar: string[] = []
  for (let i = 6; i >= 0; i--) dagar.push(ymd(Date.now() / 1000 - i * 86400))
  const steg = new Map<string, number>(), puls = new Map<string, number>()
  try {
    const s = await api.series('steps', 7 * 24)
    for (const [ts, v] of s.points) steg.set(ymd(ts), (steg.get(ymd(ts)) ?? 0) + v)
  } catch { /* ingen data */ }
  try {
    const h = await api.series('hr', 7 * 24, 60)
    for (const [ts, v] of h.points) if (v >= 100) puls.set(ymd(ts), (puls.get(ymd(ts)) ?? 0) + 1)
  } catch { /* ingen data */ }
  const rad = (namn: string, enhet: string, m: Map<string, number>, not: string): Rad => {
    if (!m.size) return { sensor: namn, enhet, digits: 0, nu: null, min: null, max: null, medel: null, not }
    const per = dagar.map((d) => m.get(d) ?? 0)
    return { sensor: namn, enhet, digits: 0, nu: per[per.length - 1], ...stats(per), not }
  }
  return [rad('Steg', 'steg', steg, 'per dygn, 7 dygn'), rad('Stresstest (puls 100+)', 'min', puls, 'per dygn, 7 dygn')]
}

async function uptime(): Promise<Rad> {
  try {
    const d = await api.datorn(24)
    const tot = Object.values(d.kategorier).reduce((a, k) => a + k.minuter, 0)
    return { sensor: 'Uptime vid datorn', enhet: 'min', digits: 0, nu: tot, min: null, max: null, medel: null, not: 'senaste 24 h' }
  } catch {
    return { sensor: 'Uptime vid datorn', enhet: 'min', digits: 0, nu: null, min: null, max: null, medel: null }
  }
}

async function headroom(): Promise<Rad> {
  try {
    const a = await api.aterhamtning()
    return { sensor: 'Headroom', enhet: 'av 100', digits: 0, nu: a?.poang ?? null, min: null, max: null, medel: null, not: 'beräknas en gång per dygn' }
  } catch {
    return { sensor: 'Headroom', enhet: 'av 100', digits: 0, nu: null, min: null, max: null, medel: null }
  }
}

export function Sensorpanel() {
  const q = useAsync(async (): Promise<Grupp[]> => {
    const [hr, idle, hrv, resp, spo2, temp, hd, lastRader, up] = await Promise.all([
      sensor('hr', 'Klockfrekvens', 'BPM', 0), idleKlock(), sensor('hrv_rmssd', 'Timingmarginal (HRV)', 'ms', 0),
      sensor('resp_rate', 'Andningsfrekvens', '/min', 1), sensor('spo2', 'SpO2', '%', 0),
      sensor('skin_temp', 'Hudtemperatur', '°C', 2), headroom(), last(), uptime(),
    ])
    return [
      { namn: 'Hjärta (Pixel Watch)', rader: [hr, idle, hrv] },
      { namn: 'Andning', rader: [resp, spo2] },
      { namn: 'Kylning', rader: [temp, hd] },
      { namn: 'Last', rader: [...lastRader, up] },
    ]
  }, [])
  const v = (x: number | null, r: Rad) => x == null ? <span class="faint">-</span> : <>{fmtNum(x, r.digits)}<span class="u">{r.enhet}</span></>
  return (
    <section class="panel sensorpanel">
      <header><h2>Sensorer</h2><span class="meta">Senaste 24 h om inget annat står</span></header>
      {q.error ? <div class="body"><div class="empty">Kunde inte hämta sensorerna ({q.error}).</div></div> : (
        <table class="data sensors">
          <thead><tr><th>Sensor</th><th class="r">Aktuellt</th><th class="r">Min</th><th class="r">Max</th><th class="r">Medel</th><th class="not" /></tr></thead>
          {(q.data ?? []).map((g) => (
            <tbody>
              <tr class="grupp"><td colSpan={6}>{g.namn}</td></tr>
              {g.rader.map((r) => (
                <tr>
                  <td class="sn">{r.sensor}</td>
                  <td class="r num">{v(r.nu, r)}</td>
                  <td class="r num">{v(r.min, r)}</td>
                  <td class="r num">{v(r.max, r)}</td>
                  <td class="r num">{v(r.medel, r)}</td>
                  <td class="not faint">{r.not ?? ''}</td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      )}
    </section>
  )
}
