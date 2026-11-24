import { useEffect, useState } from 'preact/hooks'
import { api, live } from '../api'
import { fmtNum } from '../format'
import { useAsync } from '../store'

// Svar från GET /api/system (server/src/konsiliet/api.py).
interface Usage { calls: number; prompt_tokens: number; output_tokens: number; seconds: number }
interface SystemInfo {
  modeller_laddade?: { namn: string; storlek_gb: number; vram_gb: number }[]
  modeller_konfig?: { orkestrerare?: string; specialist?: string }
  tokens_sedan_start?: Usage & { per_model?: Record<string, Usage> }
  minne?: { total_gb?: number; anvant_gb?: number; fritt_procent?: number | null; fel?: string }
  handelser_per_minut?: number
  matvarden?: { metric: string; n: number; first: number; last: number }[]
  // önskat, se docs/API-ONSKEMAL.md
  pipeline?: { step: string; p50_ms: number; p95_ms: number; n?: number }[]
}

function useRtt() {
  const [rtt, setRtt] = useState<number[]>([])
  useEffect(() => {
    let alive = true
    const ping = async () => {
      const t = performance.now()
      try { await api.health(); if (alive) setRtt((r) => [...r.slice(-29), performance.now() - t]) } catch { /* ingen server */ }
    }
    ping()
    const i = setInterval(ping, 5000)
    return () => { alive = false; clearInterval(i) }
  }, [])
  return rtt
}

export function Systemet() {
  const [n, setN] = useState(0)
  useEffect(() => { const i = setInterval(() => setN((x) => x + 1), 5000); return () => clearInterval(i) }, [])
  const sys = useAsync(() => api.system() as Promise<SystemInfo>, [n])
  const metrics = useAsync(() => api.metrics(), [Math.floor(n / 6)])
  const rtt = useRtt()
  const missing = sys.error && /404/.test(sys.error)
  const s: SystemInfo = sys.data ?? {}
  const rttMed = rtt.length ? [...rtt].sort((a, b) => a - b)[Math.floor(rtt.length / 2)] : null
  const mem = s.minne && s.minne.total_gb ? s.minne : null
  const use = s.tokens_sedan_start
  const loaded = new Map((s.modeller_laddade ?? []).map((m) => [m.namn, m]))
  const names = [...new Set([s.modeller_konfig?.orkestrerare, s.modeller_konfig?.specialist, ...loaded.keys(), ...Object.keys(use?.per_model ?? {})].filter(Boolean) as string[])]
  const role = (n: string) => n === s.modeller_konfig?.orkestrerare ? 'Orkestrerare' : n === s.modeller_konfig?.specialist ? 'Specialist' : ''

  return (
    <div class="systemet">
      <div class="pagehead">
        <h1>Systemet</h1>
        <p>Allt körs lokalt på en Mac mini M4 med 16 GB. Här syns vad det kostar.</p>
      </div>
      {missing && (
        <div class="demo-banner" role="note">
          <strong>Servern saknar /api/system.</strong>
          <span>Svarstid och händelser mäts ändå från klienten.</span>
        </div>
      )}
      <div class="sys-grid">
        <Stat label="Unified memory" value={mem ? `${fmtNum(mem.anvant_gb, 1)} / ${fmtNum(mem.total_gb, 0)}` : '-'} unit="GB" sub={mem?.fritt_procent != null ? `${mem.fritt_procent} % fritt enligt memory_pressure` : 'använt av totalt'} bar={mem ? (mem.anvant_gb ?? 0) / (mem.total_gb ?? 1) : null} />
        <Stat label="Tokens sedan start" value={use ? (use.prompt_tokens + use.output_tokens).toLocaleString('sv-SE') : '-'} unit="" sub={use ? `${use.prompt_tokens.toLocaleString('sv-SE')} in, ${use.output_tokens.toLocaleString('sv-SE')} ut, ${use.calls} anrop` : 'in och ut'} />
        <Stat label="Händelser" value={String(s.handelser_per_minut ?? live.eventsPerMinute())} unit="/min" sub="sparade händelser senaste minuten" />
        <Stat label="API-svarstid" value={rttMed != null ? fmtNum(rttMed, 1) : '-'} unit="ms" sub="median, mätt från den här klienten" />
      </div>

      <div class="grid two">
        <section class="panel">
          <header><h2>Modeller</h2><span class="meta">Ollama, sedan serverstart</span></header>
          <div class="body">
            <table class="data">
              <thead><tr><th>Modell</th><th>Roll</th><th class="r">I minnet</th><th class="r">Anrop</th><th class="r">Tokens ut</th><th class="r">Tokens/s</th></tr></thead>
              <tbody>
                {(names.length ? names : ['qwen3.5:9b', 'medgemma:4b']).map((n) => {
                  const l = loaded.get(n)
                  const u = use?.per_model?.[n]
                  return (
                    <tr>
                      <td class="mono">{n}</td>
                      <td class="faint">{role(n) || '-'}</td>
                      <td class="r num">{l ? `${fmtNum(l.vram_gb || l.storlek_gb, 1)} GB` : <span class="faint">nej</span>}</td>
                      <td class="r num">{u ? u.calls : '-'}</td>
                      <td class="r num">{u ? u.output_tokens.toLocaleString('sv-SE') : '-'}</td>
                      <td class="r num">{u && u.seconds > 0 ? fmtNum(u.output_tokens / u.seconds, 1) : '-'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p class="faint small">Tokens/s är ut-tokens delat med total anropstid, alltså inklusive promptbearbetning. Ren genereringshastighet finns i bench/.</p>
          </div>
        </section>
        <section class="panel">
          <header><h2>Pipeline</h2><span class="meta">Latens per steg</span></header>
          <div class="body">
            {s.pipeline?.length ? (
              <table class="data">
                <thead><tr><th>Steg</th><th class="r">p50</th><th class="r">p95</th><th class="r">Antal</th><th style="width:34%"></th></tr></thead>
                <tbody>
                  {s.pipeline.map((p) => {
                    const max = Math.max(...s.pipeline!.map((x) => x.p95_ms))
                    return (
                      <tr>
                        <td>{p.step}</td>
                        <td class="r num">{ms(p.p50_ms)}</td>
                        <td class="r num">{ms(p.p95_ms)}</td>
                        <td class="r num faint">{p.n ?? '-'}</td>
                        <td><div class="lat"><i style={{ width: `${(p.p50_ms / max) * 100}%` }} /><b style={{ left: `${(p.p95_ms / max) * 100}%` }} /></div></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            ) : (
              <>
                <table class="data">
                  <thead><tr><th>Steg</th><th class="r">p50</th><th class="r">p95</th></tr></thead>
                  <tbody>{['Mottagning (ingest)', 'Vakt, regelkoll', 'Specialist, per verktygsrunda', 'Granskning', 'Hela konsiliet'].map((x) => <tr><td>{x}</td><td class="r faint">-</td><td class="r faint">-</td></tr>)}</tbody>
                </table>
                <p class="faint small">Servern mäter inte latens per steg än. Önskemålet finns i docs/API-ONSKEMAL.md.</p>
              </>
            )}
          </div>
        </section>
      </div>

      <section class="panel">
        <header><h2>Databas</h2><span class="meta">SQLite, WAL</span></header>
        <div class="body">
          {metrics.error ? <div class="empty">Ingen kontakt med servern.</div> : !metrics.data?.length ? <div class="empty">Inga mätvärden än.</div> : (
            <table class="data">
              <thead><tr><th>Mätvärde</th><th class="r">Punkter</th><th>Första</th><th>Senaste</th></tr></thead>
              <tbody>
                {metrics.data.map((m) => (
                  <tr><td class="mono">{m.metric}</td><td class="r num">{m.n.toLocaleString('sv-SE')}</td><td class="num faint">{new Date(m.first * 1000).toLocaleString('sv-SE')}</td><td class="num">{new Date(m.last * 1000).toLocaleString('sv-SE')}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
      {sys.error && !missing && <p class="faint small">/api/system: {sys.error}</p>}
    </div>
  )
}

function ms(v: number) { return v >= 1000 ? `${fmtNum(v / 1000, 1)} s` : `${fmtNum(v, 0)} ms` }

function Stat({ label, value, unit, sub, bar }: { label: string; value: string; unit: string; sub: string; bar?: number | null }) {
  return (
    <div class="panel stat">
      <div class="faint">{label}</div>
      <div class="num stat-v"><b>{value}</b><span>{unit}</span></div>
      {bar != null && <div class="meter"><i style={{ width: `${Math.min(100, bar * 100)}%` }} /></div>}
      <div class="faint small">{sub}</div>
    </div>
  )
}
