// Regissören tar emot händelser (live eller uppspelning) och spelar upp dem i scenen i tur och ordning.
// Transkriptet fylls på i samma takt som scenen, så att panelen och kontoret alltid visar samma sak.

import { agentInfo } from '../agents'
import type { Ev } from '../api'
import { verdictParts, LEVELS, metricMeta } from '../format'
import { Scene, esc, type ScreenData } from './scene'
import { rost, type Line } from './rost'

export type EntryKind = 'start' | 'say' | 'tool' | 'handoff' | 'strike' | 'verdict' | 'think' | 'move'
export interface Entry {
  n: number
  kind: EntryKind
  ts: number | null
  agent?: string
  to?: string
  text?: string
  cites?: any
  tool?: string
  args?: any
  item?: string
  claim?: string
  reason?: string
  verdict?: any
  trigger?: any
  struck?: { claim: string; reason: string }[]
  matched?: boolean
}

export type Mode = 'live' | 'replay' | 'demo'

export interface DirectorState {
  mode: Mode
  consultId: string | null
  trigger: any
  playing: boolean
  index: number
  total: number
  speed: number
  active: boolean   // ett möte pågår i scenen
  backlog: number
  finished: boolean
}

type ScreenProvider = (metric: string, hours: number, window?: [number, number] | null) => Promise<ScreenData | null>

const CONSULT_KINDS = new Set(['consult.start', 'agent.move', 'agent.think', 'agent.tool', 'agent.say', 'agent.handoff', 'review.strike', 'consult.verdict'])

export class Director {
  scene = new Scene()
  entries: Entry[] = []
  state: DirectorState = { mode: 'live', consultId: null, trigger: null, playing: true, index: 0, total: 0, speed: 1, active: false, backlog: 0, finished: false }
  private queue: Ev[] = []
  private replayEvents: Ev[] = []
  private pumping = false
  private listeners = new Set<() => void>()
  private n = 0
  private lastTs: number | null = null
  private liveBuffer: Ev[] = []   // live-händelser som kommer under en uppspelning
  screenProvider: ScreenProvider | null = null
  idleScreen: (() => ScreenData | null) | null = null

  on(l: () => void) { this.listeners.add(l); return () => { this.listeners.delete(l) } }
  private emit() { for (const l of this.listeners) l() }
  bump() { this.emit() }

  // ------------------------------------------------------------ in

  /** Live-händelse från servern. */
  live(ev: Ev, history: boolean) {
    if (!CONSULT_KINDS.has(ev.kind)) return
    if (this.state.mode !== 'live') { this.liveBuffer.push(ev); return }
    if (history) { this.historyBuffer.push(ev); this.scheduleHistory(); return }
    this.queue.push(ev)
    this.pump()
  }

  private historyBuffer: Ev[] = []
  private historyTimer: number | null = null
  private scheduleHistory() {
    if (this.historyTimer) clearTimeout(this.historyTimer)
    this.historyTimer = window.setTimeout(() => this.applyHistory(), 250)
  }

  /** Vid anslutning: om ett möte pågår, hoppa fram till där det är nu. */
  private applyHistory() {
    const evs = this.historyBuffer
    this.historyBuffer = []
    let start = -1
    for (let i = evs.length - 1; i >= 0; i--) if (evs[i].kind === 'consult.start') { start = i; break }
    if (start < 0) return
    const tail = evs.slice(start)
    if (tail.some((e) => e.kind === 'consult.verdict')) return
    if (evs[evs.length - 1].ts && Date.now() / 1000 - (evs[evs.length - 1].ts ?? 0) > 3600) return
    for (const e of tail) this.apply(e, true)
    this.emit()
  }

  // ------------------------------------------------------------ uppspelning

  replay(events: Ev[], mode: 'replay' | 'demo', speed = 1) {
    this.stop()
    this.state.mode = mode
    this.replayEvents = events.filter((e) => CONSULT_KINDS.has(e.kind))
    this.state.total = this.replayEvents.length
    this.state.index = 0
    this.state.finished = false
    this.setSpeed(speed)
    this.state.playing = true
    this.scene.paused = false
    this.queue = [...this.replayEvents]
    this.pump()
    this.emit()
  }

  seek(index: number) {
    if (this.state.mode === 'live') return
    const evs = this.replayEvents
    this.hardReset()
    for (let i = 0; i < index && i < evs.length; i++) this.apply(evs[i], true)
    this.state.index = Math.min(index, evs.length)
    this.queue = evs.slice(index)
    this.state.finished = this.queue.length === 0
    this.pump()
    this.emit()
  }

  restart() { this.seek(0) }

  setSpeed(s: number) {
    this.state.speed = s
    if (s > 2) rost.stop()
    else rost.setRate(s)
    if (this.state.mode !== 'live') this.scene.speed = s
    this.emit()
  }

  togglePlay() {
    this.state.playing = !this.state.playing
    this.scene.paused = !this.state.playing
    if (this.state.playing) rost.resume(); else rost.pause()
    if (this.state.playing && this.state.finished) this.restart()
    this.emit()
  }

  /** Tillbaka till live. Live-händelser som kom under uppspelningen spelas inte upp i efterhand. */
  backToLive() {
    this.stop()
    this.state.mode = 'live'
    this.state.playing = true
    this.scene.paused = false
    this.scene.speed = 1
    this.liveBuffer = []
    this.emit()
  }

  private stop() {
    this.hardReset()
    this.queue = []
  }

  private hardReset() {
    rost.stop()
    this.scene.reset()
    this.entries = []
    this.n = 0
    this.lastTs = null
    this.state.consultId = null
    this.state.trigger = null
    this.state.active = false
    this.state.index = 0
    this.state.finished = false
    this.pumping = false
    if (this.idleScreen) { const s = this.idleScreen(); if (s) this.scene.screen = s }
  }

  // ------------------------------------------------------------ uppspelningsloop

  private async pump() {
    if (this.pumping) return
    this.pumping = true
    const gen = this.scene.gen
    while (this.queue.length) {
      if (gen !== this.scene.gen) return
      const ev = this.queue.shift()!
      this.prefetchVoice()
      this.state.backlog = this.queue.length
      if (this.state.mode === 'live') this.scene.speed = 1 + Math.min(3, this.queue.length * 0.35)
      // i uppspelning: håll ungefär de verkliga pauserna, men aldrig längre än 2,5 s
      if (this.state.mode !== 'live' && this.lastTs != null && ev.ts != null) {
        const gap = Math.max(0, Math.min(2.5, ev.ts - this.lastTs))
        if (gap > 0.05) await this.scene.wait(gap)
        if (gen !== this.scene.gen) return
      }
      this.lastTs = ev.ts ?? this.lastTs
      try {
        await this.apply(ev, false)
      } catch (e) {
        console.error('kunde inte spela upp händelse', ev, e)
      }
      if (gen !== this.scene.gen) return
      if (this.state.mode !== 'live') this.state.index++
      this.emit()
    }
    this.pumping = false
    if (this.state.mode !== 'live' && this.state.index >= this.state.total) { this.state.finished = true; this.emit() }
  }

  // ------------------------------------------------------------ händelser

  private add(e: Omit<Entry, 'n'>): Entry {
    const full = { ...e, n: ++this.n }
    this.entries.push(full)
    if (this.entries.length > 400) this.entries.shift()
    this.emit()
    return full
  }

  async apply(ev: Ev, instant: boolean): Promise<void> {
    const p = ev.payload ?? {}
    const s = this.scene
    const gen0 = s.gen
    const id: string | undefined = p.agent
    switch (ev.kind) {
      case 'consult.start': {
        if (!instant && this.state.active) await this.endConsult(true)
        s.clearVerdict()
        this.state.consultId = p.consult_id ?? null
        this.state.trigger = p.trigger ?? null
        this.state.active = true
        const members: string[] = Array.isArray(p.members) && p.members.length ? p.members.map(String) : [...s.actors.keys()]
        s.setMembers(members)
        this.add({ kind: 'start', ts: ev.ts, trigger: p.trigger })
        this.focusTrigger(p.trigger)
        const walks = members.map((m, i) => {
          const a = s.ensure(m)
          const seat = s.seatAtTable(a)
          if (instant) return s.walkTo(m, seat, true)
          return s.wait(i * 0.22).then(() => s.walkTo(m, seat))
        })
        if (!instant) {
          await s.wait(1.2)
          await Promise.race([Promise.all(walks), s.wait(7)])
        }
        return
      }
      case 'agent.move': {
        if (!id) return
        const a = s.ensure(id)
        const spot = s.spotFor(a, String(p.to ?? 'bord'))
        const walk = s.walkTo(id, spot, instant)
        if (!instant) await Promise.race([walk, s.wait(0.6)])
        return
      }
      case 'agent.think': {
        if (!id || instant) return
        s.think(id, true)
        await s.wait(0.5)
        return
      }
      case 'agent.tool': {
        if (!id) return
        const tool = String(p.tool ?? '')
        const args = p.args ?? {}
        this.add({ kind: 'tool', ts: ev.ts, agent: id, tool, args })
        const where = toolZone(tool, args)
        const a = s.ensure(id)
        const spot = where === 'desk' ? a.home : s.spotFor(a, where)
        if (instant) { s.walkTo(id, spot, true); return }
        s.think(id, false)
        const before = a.target
        await Promise.race([s.walkTo(id, spot), s.wait(6)])
        s.chip(id, `<span class="lbl">${esc(toolLabel(tool, args))}</span>`, 2.6)
        if (where === 'arkiv') s.useTerminal(2.6)
        if (where === 'labb') s.useAnalyzer(2.6)
        s.busy(id, 2.6)
        const m = metricOf(tool, args)
        if (m) this.focusMetric(m, hoursOf(args), args.window ?? (args.start && args.end ? [args.start, args.end] : null))
        await s.wait(2.4)
        // från arkivet eller labbet: tillbaka dit agenten var (servern styr annars platsen med agent.move)
        if (where !== 'desk' && before && before !== spot && a.target === spot) s.walkTo(id, before)
        return
      }
      case 'agent.say': {
        if (!id) return
        const text = String(p.text ?? '')
        this.add({ kind: 'say', ts: ev.ts, agent: id, to: p.to, text, cites: p.cites })
        if (instant) { await s.say(id, text, p.cites, p.to, true); return }
        const voice = this.voice({ id: ev.id, agent: id, text, demo: this.state.mode === 'demo' })
        await s.say(id, text, p.cites, p.to)
        // nästa replik väntar tills rösten är klar, så att två läkare aldrig pratar i munnen på varandra
        if (voice && s.gen === gen0) await voice
        return
      }
      case 'agent.handoff': {
        if (!id || !p.to) return
        const to = String(p.to)
        const item = typeof p.item === 'string' ? p.item : p.item?.title ?? p.item?.label ?? 'Dokument'
        this.add({ kind: 'handoff', ts: ev.ts, agent: id, to, item })
        if (instant) return
        const a = s.ensure(id), b = s.ensure(to)
        await Promise.race([Promise.all([s.arrived(id), s.arrived(to)]), s.wait(5)])
        let walked = false
        const back = a.target
        if (Math.hypot(a.x - b.x, a.y - b.y) > 60) {
          walked = true
          await Promise.race([s.walkTo(id, s.spotFor(a, to)), s.wait(6)])
          s.face(id, to)
        }
        await s.fly(id, to, item)
        await s.wait(0.3)
        if (walked && back) s.walkTo(id, back)
        return
      }
      case 'review.strike': {
        const claim = String(p.claim ?? '')
        const reason = String(p.reason ?? '')
        const target = this.matchClaim(claim)
        if (target) { (target.struck ??= []).push({ claim, reason }); this.emit() }
        this.add({ kind: 'strike', ts: ev.ts, agent: 'granskare', to: p.target, claim, reason, matched: !!target })
        await s.strike(claim, reason, target?.agent ?? (p.target ? String(p.target) : null), instant)
        return
      }
      case 'consult.verdict': {
        const v = p.verdict
        this.add({ kind: 'verdict', ts: ev.ts, verdict: v })
        const parts = verdictParts(v)
        const lvl = parts.level ? LEVELS[String(parts.level).toLowerCase()] : undefined
        s.showVerdict(`<header><b>Markerad som lösning</b>${lvl ? `<span class="tag ${lvl.cls}">${esc(lvl.label)}</span>` : ''}<button class="x" aria-label="Stäng">Stäng</button></header>
          <p>${esc(parts.summary || 'Trådstartaren har markerat tråden som löst.')}</p>
          ${parts.questions.length ? `<div class="qs"><span>Att ta med till vården</span><ol>${parts.questions.slice(0, 4).map((q) => `<li>${esc(q)}</li>`).join('')}</ol></div>` : ''}`)
        if (instant) { this.state.active = false; return }
        const chair = s.members.includes('ordforande') ? 'ordforande' : s.members[0]
        if (chair && parts.summary) s.focus = chair
        await s.wait(6)
        await this.endConsult(false)
        return
      }
    }
  }

  /** Rösten till en replik, eller null om ljudet är av eller uppspelningen ligger efter. */
  private voice(line: Line): Promise<void> | null {
    if (!rost.on) return null
    const live = this.state.mode === 'live'
    if (live && this.queue.length >= 3) return null   // live och efter: hoppa över hellre än att släpa
    if (!live && this.state.speed > 2) return null
    const a = this.scene.ensure(line.agent)
    return rost.speak(line, {
      rate: live ? 1 : this.state.speed,
      // Live väntar så länge inget annat händer; uppspelning upp till 40 s (rösten görs i förväg på servern)
      maxWait: this.state.mode === 'demo' ? 5 : live ? 90 : 40,
      giveUp: live ? () => this.queue.length > 0 : undefined,
      onFrame: () => { a.mouthUntil = this.scene.t + 0.15 },
    })
  }

  private prefetchVoice() {
    if (!rost.on) return
    const next = this.queue.find((e) => e.kind === 'agent.say')
    if (next?.payload?.agent && next.payload.text)
      rost.prefetch({ id: next.id, agent: String(next.payload.agent), text: String(next.payload.text), demo: this.state.mode === 'demo' })
  }

  private async endConsult(quick: boolean) {
    const s = this.scene
    this.state.active = false
    const members = [...s.members]
    s.setMembers([])
    for (const m of members) {
      const a = s.ensure(m)
      a.tableSeat = null
      if (!quick) await s.wait(0.15)
      s.walkTo(m, a.home)
    }
    this.emit()
  }

  /** Hitta yttrandet som granskaren stryker i. */
  private matchClaim(claim: string): Entry | null { return matchClaimIn(this.entries, claim) }

  private focusTrigger(trigger: any) {
    if (!trigger) return
    const m = trigger.metric ?? (trigger.kind === 'question' ? 'hr' : null)
    if (m) this.focusMetric(m, trigger.hours ?? null, trigger.window ?? null)
  }

  focusMetric(metric: string, hours: number | null, window: [number, number] | null) {
    const prov = this.screenProvider
    if (!prov) return
    const h = hours ?? (window ? Math.max(3, Math.ceil((Date.now() / 1000 - window[0]) / 3600) + 1) : 24)
    prov(metric, h, window).then((d) => { if (d) this.scene.screen = d }).catch(() => {})
  }
}

// ------------------------------------------------------------ verktyg

function toolZone(tool: string, args: any): string {
  const t = tool.toLowerCase()
  if (/journal|1177/.test(t)) return 'arkiv'
  if (/labb?\b|lab_|prov|analys/.test(t) || t === 'hamta_labb') return 'labb'
  if (/medgemma|pubmed|k(a|ä)lla|source|litteratur|riktlinje|search/.test(t)) return 'arkiv'
  if (/tavla|wall|plot|graf/.test(t)) return 'tavla'
  void args
  return 'desk'
}

function metricOf(tool: string, args: any): string | null {
  if (args && typeof args.metric === 'string') return args.metric
  const t = tool.toLowerCase()
  if (/hrv/.test(t)) return 'hrv_rmssd'
  if (/spo2|syre/.test(t)) return 'spo2'
  if (/puls|\bhr\b|heart/.test(t)) return 'hr'
  return null
}

function hoursOf(a: any): number | null {
  const h = a?.timmar_bakat ?? a?.hours
  return typeof h === 'number' ? h : null
}

/** Bestämd form efter "senaste": dygnet, 3 dygnen, veckan, timmen, 12 timmarna. */
function fmtSpan(h: number): string {
  if (h === 168) return 'veckan'
  if (h >= 24 && h % 24 === 0) return h === 24 ? 'dygnet' : `${h / 24} dygnen`
  return h === 1 ? 'timmen' : `${String(h).replace('.', ',')} timmarna`
}

/** Etiketten med liten begynnelsebokstav, men förkortningar (HRV, SpO2) behålls. */
function metricLabel(metric: string): string {
  const l = metricMeta(metric).label
  return l.replace(/^(\S+)/, (w) => (/[A-ZÅÄÖ]{2}/.test(w) ? w : w.toLowerCase()))
}

export function toolLabel(tool: string, args: any): string {
  const t = tool.toLowerCase()
  const a = args ?? {}
  const h = hoursOf(a)
  const span = h ? `, senaste ${fmtSpan(h)}`
    : a.natter ? `, senaste ${Number(a.natter) === 1 ? 'natten' : `${a.natter} nätterna`}`
    : a.dagar ? `, senaste ${fmtSpan(Number(a.dagar) * 24)}` : ''
  if (/baslinje/.test(t)) return `Jämför ${metricLabel(String(a.metric ?? ''))} med baslinjen`
  if (a.metric) return `Slår upp ${metricLabel(String(a.metric))}${span}`
  if (/journal|1177/.test(t)) return `Läser journalen${a.sokord ? `: ${a.sokord}` : a.query ? `: ${a.query}` : ''}`
  if (/lab|prov/.test(t)) return `Läser provsvar${a.analyt ? `: ${a.analyt}` : a.analyte ? `: ${a.analyte}` : ''}`
  if (/sleep|s(o|ö)mn/.test(t)) return `Läser sömndata${span}`
  if (/medgemma/.test(t)) return 'Frågar MedGemma'
  if (/pubmed|k(a|ä)lla|source|litteratur|search/.test(t)) return `Söker källa${a.query ? `: ${a.query}` : ''}`
  return `${tool}${span}`
}

export function agentName(id?: string) { return id ? agentInfo(id).name : '' }

/** Bygger transkriptet direkt ur händelser, utan scen. Används i konsilielistan. */
export function entriesFromEvents(events: Ev[]): Entry[] {
  const out: Entry[] = []
  let n = 0
  for (const ev of events) {
    const p = ev.payload ?? {}
    const base = { n: ++n, ts: ev.ts }
    switch (ev.kind) {
      case 'consult.start': out.push({ ...base, kind: 'start', trigger: p.trigger }); break
      case 'agent.tool': out.push({ ...base, kind: 'tool', agent: p.agent, tool: String(p.tool ?? ''), args: p.args }); break
      case 'agent.say': out.push({ ...base, kind: 'say', agent: p.agent, to: p.to, text: String(p.text ?? ''), cites: p.cites }); break
      case 'agent.handoff': out.push({ ...base, kind: 'handoff', agent: p.agent, to: p.to, item: typeof p.item === 'string' ? p.item : p.item?.title ?? 'Dokument' }); break
      case 'review.strike': {
        const claim = String(p.claim ?? ''), reason = String(p.reason ?? '')
        const target = matchClaimIn(out, claim)
        if (target) (target.struck ??= []).push({ claim, reason })
        out.push({ ...base, kind: 'strike', agent: 'granskare', to: p.target, claim, reason, matched: !!target })
        break
      }
      case 'consult.verdict': out.push({ ...base, kind: 'verdict', verdict: p.verdict }); break
    }
  }
  return out
}

export function matchClaimIn(entries: Entry[], claim: string): Entry | null {
  const norm = (x: string) => x.toLowerCase().replace(/[^\p{L}\p{N} ]/gu, ' ').replace(/\s+/g, ' ').trim()
  const c = norm(claim)
  if (!c) return null
  const says = entries.filter((e) => e.kind === 'say' && e.agent !== 'granskare')
  for (let i = says.length - 1; i >= 0; i--) if (norm(says[i].text ?? '').includes(c)) return says[i]
  const words = new Set(c.split(' ').filter((w) => w.length > 3))
  let best: Entry | null = null, bestScore = 0
  for (const e of says) {
    const ws = norm(e.text ?? '').split(' ')
    const score = ws.filter((w) => words.has(w)).length / Math.max(1, words.size)
    if (score > bestScore) { bestScore = score; best = e }
  }
  return bestScore >= 0.5 ? best : null
}
