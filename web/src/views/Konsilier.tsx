import { useMemo } from 'preact/hooks'
import { api } from '../api'
import { cites as toCites, dateTime, duration, fmtNum, LEVELS, verdictParts } from '../format'
import { entriesFromEvents } from '../office/director'
import { go, useAsync } from '../store'
import { consultEvents, Transcript, triggerText } from './Kontoret'

function levelTag(v: any) {
  const p = verdictParts(v)
  const l = p.level ? LEVELS[String(p.level).toLowerCase()] : null
  return l ? <span class={`tag ${l.cls}`}>{l.label}</span> : null
}

export function Konsilier({ id }: { id: string | null }) {
  return id ? <Detail id={id} /> : <List />
}

function List() {
  const q = useAsync(() => api.consults(), [])
  const rows = q.data ?? []
  return (
    <div>
      <div class="pagehead">
        <h1>Konsilier</h1>
        <p>Varje gång vakten eller du kallar in läkarteamet sparas hela samtalet här.</p>
      </div>
      <section class="panel">
        {q.error ? <div class="empty">Kunde inte hämta konsilier ({q.error}).</div>
          : !rows.length ? (
            <div class="empty">
              {q.loading ? 'Hämtar.' : <>Inga konsilier än. <a href="#/kontoret?demo=1">Se demon i kontoret</a> eller <a href="#/fraga">ställ en fråga</a>.</>}
            </div>
          ) : (
            <table class="data clickable">
              <thead><tr><th>Start</th><th>Anledning</th><th>Bedömning</th><th class="r">Tid</th><th class="r">Tokens</th></tr></thead>
              <tbody>
                {rows.map((c) => {
                  const t = triggerText(c.trigger)
                  const v = verdictParts(c.verdict)
                  const sec = c.ended ? c.ended - c.started : null
                  return (
                    <tr onClick={() => go(`konsilier/${encodeURIComponent(c.id)}`)} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') go(`konsilier/${encodeURIComponent(c.id)}`) }}>
                      <td class="num nowrap">{dateTime(c.started)}</td>
                      <td><div>{t.title}</div>{t.detail && <div class="faint clamp">{t.detail}</div>}</td>
                      <td>{c.verdict ? <div class="vcell">{levelTag(c.verdict)}<span class="clamp">{v.summary}</span></div> : <span class="faint">{c.ended ? 'Ingen bedömning' : 'Pågår'}</span>}</td>
                      <td class="r num">{sec != null ? duration(sec) : '-'}</td>
                      <td class="r num">{fmtNum(tokens(c.stats))}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
      </section>
    </div>
  )
}

function tokens(stats: any): number | null {
  if (!stats) return null
  if (typeof stats.prompt_tokens === 'number') return stats.prompt_tokens + (stats.output_tokens ?? 0)
  for (const k of ['tokens', 'tokens_total', 'total_tokens']) if (typeof stats[k] === 'number') return stats[k]
  return null
}

const STAT_LABELS: Record<string, string> = {
  tokens: 'Tokens', tokens_total: 'Tokens', total_tokens: 'Tokens', tokens_in: 'Tokens in', tokens_out: 'Tokens ut',
  prompt_tokens: 'Tokens in', completion_tokens: 'Tokens ut', seconds: 'Sekunder', duration: 'Sekunder', elapsed: 'Sekunder',
  tokens_per_s: 'Tokens/s', tps: 'Tokens/s', model: 'Modell', models: 'Modeller', calls: 'Modellanrop', llm_calls: 'Modellanrop',
  tool_calls: 'Verktygsanrop', strikes: 'Strykningar', rounds: 'Rundor',
  output_tokens: 'Tokens ut', sekunder_totalt: 'Sekunder totalt', modeller: 'Modeller', per_model: 'Per modell',
}

function Detail({ id }: { id: string }) {
  const q = useAsync(() => consultEvents(id), [id])
  const entries = useMemo(() => (q.data ? entriesFromEvents(q.data.events) : []), [q.data])
  const c = q.data?.consult
  const start = q.data?.events.find((e) => e.kind === 'consult.start')
  const trig = triggerText(c?.trigger ?? start?.payload.trigger)
  const verdictEv = [...(q.data?.events ?? [])].reverse().find((e) => e.kind === 'consult.verdict')
  const verdict = c?.verdict ?? verdictEv?.payload.verdict
  const v = verdictParts(verdict)
  const allCites = useMemo(() => {
    const seen = new Map<string, ReturnType<typeof toCites>[number]>()
    for (const e of entries) for (const ci of toCites(e.cites)) seen.set(ci.label, ci)
    return [...seen.values()]
  }, [entries])
  const strikes = entries.filter((e) => e.kind === 'strike')
  const stats = c?.stats && typeof c.stats === 'object' ? Object.entries(c.stats) : []
  const sec = c?.ended && c?.started ? c.ended - c.started : null

  return (
    <div class="konsil">
      <div class="pagehead">
        <a class="btn small" href="#/konsilier">Alla konsilier</a>
        <h1>{trig.title}</h1>
        <span style="flex:1" />
        <button class="btn primary small" onClick={() => go(`kontoret?replay=${encodeURIComponent(id)}`)}>Spela upp i kontoret</button>
      </div>
      {q.loading && <div class="empty">Hämtar.</div>}
      {q.error && <div class="empty">Kunde inte hämta konsiliet ({q.error}).</div>}
      {q.data && (
        <div class="k-detail">
          <div class="col">
            <section class="panel">
              <header><h2>Anledning</h2><span class="meta num">{c ? dateTime(c.started) : start?.ts ? dateTime(start.ts) : ''}</span></header>
              <div class="body"><p class="lead">{trig.detail || trig.title}</p></div>
            </section>
            <section class="panel">
              <header><h2>Bedömning</h2>{levelTag(verdict)}</header>
              <div class="body">
                {verdict ? (
                  <>
                    {v.summary && <p class="lead">{v.summary}</p>}
                    {v.points.length > 0 && <ul class="plain">{v.points.map((p) => <li>{p}</li>)}</ul>}
                    {v.questions.length > 0 && <><h3 class="sub">Att ta med till vården</h3><ol class="plain">{v.questions.map((x) => <li>{x}</li>)}</ol></>}
                    <p class="faint small">Underlag, inte diagnos. Kontakta vården vid oro.</p>
                  </>
                ) : <div class="empty">Ingen bedömning sparad.</div>}
              </div>
            </section>
            <section class="panel">
              <header><h2>Struket av granskaren</h2><span class="meta num">{strikes.length}</span></header>
              <div class="body">
                {!strikes.length ? <div class="faint">Inget struket.</div> : (
                  <ul class="strikes">{strikes.map((s) => <li><span class="strike-anim">{s.claim}</span><div class="muted">{s.reason}</div></li>)}</ul>
                )}
              </div>
            </section>
            <section class="panel">
              <header><h2>Källor</h2><span class="meta num">{allCites.length}</span></header>
              <div class="body">
                {!allCites.length ? <div class="faint">Inga källhänvisningar.</div> : <div class="cites">{allCites.map((ci) => <span class={`chip k-${ci.kind}`} title={ci.title}><i />{ci.label}</span>)}</div>}
              </div>
            </section>
            <section class="panel">
              <header><h2>Körning</h2></header>
              <div class="body">
                <dl class="stats">
                  <dt>Tid</dt><dd class="num">{sec != null ? duration(sec) : '-'}</dd>
                  <dt>Händelser</dt><dd class="num">{q.data.events.length}</dd>
                  {stats.map(([k, val]) => <><dt>{STAT_LABELS[k] ?? k}</dt><dd class="num">{fmtStat(val)}</dd></>)}
                </dl>
              </div>
            </section>
          </div>
          <section class="panel k-transcript">
            <header><h2>Samtalet</h2><span class="meta num">{entries.filter((e) => e.kind === 'say').length} inlägg</span></header>
            <Transcript entries={entries} />
          </section>
        </div>
      )}
    </div>
  )
}

function fmtStat(v: any): string {
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString('sv-SE') : fmtNum(v, 1)
  if (Array.isArray(v)) return v.map(fmtStat).join(', ')
  if (v && typeof v === 'object') return Object.entries(v).map(([k, x]) => `${k}: ${fmtStat(x)}`).join(', ')
  return String(v)
}
