import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'
import { agentInfo } from '../agents'
import { api, type Consult, type Ev } from '../api'
import { cites, dateTime, hms, LEVELS, verdictParts } from '../format'
import { toolLabel, type Entry } from '../office/director'
import { demoEvents } from '../office/demo'
import { director, go, useAsync, useDirector } from '../store'

export function triggerText(t: any): { title: string; detail: string } {
  if (!t) return { title: 'Konsilium', detail: '' }
  if (typeof t === 'string') return { title: t, detail: '' }
  if (t.kind === 'question') return { title: 'Fråga från dig', detail: String(t.question ?? '') }
  return { title: String(t.title ?? t.rule ?? 'Avvikelse'), detail: String(t.detail ?? '') }
}

/** Hämtar alla händelser för ett möte. Händelseloggen har riktiga tider; transkriptet används som reserv. */
export async function consultEvents(id: string): Promise<{ events: Ev[]; consult: Consult | null }> {
  let consult: Consult | null = null
  try { consult = await api.consult(id) } catch { /* finns kanske bara i händelseloggen */ }
  let fromLog: Ev[] = []
  try {
    const all = await api.events(5000)
    fromLog = all.filter((e) => e.payload?.consult_id === id)
  } catch { /* ingen server */ }
  let fromTranscript: Ev[] = []
  const tr = consult?.transcript
  if (Array.isArray(tr)) {
    fromTranscript = tr.map((x: any, i: number): Ev | null => {
      // serverns transkript: {t: sekunder sedan start, kind, ...payload}
      if (x && typeof x.kind === 'string') return { id: null, ts: x.ts ?? (typeof x.t === 'number' ? consult!.started + x.t : null), kind: x.kind, payload: x.payload ?? x }
      if (x && x.agent && (x.text || x.content)) return { id: null, ts: x.ts ?? (consult!.started + i), kind: 'agent.say', payload: { consult_id: id, agent: x.agent, to: x.to, text: x.text ?? x.content, cites: x.cites } }
      return null
    }).filter(Boolean) as Ev[]
  }
  let events = fromLog.length >= fromTranscript.length ? fromLog : fromTranscript
  if (consult && !events.some((e) => e.kind === 'consult.start'))
    events = [{ id: null, ts: consult.started, kind: 'consult.start', payload: { consult_id: id, trigger: consult.trigger, members: [] } }, ...events]
  if (consult?.verdict && !events.some((e) => e.kind === 'consult.verdict'))
    events = [...events, { id: null, ts: consult.ended ?? null, kind: 'consult.verdict', payload: { consult_id: id, verdict: consult.verdict } }]
  return { events, consult }
}

export function Kontoret({ query }: { query: URLSearchParams }) {
  const d = useDirector()
  const host = useRef<HTMLDivElement>(null)
  const [err, setErr] = useState<string | null>(null)
  const consults = useAsync(() => api.consults(), [])
  const demo = query.get('demo') === '1'
  const replayId = query.get('replay')

  useLayoutEffect(() => {
    host.current?.appendChild(director.scene.root)
    return () => { director.scene.root.remove() }
  }, [])

  useEffect(() => {
    setErr(null)
    if (demo) director.replay(demoEvents(), 'demo', Number(query.get('speed') ?? 1) || 1)
    else if (replayId) {
      consultEvents(replayId).then(({ events }) => {
        if (!events.length) { setErr('Hittade inga händelser för det här konsiliet.'); return }
        director.replay(events, 'replay', 1)
      }).catch((e) => setErr(String(e)))
    } else if (director.state.mode !== 'live') director.backToLive()
  }, [demo, replayId, query.get('t')])

  const s = d.state
  const trig = triggerText(s.trigger)
  const list = consults.data ?? []

  return (
    <div class="kontoret">
      <div class="pagehead k-head">
        <h1>Kontoret</h1>
        <div class="k-status">
          {s.mode === 'live' && (s.active
            ? <span><span class="dot on pulse" /> Pågår: <b>{trig.title}</b></span>
            : <span class="muted"><span class="dot" /> Inget pågående konsilium. Vakten bevakar din data.</span>)}
          {s.mode === 'replay' && <span><span class="dot" /> Uppspelning: <b>{trig.title}</b></span>}
          {s.mode === 'demo' && <span><span class="dot demo" /> Demo: <b>{trig.title}</b></span>}
        </div>
        <span style="flex:1" />
        <div class="k-modes">
          <div class="seg" role="group" aria-label="Läge">
            <button aria-pressed={s.mode === 'live'} onClick={() => go('kontoret')}>Live</button>
            <button aria-pressed={s.mode === 'demo'} onClick={() => go(`kontoret?demo=1&t=${Date.now()}`)}>Demo</button>
          </div>
          <select aria-label="Spela upp ett konsilium" value={replayId ?? ''} onChange={(e) => { const v = (e.target as HTMLSelectElement).value; if (v) go(`kontoret?replay=${encodeURIComponent(v)}`) }}>
            <option value="">{list.length ? 'Spela upp konsilium' : 'Inga sparade konsilier'}</option>
            {list.map((c) => <option value={c.id}>{dateTime(c.started)}, {triggerText(c.trigger).title}</option>)}
          </select>
        </div>
      </div>

      {s.mode === 'demo' && (
        <div class="demo-banner" role="note">
          <strong>Demo - syntetisk data.</strong>
          <span>Ett påhittat exempel som visar hur konsiliet arbetar. Inga av siffrorna är uppmätta.</span>
        </div>
      )}
      {err && <div class="demo-banner" role="alert"><strong>Kunde inte spela upp.</strong> <span>{err}</span></div>}

      <div class="k-grid">
        <section class="k-stage">
          <div ref={host} class="k-scene" />
          {s.mode !== 'live' && <ReplayBar />}
          <Legend />
        </section>
        <aside class="panel k-transcript">
          <header><h2>Samtalet</h2><span class="meta">{s.consultId && s.mode !== 'demo' ? <span class="mono">{s.consultId.slice(0, 8)}</span> : null}</span></header>
          <Transcript entries={d.entries} />
        </aside>
      </div>
    </div>
  )
}

function ReplayBar() {
  const d = useDirector()
  const s = d.state
  return (
    <div class="replaybar">
      <button class="btn small" onClick={() => d.togglePlay()} aria-label={s.playing ? 'Pausa' : 'Spela'}>
        {s.playing && !s.finished ? <PauseIcon /> : <PlayIcon />}
        <span>{s.playing && !s.finished ? 'Pausa' : s.finished ? 'Spela igen' : 'Spela'}</span>
      </button>
      <button class="btn small" onClick={() => d.restart()}>Från början</button>
      <input type="range" min={0} max={s.total} value={s.index} aria-label="Position i uppspelningen"
        onInput={(e) => d.seek(Number((e.target as HTMLInputElement).value))} />
      <span class="num faint">{s.index}/{s.total}</span>
      <div class="seg" role="group" aria-label="Hastighet">
        {[0.5, 1, 2, 4].map((v) => <button aria-pressed={s.speed === v} onClick={() => d.setSpeed(v)}>{String(v).replace('.', ',')}x</button>)}
      </div>
    </div>
  )
}

const PlayIcon = () => <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 1l7 4-7 4z" fill="currentColor" /></svg>
const PauseIcon = () => <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 1h2v8H2zM6 1h2v8H6z" fill="currentColor" /></svg>

function Legend() {
  const d = useDirector()
  const ids = [...d.scene.actors.keys()]
  return (
    <ul class="k-legend" aria-label="Läkarteamet">
      {ids.map((id) => {
        const a = agentInfo(id)
        const active = d.scene.members.includes(id)
        return <li class={active || !d.scene.members.length ? '' : 'away'}><i style={{ background: a.color }} /><span>{a.name}</span><span class="faint">{a.role}</span></li>
      })}
    </ul>
  )
}

export function Transcript({ entries, compact }: { entries: Entry[]; compact?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  useLayoutEffect(() => {
    const el = ref.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [entries.length, entries[entries.length - 1]?.struck?.length])
  if (!entries.length) return <div class="tr-list"><div class="empty">Samtalet visas här när konsiliet arbetar.</div></div>
  return (
    <div class={`tr-list ${compact ? 'compact' : ''}`} ref={ref} onScroll={(e) => {
      const el = e.currentTarget as HTMLDivElement
      stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    }}>
      {entries.map((e) => <EntryRow key={e.n} e={e} />)}
    </div>
  )
}

function Who({ id }: { id: string }) {
  const a = agentInfo(id)
  return <span class="who"><i style={{ background: a.color }} /><b>{a.name}</b></span>
}

function struckText(text: string, struck?: { claim: string; reason: string }[]) {
  if (!struck?.length) return text
  const out: (string | preact.JSX.Element)[] = []
  let rest = text
  for (const s of struck) {
    const i = rest.toLowerCase().indexOf(s.claim.toLowerCase())
    if (i < 0) return <span class="strike-anim">{text}</span>
    out.push(rest.slice(0, i), <span class="strike-anim" title={s.reason}>{rest.slice(i, i + s.claim.length)}</span>)
    rest = rest.slice(i + s.claim.length)
  }
  out.push(rest)
  return out
}

function EntryRow({ e }: { e: Entry }) {
  const time = e.ts ? <time class="num faint">{hms(e.ts)}</time> : null
  switch (e.kind) {
    case 'start': {
      const t = triggerText(e.trigger)
      return (
        <div class="tr-start">
          <div class="row"><b>Konsiliet kallas in</b>{time}</div>
          <div>{t.title}</div>
          {t.detail && <div class="muted">{t.detail}</div>}
        </div>
      )
    }
    case 'say': {
      const to = e.to && e.to !== 'alla' && e.to !== 'all' ? agentInfo(e.to).name.toLowerCase() : null
      const cs = cites(e.cites)
      return (
        <div class="tr-say">
          <div class="row"><Who id={e.agent!} />{to && <span class="faint">till {to}</span>}{time}</div>
          <p>{struckText(e.text ?? '', e.struck)}</p>
          {cs.length > 0 && <div class="cites">{cs.map((c) => <span class={`chip k-${c.kind}`} title={c.title}><i />{c.label}</span>)}</div>}
          {e.struck?.map((s) => <div class="tr-reason"><b>Struket:</b> {s.reason}</div>)}
        </div>
      )
    }
    case 'tool':
      return <div class="tr-small"><Who id={e.agent!} /><span class="muted">{toolLabel(e.tool ?? '', e.args)}</span>{time}</div>
    case 'handoff':
      return <div class="tr-small"><Who id={e.agent!} /><span class="muted">räcker över <span class="mono">{e.item}</span> till {agentInfo(e.to!).name.toLowerCase()}</span>{time}</div>
    case 'strike':
      return e.matched ? null : (
        <div class="tr-say tr-struck">
          <div class="row"><Who id="granskare" /><span class="faint">stryker {e.to ? `${agentInfo(e.to).name.toLowerCase()}s påstående` : ''}</span>{time}</div>
          <p><span class="strike-anim">{e.claim}</span></p>
          <div class="tr-reason">{e.reason}</div>
        </div>
      )
    case 'verdict': {
      const v = verdictParts(e.verdict)
      const lvl = v.level ? LEVELS[String(v.level).toLowerCase()] : null
      return (
        <div class="tr-verdict">
          <div class="row"><b>Bedömning</b>{lvl && <span class={`tag ${lvl.cls}`}>{lvl.label}</span>}{time}</div>
          {v.summary && <p>{v.summary}</p>}
          {v.points.length > 0 && <ul>{v.points.map((p) => <li>{p}</li>)}</ul>}
          {v.questions.length > 0 && <><div class="faint qs-h">Att ta med till vården</div><ol>{v.questions.map((q) => <li>{q}</li>)}</ol></>}
          <div class="faint disclaimer">Underlag, inte diagnos. Kontakta vården vid oro.</div>
        </div>
      )
    }
    default:
      return null
  }
}
