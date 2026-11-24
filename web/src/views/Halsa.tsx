// Delar av Översikt som bygger på serverns rutiner: återhämtningspoäng, morgonbrief, datortid och 1177-hämtning.

import { useEffect, useMemo, useState } from 'preact/hooks'
import { api } from '../api'
import { duration, fmtNum, hm } from '../format'
import { side, useAsync, useSide } from '../store'

function zText(z: number, digits = 2) {
  const a = Math.abs(z)
  return `${z >= 0 ? '+' : '-'}${fmtNum(a, digits)}`
}

export function RecoveryScore() {
  const q = useAsync(() => api.aterhamtning(), [])
  const d = q.data
  const delar = d?.delar ?? {}
  const p: number | null = d?.poang ?? null
  return (
    <section class="panel score">
      <header><h2>Headroom i dag</h2><span class="meta">Öppen formel, inga dolda vikter</span></header>
      <div class="body">
        {q.error ? <div class="empty">Kunde inte hämta ({q.error}).</div> : p == null ? <div class="empty">{q.loading ? 'Hämtar.' : 'För lite data än. Poängen kräver nattdata och minst en veckas baslinje.'}</div> : (
          <div class="score-grid">
            <div class="score-big">
              <b class="num">{p}</b><span class="faint">av 100</span>
              <div class="meter"><i style={{ width: `${p}%` }} /></div>
            </div>
            <table class="data score-parts">
              <thead><tr><th>Del</th><th class="r">I natt</th><th class="r">Baslinje</th><th class="r">z</th><th class="r">Bidrag</th></tr></thead>
              <tbody>
                <tr><td>Start</td><td /><td /><td /><td class="r num">50</td></tr>
                {delar.hrv && <tr><td>HRV</td><td class="r num">{fmtNum(delar.hrv.natt_ms, 0)} ms</td><td class="r num">{fmtNum(delar.hrv.baslinje_ms, 0)} ms</td><td class="r num">{zText(delar.hrv.z)}</td><td class="r num">{zText(12 * delar.hrv.z, 1)}</td></tr>}
                {delar.vilopuls && <tr><td>Idle-klock (vilopuls)</td><td class="r num">{fmtNum(delar.vilopuls.natt, 0)}</td><td class="r num">{fmtNum(delar.vilopuls.baslinje, 0)}</td><td class="r num">{zText(delar.vilopuls.z)}</td><td class="r num">{zText(-10 * delar.vilopuls.z, 1)}</td></tr>}
                {delar.somn && <tr><td>Viloläge (sömn)</td><td class="r num">{fmtNum(delar.somn.timmar, 1)} h</td><td class="r num">7,5 h</td><td /><td class="r num">{zText(8 * (delar.somn.timmar - 7.5), 1)}</td></tr>}
              </tbody>
            </table>
            <code class="formula">{d.formel ?? '50 + 12*z_hrv - 10*z_vilopuls + 8*(sömntimmar-7.5)'}</code>
          </div>
        )}
      </div>
    </section>
  )
}

export function BriefPanel() {
  const s = useSide()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const b = s.brief?.payload
  async function make() {
    setBusy(true); setErr(null)
    try { const r = await api.brief(); if (!side.brief || side.brief.payload.text !== r.text) { side.brief = { id: null, ts: Date.now() / 1000, kind: 'brief.morgon', payload: r } } }
    catch (e: any) { setErr(String(e?.message ?? e)) } finally { setBusy(false) }
  }
  return (
    <section class="panel brief">
      <header><h2>POST-skärmen</h2><span class="meta">{b ? b.datum : 'Idrottsläkaren, lokal modell'}</span></header>
      <div class="body">
        {b ? <p class="lead">{b.text}</p> : <div class="faint">{__PUBLIK_DEMO__ ? 'Språkmodellen är avstängd i den publika demon. På riktigt skriver idrottsläkaren morgonens POST-rapport utifrån nattens siffror.' : 'Ingen POST-rapport i dag än. Idrottsläkaren skriver den varje morgon utifrån nattens siffror.'}</div>}
        {b?.fakta && (
          <div class="brief-facts">
            {b.fakta.steg_senaste_dygnet != null && <span class="tag">{Number(b.fakta.steg_senaste_dygnet).toLocaleString('sv-SE')} steg</span>}
            {b.fakta.aterhamtning?.poang != null && <span class="tag">återhämtning {b.fakta.aterhamtning.poang}</span>}
            {b.fakta.minuter_vid_datorn && <span class="tag">{Object.values(b.fakta.minuter_vid_datorn as Record<string, number>).reduce((a, x) => a + x, 0)} min vid datorn</span>}
          </div>
        )}
        <div class="row-end">
          {err && <span class="err small">{err}</span>}
          {!__PUBLIK_DEMO__ && <button class="btn small" disabled={busy} onClick={make}>{busy ? 'Skriver' : b ? 'Skriv ny' : 'Skriv nu'}</button>}
        </div>
      </div>
    </section>
  )
}

const KATS: [string, string, string][] = [
  ['kod', 'Kod', 'var(--spo2)'], ['spel', 'Spel', 'var(--hrv)'], ['chatt', 'Chatt', 'var(--resp)'], ['webb', 'Webb', 'var(--steps)'], ['annat', 'Annat', 'var(--text-3)'],
]

export function DatornPanel() {
  const [hours, setHours] = useState(24)
  const q = useAsync(() => api.datorn(hours), [hours])
  const k = q.data?.kategorier
  const total = k ? Object.values(k).reduce((a, x) => a + x.minuter, 0) : 0
  const maxMin = k ? Math.max(1, ...Object.values(k).map((x) => x.minuter)) : 1
  const pulses = k ? Object.values(k).map((x) => x.puls_median).filter((x): x is number => x != null) : []
  const lo = pulses.length ? Math.min(...pulses) - 5 : 50, hi = pulses.length ? Math.max(...pulses) + 5 : 100
  return (
    <section class="panel">
      <header>
        <h2>Uptime vid datorn</h2>
        <div class="seg" role="group" aria-label="Period">
          {[[24, 'Dygn'], [168, 'Vecka']].map(([h, l]) => <button aria-pressed={hours === h} onClick={() => setHours(h as number)}>{l}</button>)}
        </div>
      </header>
      <div class="body">
        <p class="faint small first">Minuter med varje typ av program i förgrunden, och medianpulsen (BPM) under just de minuterna. Bara kategorin sparas, aldrig fönstertitlar.</p>
        {q.error ? <div class="empty">Kunde inte hämta ({q.error}).</div> : !total ? <div class="empty">{q.loading ? 'Hämtar.' : 'Ingen datortid registrerad.'}</div> : (
          <table class="data datorn">
            <thead><tr><th>Kategori</th><th class="r">Tid</th><th style="width:30%" /><th class="r">Klockfrekvens, median</th><th style="width:26%" /></tr></thead>
            <tbody>
              {KATS.map(([key, label, col]) => {
                const x = k![key]
                if (!x) return null
                return (
                  <tr>
                    <td><i class="sw" style={{ background: col }} />{label}</td>
                    <td class="r num">{duration(x.minuter * 60)}</td>
                    <td><div class="hbar"><i style={{ width: `${(x.minuter / maxMin) * 100}%`, background: col }} /></div></td>
                    <td class="r num">{x.puls_median != null ? <b>{fmtNum(x.puls_median, 0)}</b> : <span class="faint">-</span>}</td>
                    <td>{x.puls_median != null && <div class="pscale"><i style={{ left: `${((x.puls_median - lo) / (hi - lo)) * 100}%` }} /></div>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}

/** Band under tidslinjen som visar när datorn användes, per kategori. */
export function DatorStrip({ from, to, nonce }: { from: number; to: number; nonce: number }) {
  const hours = Math.ceil((to - from) / 3600)
  const q = useAsync(async () => {
    const out: Record<string, number[]> = {}
    await Promise.all(KATS.slice(0, 4).map(async ([key]) => {
      try { out[key] = (await api.series(`dator_${key}`, hours)).points.map((p) => p[0]) } catch { out[key] = [] }
    }))
    return out
  }, [hours, nonce])
  const d = q.data
  const any = d && Object.values(d).some((x) => x.length)
  const W = 1000
  const rows = useMemo(() => KATS.slice(0, 4).map(([key, label, col]) => ({ key, label, col, ts: d?.[key] ?? [] })), [d])
  if (!any) return null
  const x = (t: number) => ((t - from) / (to - from)) * W
  return (
    <div class="dstrip">
      {rows.map((r) => (
        <div class="dstrip-row">
          <span class="faint">{r.label}</span>
          <svg viewBox={`0 0 ${W} 8`} preserveAspectRatio="none">
            <rect x="0" y="0" width={W} height="8" class="dstrip-bg" />
            {r.ts.map((t) => <rect x={x(t)} y="0" width={Math.max(1, (60 / (to - from)) * W)} height="8" fill={r.col} />)}
          </svg>
        </div>
      ))}
    </div>
  )
}

// ------------------------------------------------------------ 1177

const SYNC_TEXT: Record<string, string> = {
  startar: 'Startar hämtningen.', loggar_in: 'Väntar på inloggning.', qr: 'Skanna QR-koden med BankID-appen.', bankid_lank: 'Väntar på BankID.',
  inloggad: 'Inloggad. Hämtar journalen.', hamtar: 'Hämtar.', klar: 'Klart. Journalen är uppdaterad.', misslyckades: 'Hämtningen misslyckades.',
}

export function Sync1177() {
  if (__PUBLIK_DEMO__) return null
  const s = useSide()
  const [open, setOpen] = useState(false)
  const [startedAt, setStartedAt] = useState(0)
  const [err, setErr] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now())
  useEffect(() => { if (!open) return; const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [open])
  // senaste status som hör till den här hämtningen
  const ev = s.sync && (s.sync.ts ?? 0) * 1000 >= startedAt - 2000 ? s.sync : null
  const st = String(ev?.payload.status ?? (open && !err ? 'startar' : ''))
  const [qr, setQr] = useState<{ png: string; kvar: number; at: number } | null>(null)
  const [link, setLink] = useState<string | null>(null)
  useEffect(() => {
    if (!ev) return
    if (ev.payload.status === 'qr' && ev.payload.png) setQr({ png: ev.payload.png, kvar: Number(ev.payload.kvar ?? 0), at: Date.now() })
    if (ev.payload.status === 'bankid_lank' && ev.payload.url) setLink(String(ev.payload.url))
    if (['inloggad', 'hamtar', 'klar', 'misslyckades'].includes(ev.payload.status)) setQr(null)
  }, [ev])
  async function start() {
    setOpen(true); setErr(null); setQr(null); setLink(null); setStartedAt(Date.now())
    try { await api.sync1177() } catch (e: any) { setErr(String(e?.message ?? e)) }
  }
  const kvar = qr ? Math.max(0, qr.kvar - Math.floor((now - qr.at) / 1000)) : null
  const done = st === 'klar' || st === 'misslyckades' || !!err
  return (
    <>
      <button class="btn small" onClick={start}>Hämta från 1177</button>
      {open && (
        <div class="modal" role="dialog" aria-modal="true" aria-label="Hämta journal från 1177" onClick={(e) => { if (e.target === e.currentTarget && done) setOpen(false) }}>
          <div class="modal-box panel">
            <header><h2>Hämta journal från 1177</h2><button class="iconbtn" onClick={() => setOpen(false)} aria-label="Stäng">Stäng</button></header>
            <div class="body">
              {err ? <p class="err">Kunde inte starta: {err}</p> : <p>{SYNC_TEXT[st] ?? st}</p>}
              {ev?.payload.detail && <p class="muted small">{String(ev.payload.detail)}</p>}
              {st === 'hamtar' && ev?.payload.av && <div class="meter"><i style={{ width: `${(Number(ev.payload.steg) / Number(ev.payload.av)) * 100}%` }} /></div>}
              {st === 'hamtar' && ev?.payload.kategori && <p class="faint small">{String(ev.payload.kategori)} ({ev.payload.steg} av {ev.payload.av})</p>}
              {qr && (
                <div class="qr">
                  <img src={`data:image/png;base64,${qr.png}`} alt="QR-kod för BankID" width={240} height={240} />
                  <span class="num faint">{kvar} s kvar</span>
                </div>
              )}
              {link && !done && <p><a class="btn" href={link}>Öppna BankID på den här enheten</a></p>}
              {st === 'klar' && ev && <p class="faint small num">{Object.entries(ev.payload).filter(([k, v]) => typeof v === 'number' && k !== 'ts').map(([k, v]) => `${k}: ${v}`).join(', ')}</p>}
              <p class="faint small">Inloggningen sker med ditt BankID direkt mot 1177. Journalen sparas bara på Mac minin. {ev?.ts ? `Senaste status ${hm(ev.ts)}.` : ''}</p>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
