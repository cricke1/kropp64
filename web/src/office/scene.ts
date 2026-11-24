// Scenen: figurerna, deras rörelser, kameran och allt som ritas ovanpå (pratbubblor, källchips, strykningar).
// Scenen har en egen klocka. Uppspelningshastighet och paus påverkar allt, även väntan i regissören.

import { agentInfo, DEFAULT_ORDER, type AgentInfo } from '../agents'
import { bindUnits, cites as toCites, metricMeta, type Cite } from '../format'
import {
  analyzerScreen, buildGrid, deskMonitor, DESKS, deskSeat, drawBackground, MAP_H, MAP_W, staticDrawables, TABLE_SEATS,
  terminalScreen, ZONES, type Drawable, type Spot,
} from './map'
import { Pathfinder, type Pt } from './path'
import { rect, text3, type Ctx, canvas } from './pixel'
import { FOOT_Y, sprite, SPRITE_W, type Dir } from './sprites'

export interface ScreenData {
  metric: string
  points: [number, number][]
  window?: [number, number] | null
  live?: boolean
}

interface Actor {
  id: string
  info: AgentInfo
  x: number; y: number
  dir: Dir
  path: Pt[]
  pose: 'stand' | 'walk' | 'sit'
  target: Spot | null
  home: Spot
  tableSeat: Spot | null
  phase: number
  blinkAt: number
  mouthUntil: number
  busyUntil: number
  holdUntil: number
  pen: boolean
  penUp: boolean
  arrivals: (() => void)[]
  standUntil: number
  thinking: boolean
  at: string            // zonnamn där figuren står, eller 'desk'/'table'
  els: { bubble?: HTMLElement; think?: HTMLElement; chip?: HTMLElement }
}

interface Flight { from: Pt; to: Pt; t0: number; dur: number; label: HTMLElement; done: () => void }
interface Timer { at: number; fn: () => void; gen: number }

const WALK_SPEED = 58 // px per sekund

export class Scene {
  // logik
  t = 0
  speed = 1
  paused = false
  gen = 0
  actors = new Map<string, Actor>()
  private timers: Timer[] = []
  private flights: Flight[] = []
  private pf = new Pathfinder(buildGrid())
  private bg: HTMLCanvasElement | null = null
  private statics: Drawable[] | null = null
  screen: ScreenData = { metric: 'hr', points: [] }
  spoken = new Map<string, number>()
  members: string[] = []
  terminalUntil = 0
  analyzerUntil = 0
  focus: string | null = null
  ambient = true
  private nextAmbient = 8

  // rendering
  root: HTMLDivElement
  private cv: HTMLCanvasElement
  private ctx: Ctx
  private off: HTMLCanvasElement
  private offCtx: Ctx
  private layer: HTMLDivElement
  private k = 2         // enhetspixlar per logisk pixel
  private dpr = 1
  private viewW = MAP_W
  camX = 0
  private camTarget = 0
  private userPanUntil = 0
  private last = 0
  private raf = 0
  private hoverEl: HTMLDivElement
  private ro: ResizeObserver

  constructor() {
    this.root = document.createElement('div')
    this.root.className = 'office'
    this.cv = document.createElement('canvas')
    this.cv.className = 'office-canvas'
    this.ctx = this.cv.getContext('2d')!
    this.layer = document.createElement('div')
    this.layer.className = 'office-layer'
    this.hoverEl = document.createElement('div')
    this.hoverEl.className = 'ob-name'
    this.layer.appendChild(this.hoverEl)
    this.root.append(this.cv, this.layer)
    ;[this.off, this.offCtx] = canvas(MAP_W, MAP_H)
    for (const id of DEFAULT_ORDER) this.ensure(id)
    this.ro = new ResizeObserver(() => this.resize())
    this.ro.observe(this.root)
    this.bindPointer()
    this.last = performance.now()
    const loop = (now: number) => {
      const dt = Math.min(0.1, (now - this.last) / 1000)
      this.last = now
      this.update(dt)
      if (this.root.isConnected) this.render()
      this.raf = requestAnimationFrame(loop)
    }
    this.raf = requestAnimationFrame(loop)
  }

  destroy() { cancelAnimationFrame(this.raf); this.ro.disconnect() }

  // ------------------------------------------------------------ figurer

  ensure(id: string): Actor {
    let a = this.actors.get(id)
    if (a) return a
    const i = this.actors.size
    const home = deskSeat(DESKS.findIndex((d) => d.id === id) >= 0 ? DESKS.findIndex((d) => d.id === id) : i)
    // Okända agenter som inte har ett eget skrivbord får stå vid dörren tills de behövs.
    const ownDesk = DESKS.some((d) => d.id === id)
    const start = ownDesk ? home : { ...ZONES.dorr[0] }
    a = {
      id, info: agentInfo(id), x: start.x, y: start.y, dir: start.dir, path: [], pose: start.sit ? 'sit' : 'stand',
      target: start, home: ownDesk ? home : start, tableSeat: null, phase: Math.random() * 4, blinkAt: 1 + Math.random() * 4,
      mouthUntil: 0, busyUntil: 0, holdUntil: 0, pen: id === 'granskare', penUp: false, arrivals: [], standUntil: 0,
      thinking: false, at: ownDesk ? 'desk' : 'dorr', els: {},
    }
    this.actors.set(id, a)
    return a
  }

  /** Återställ allt till viloläge: alla vid sina skrivbord, inga bubblor. */
  reset() {
    this.gen++
    this.timers = []
    for (const f of this.flights) f.label.remove()
    this.flights = []
    for (const a of this.actors.values()) {
      for (const el of Object.values(a.els)) el?.remove()
      a.els = {}
      const s = a.home
      a.x = s.x; a.y = s.y; a.dir = s.dir; a.pose = s.sit ? 'sit' : 'stand'; a.path = []; a.target = s
      a.tableSeat = null; a.thinking = false; a.holdUntil = 0; a.busyUntil = 0; a.penUp = false; a.at = 'desk'
      a.arrivals.forEach((r) => r()); a.arrivals = []
    }
    this.layer.querySelectorAll('.ob-card').forEach((e) => e.remove())
    this.spoken.clear()
    this.members = []
    this.focus = null
    this.terminalUntil = this.analyzerUntil = 0
  }

  // ------------------------------------------------------------ klocka

  wait(sec: number): Promise<void> {
    const gen = this.gen
    return new Promise((res) => this.timers.push({ at: this.t + sec, fn: res, gen }))
  }
  after(sec: number, fn: () => void) {
    this.timers.push({ at: this.t + sec, fn, gen: this.gen })
  }

  // ------------------------------------------------------------ rörelse

  spotFor(a: Actor, where: string): Spot {
    const w = where.toLowerCase()
    if (/bord|konferens|m(o|ö)te|table|meeting/.test(w)) return this.seatAtTable(a)
    if (/skrivbord|desk|plats|hem|home/.test(w) || w === a.id) return a.home
    if (/arkiv|journal|1177|archive|bok|bibliotek|litteratur/.test(w)) return this.freeSpot('arkiv', a)
    if (/lab|prov|analys/.test(w)) return this.freeSpot('labb', a)
    if (/tavla|whiteboard|sk(a|ä)rm|monitor|v(a|ä)gg|graf/.test(w)) return this.freeSpot('tavla', a)
    if (/kaffe|fika|coffee|vatten/.test(w)) return this.freeSpot('kaffe', a)
    if (/d(o|ö)rr|door/.test(w)) return ZONES.dorr[0]
    if (this.actors.has(w) && w !== a.id) {
      const o = this.actors.get(w)!
      return this.besides(o, a)
    }
    return this.seatAtTable(a)
  }

  zoneOf(spot: Spot): string {
    for (const [name, spots] of Object.entries(ZONES)) if (spots.includes(spot)) return name
    if (TABLE_SEATS.includes(spot)) return 'table'
    return 'desk'
  }

  seatAtTable(a: Actor): Spot {
    if (a.tableSeat) return a.tableSeat
    const taken = new Set([...this.actors.values()].map((o) => o.tableSeat).filter(Boolean))
    let idx = a.id === 'ordforande' ? 0 : a.id === 'granskare' ? 7 : -1
    if (idx < 0 || taken.has(TABLE_SEATS[idx])) {
      const order = [2, 5, 1, 4, 3, 6, 0, 7]
      idx = order.find((i) => !taken.has(TABLE_SEATS[i]) && !(i === 0 && a.id !== 'ordforande' && !this.actors.has('ordforande')) ) ?? 2
    }
    a.tableSeat = TABLE_SEATS[idx]
    return a.tableSeat
  }

  private freeSpot(zone: string, a: Actor): Spot {
    const spots = ZONES[zone]
    const used = new Set([...this.actors.values()].filter((o) => o !== a).map((o) => o.target))
    return spots.find((s) => !used.has(s)) ?? spots[0]
  }

  private besides(o: Actor, a: Actor): Spot {
    for (const dx of [-15, 15, -24, 24]) {
      for (const dy of [0, 8, -8]) {
        const x = o.x + dx, y = o.y + dy
        if (!this.pf.blocked(Math.floor(x / 8), Math.floor(y / 8))) return { x, y, dir: dx < 0 ? 'right' : 'left' }
      }
    }
    void a
    return { x: o.x, y: o.y + 14, dir: 'up' }
  }

  walkTo(id: string, spot: Spot, instant = false): Promise<void> {
    const a = this.ensure(id)
    a.target = spot
    a.at = this.zoneOf(spot)
    if (instant) {
      a.x = spot.x; a.y = spot.y; a.dir = spot.dir; a.pose = spot.sit ? 'sit' : 'stand'; a.path = []
      a.arrivals.forEach((r) => r()); a.arrivals = []
      return Promise.resolve()
    }
    const goal = spot.approach ?? spot
    const path = Math.hypot(goal.x - a.x, goal.y - a.y) < 1 ? [] : this.pf.find({ x: a.x, y: a.y }, goal)
    if (spot.approach) path.push({ x: spot.x, y: spot.y })
    if (a.pose === 'sit') a.standUntil = this.t + 0.18
    a.path = path.filter((p, i) => i > 0 || Math.hypot(p.x - a.x, p.y - a.y) > 0.5)
    if (!a.path.length) { this.arrive(a); return Promise.resolve() }
    return new Promise((res) => a.arrivals.push(res))
  }

  arrived(id: string): Promise<void> {
    const a = this.ensure(id)
    if (!a.path.length) return Promise.resolve()
    return new Promise((res) => a.arrivals.push(res))
  }

  private arrive(a: Actor) {
    const s = a.target
    if (s) { a.x = s.x; a.y = s.y; a.dir = s.dir; a.pose = s.sit ? 'sit' : 'stand' } else a.pose = 'stand'
    const r = a.arrivals; a.arrivals = []
    r.forEach((f) => f())
  }

  face(id: string, toward: string) {
    const a = this.actors.get(id), b = this.actors.get(toward)
    if (!a || !b || a.pose !== 'stand') return
    const dx = b.x - a.x, dy = b.y - a.y
    a.dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : dy > 0 ? 'down' : 'up'
  }

  setMembers(ids: string[]) {
    this.members = ids
    ids.forEach((id) => this.ensure(id))
  }

  // ------------------------------------------------------------ överlägg

  private el(cls: string, html = ''): HTMLDivElement {
    const d = document.createElement('div')
    d.className = cls
    d.innerHTML = html
    this.layer.appendChild(d)
    return d
  }

  /** Pratbubbla med skrivmaskinseffekt. Löser när texten skrivits ut och hunnit läsas. */
  async say(id: string, text: string, cites: any, to?: string, instant = false) {
    const a = this.ensure(id)
    const gen = this.gen
    this.spoken.set(id, (this.spoken.get(id) ?? 0) + 1)
    if (instant) return
    this.focus = id
    a.thinking = false
    a.els.think?.remove(); a.els.think = undefined
    // stäng andras bubblor
    for (const o of this.actors.values()) if (o !== a && o.els.bubble) this.fadeBubble(o)
    a.els.bubble?.remove()
    if (to && this.actors.has(to)) this.face(id, to)
    const b = this.el('ob-bubble')
    b.style.setProperty('--agent', a.info.color)
    const toName = to ? (to === 'alla' || to === 'all' ? 'i tråden' : this.actors.has(to) ? `till ${agentInfo(to).name.toLowerCase()}` : '') : ''
    b.innerHTML = `<div class="who"><b>${esc(a.info.name)}</b>${toName ? `<span>${esc(toName)}</span>` : ''}</div><div class="txt"></div><div class="cites"></div><i class="tail"></i>`
    a.els.bubble = b
    const txt = b.querySelector('.txt') as HTMLElement
    const chunks = splitChunks(text, 170).map(bindUnits)
    for (let ci = 0; ci < chunks.length; ci++) {
      const chunk = chunks[ci]
      // skriv ut ordvis i takt med scenklockan
      const cps = 46
      const start = this.t
      txt.textContent = ''
      while (true) {
        if (gen !== this.gen) return
        const n = Math.min(chunk.length, Math.floor((this.t - start) * cps))
        // ordvis: visa aldrig ett halvt ord
        txt.textContent = n >= chunk.length ? chunk : chunk.slice(0, Math.max(0, chunk.lastIndexOf(' ', n)))
        a.mouthUntil = this.t + 0.12
        if (n >= chunk.length) break
        await this.wait(0.03)
      }
      if (ci === chunks.length - 1) {
        const cs = toCites(cites)
        if (cs.length) (b.querySelector('.cites') as HTMLElement).innerHTML = cs.map(chipHtml).join('')
      }
      await this.wait(1.1 + chunk.length / 34)
      if (gen !== this.gen) return
    }
    b.classList.add('done')
    this.after(5, () => { if (a.els.bubble === b) this.fadeBubble(a) })
  }

  private fadeBubble(a: Actor) {
    const b = a.els.bubble
    if (!b) return
    a.els.bubble = undefined
    b.classList.add('out')
    setTimeout(() => b.remove(), 260)
  }

  think(id: string, on: boolean) {
    const a = this.ensure(id)
    a.thinking = on
    if (on && !a.els.think) a.els.think = this.el('ob-think', '<i></i><i></i><i></i>')
    if (!on && a.els.think) { a.els.think.remove(); a.els.think = undefined }
    if (on) this.after(14, () => { if (a.thinking) this.think(id, false) })
  }

  chip(id: string, html: string, sec: number) {
    const a = this.ensure(id)
    a.els.chip?.remove()
    const c = this.el('ob-chip', html)
    a.els.chip = c
    this.after(sec, () => { if (a.els.chip === c) { c.remove(); a.els.chip = undefined } })
  }

  busy(id: string, sec: number) { this.ensure(id).busyUntil = this.t + sec }
  useTerminal(sec: number) { this.terminalUntil = this.t + sec }
  useAnalyzer(sec: number) { this.analyzerUntil = this.t + sec }

  /** Ett papper flyger i en båge från en figur till en annan. */
  fly(fromId: string, toId: string, item: string): Promise<void> {
    const a = this.ensure(fromId), b = this.ensure(toId)
    const label = this.el('ob-doc', esc(item || 'Dokument'))
    return new Promise((done) => {
      this.flights.push({ from: { x: a.x + 4, y: a.y - 10 }, to: { x: b.x - 2, y: b.y - 10 }, t0: this.t, dur: 0.9, label, done: () => { b.holdUntil = this.t + 4; done() } })
    })
  }

  /** Granskaren stryker ett påstående. Kortet visas ovanför den som sa det. */
  async strike(claim: string, reason: string, speaker: string | null, instant = false) {
    if (instant) return
    const g = this.ensure('granskare')
    g.penUp = true
    this.focus = 'granskare'
    const anchor = speaker && this.actors.has(speaker) ? speaker : 'granskare'
    const card = this.el('ob-card ob-strike')
    card.dataset.anchor = anchor
    card.innerHTML = `<div class="claim"><span>${esc(claim)}</span></div><div class="reason"><b>Strukit av moderator.</b> Anledning: ${esc(reason || 'saknar stöd i datan.')}</div>`
    await this.wait(0.5)
    card.querySelector('.claim span')!.classList.add('struck')
    await this.wait(2.8 + Math.min(4, (claim.length + reason.length) / 50))
    g.penUp = false
    card.classList.add('out')
    setTimeout(() => card.remove(), 300)
  }

  showVerdict(html: string) {
    this.layer.querySelectorAll('.ob-verdict').forEach((e) => e.remove())
    const v = this.el('ob-card ob-verdict', html)
    v.querySelector('button')?.addEventListener('click', () => v.remove())
  }
  clearVerdict() { this.layer.querySelectorAll('.ob-verdict').forEach((e) => e.remove()) }

  // ------------------------------------------------------------ uppdatering

  private update(dtReal: number) {
    if (this.paused) return
    const dt = dtReal * this.speed
    this.t += dt
    // timers
    if (this.timers.length) {
      const due = this.timers.filter((x) => x.at <= this.t)
      if (due.length) {
        this.timers = this.timers.filter((x) => x.at > this.t)
        for (const x of due) if (x.gen === this.gen) x.fn()
      }
    }
    for (const a of this.actors.values()) {
      if (a.path.length && this.t >= a.standUntil) {
        a.pose = 'walk'
        let step = WALK_SPEED * dt
        while (step > 0 && a.path.length) {
          const p = a.path[0]
          const dx = p.x - a.x, dy = p.y - a.y
          const d = Math.hypot(dx, dy)
          if (d > 0.01) a.dir = Math.abs(dx) > Math.abs(dy) * 1.1 ? (dx > 0 ? 'right' : 'left') : dy > 0 ? 'down' : 'up'
          if (d <= step) { a.x = p.x; a.y = p.y; step -= d; a.path.shift() }
          else { a.x += (dx / d) * step; a.y += (dy / d) * step; step = 0 }
        }
        a.phase += dt * 7.5
        if (!a.path.length) this.arrive(a)
      }
      if (this.t > a.blinkAt + 0.14) a.blinkAt = this.t + 2.5 + Math.random() * 3.5
    }
    for (const f of [...this.flights]) {
      if (this.t - f.t0 >= f.dur) {
        this.flights.splice(this.flights.indexOf(f), 1)
        f.label.remove()
        f.done()
      }
    }
    // liv i kontoret när inget möte pågår
    if (this.ambient && !this.members.length && this.t > this.nextAmbient) {
      this.nextAmbient = this.t + 9 + Math.random() * 14
      const idle = [...this.actors.values()].filter((a) => a.at === 'desk' && !a.path.length && DESKS.some((d) => d.id === a.id))
      const r = Math.random()
      if (idle.length) {
        const a = idle[Math.floor(Math.random() * idle.length)]
        if (r < 0.45) {
          const gen = this.gen
          const back = a.home
          this.walkTo(a.id, this.freeSpot('kaffe', a)).then(() => this.wait(3 + Math.random() * 3)).then(() => { if (gen === this.gen && !this.members.length) this.walkTo(a.id, back) })
        } else {
          a.busyUntil = this.t + 4 + Math.random() * 6
        }
      }
    }
    // kamera
    const fa = this.focus ? this.actors.get(this.focus) : null
    const fx = fa ? fa.x : 208
    if (performance.now() > this.userPanUntil) this.camTarget = clamp(fx - this.viewW / 2, 0, MAP_W - this.viewW)
    this.camX += (this.camTarget - this.camX) * Math.min(1, dtReal * 3)
  }

  // ------------------------------------------------------------ rendering

  private resize() {
    const w = this.root.clientWidth
    if (!w) return
    this.dpr = window.devicePixelRatio || 1
    const fit = Math.floor((w * this.dpr) / MAP_W)
    let k = fit
    if (k / this.dpr < 1.45) k = Math.max(1, Math.ceil(1.45 * this.dpr))
    this.k = Math.max(1, k)
    this.viewW = Math.min(MAP_W, Math.floor((w * this.dpr) / this.k))
    this.cv.width = this.viewW * this.k
    this.cv.height = MAP_H * this.k
    const cssW = (this.viewW * this.k) / this.dpr, cssH = (MAP_H * this.k) / this.dpr
    this.cv.style.width = `${cssW}px`
    this.cv.style.height = `${cssH}px`
    this.layer.style.width = `${cssW}px`
    this.layer.style.height = `${cssH}px`
    this.root.style.height = `${cssH}px`
    this.root.classList.toggle('panning', this.viewW < MAP_W)
    this.ctx.imageSmoothingEnabled = false
    this.camX = clamp(this.camX, 0, MAP_W - this.viewW)
  }

  /** Logisk punkt till CSS-pixlar i överlägget. */
  private toCss(x: number, y: number) {
    const s = this.k / this.dpr
    return { x: (x - Math.round(this.camX)) * s, y: y * s }
  }

  private render() {
    const c = this.offCtx
    if (!this.bg) {
      this.bg = drawBackground()
      this.statics = staticDrawables((id) => agentInfo(id).color)
    }
    c.drawImage(this.bg, 0, 0)
    this.drawWallScreen(c)
    this.drawStatusScreen(c)
    terminalScreen(c, this.t < this.terminalUntil ? 1 : 0, this.t)
    analyzerScreen(c, this.t < this.analyzerUntil ? 1 : 0, this.t)

    const list: Drawable[] = [...this.statics!]
    // skrivbordsskärmar ligger ovanpå skrivborden men under figurerna framför
    DESKS.forEach((d) => {
      const a = this.actors.get(d.id)
      const atDesk = a && a.at === 'desk' && !a.path.length
      const busy = a && this.t < a.busyUntil
      list.push({ depth: d.y + 22.2, draw: (cx) => deskMonitor(cx, d, (cc, x, y, w, h) => this.monitorContent(cc, x, y, w, h, a?.info.color ?? '#6a7a80', !!atDesk, !!busy)) })
    })
    for (const a of this.actors.values()) list.push({ depth: a.y, draw: (cx) => this.drawActor(cx, a) })
    list.sort((p, q) => p.depth - q.depth)
    for (const d of list) d.draw(c)
    for (const f of this.flights) this.drawFlight(c, f)

    const ctx = this.ctx
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(this.off, Math.round(this.camX), 0, this.viewW, MAP_H, 0, 0, this.cv.width, this.cv.height)
    this.placeOverlays()
  }

  private drawActor(c: Ctx, a: Actor) {
    const walking = a.pose === 'walk'
    const pose = walking ? 'walk' : a.pose
    const frame = walking ? Math.floor(a.phase) % 4 : 0
    const img = sprite(a.info.look, {
      dir: a.dir, pose, frame, blink: this.t > a.blinkAt, mouth: this.t < a.mouthUntil && Math.floor(this.t * 9) % 2 === 0,
      busy: pose === 'sit' && this.t < a.busyUntil ? Math.floor(this.t * 6) % 2 : 0,
      hold: this.t < a.holdUntil, pen: a.pen && (a.penUp || a.pose !== 'sit'), penUp: a.penUp,
    })
    const x = Math.round(a.x - SPRITE_W / 2), y = Math.round(a.y - FOOT_Y)
    if (pose !== 'sit') {
      c.fillStyle = 'rgba(20,16,24,0.26)'
      c.fillRect(Math.round(a.x) - 5, Math.round(a.y) - 1, 10, 2)
      c.fillRect(Math.round(a.x) - 4, Math.round(a.y) + 1, 8, 1)
    }
    c.drawImage(img, x, y)
  }

  private drawFlight(c: Ctx, f: Flight) {
    const p = Math.min(1, (this.t - f.t0) / f.dur)
    const e = p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2
    const x = f.from.x + (f.to.x - f.from.x) * e
    const y = f.from.y + (f.to.y - f.from.y) * e - Math.sin(p * Math.PI) * 18
    c.fillStyle = 'rgba(20,16,24,0.22)'
    c.fillRect(Math.round(x) - 2, Math.round(f.from.y + (f.to.y - f.from.y) * e) + 12, 6, 2)
    rect(c, x - 3, y - 4, 7, 9, '#1b1820')
    rect(c, x - 2, y - 3, 5, 7, '#f4f1e8')
    rect(c, x - 1, y - 2, 3, 1, '#a9a393'); rect(c, x - 1, y, 3, 1, '#a9a393'); rect(c, x - 1, y + 2, 2, 1, '#a9a393')
    const pos = this.toCss(x, y - 8)
    f.label.style.transform = `translate(${pos.x}px, ${pos.y}px) translate(-50%, -100%)`
  }

  private monitorContent(c: Ctx, x: number, y: number, w: number, h: number, col: string, atDesk: boolean, busy: boolean) {
    if (!atDesk && !busy) {
      rect(c, x, y, w, h, '#162024')
      const blink = Math.floor(this.t * 1.2) % 2
      if (blink) rect(c, x + w - 3, y + h - 2, 1, 1, '#4cc38a')
      return
    }
    rect(c, x, y, w, h, '#1e3036')
    if (busy) {
      // graf som ritas fram i agentens färg
      const n = Math.floor((this.t * 14) % (w + 8))
      for (let i = 0; i < Math.min(w - 2, n); i++) {
        const v = Math.sin((i + x) * 0.55) * 2.5 + Math.sin((i + y) * 0.21) * 2
        rect(c, x + 1 + i, y + Math.round(h / 2 + v), 1, 1, col)
      }
      rect(c, x + 1, y + 1, 8, 1, '#8fb0b8')
    } else {
      for (let i = 0; i < 5; i++) rect(c, x + 2 + (i % 2) * 2, y + 2 + i * 2, 6 + ((i * 7 + x) % 10), 1, i === 0 ? col : '#4f6d74')
    }
  }

  private drawWallScreen(c: Ctx) {
    const X = 154, Y = 9, W = 110, H = 29
    rect(c, X, Y, W, H, '#142024')
    const meta = metricMeta(this.screen.metric)
    const col = METRIC_PIX[this.screen.metric] ?? '#c9d1d6'
    text3(c, meta.short.slice(0, 5).toUpperCase(), X + 3, Y + 2, col)
    const pts = this.screen.points
    const px0 = X + 3, py0 = Y + 9, pw = W - 6, ph = H - 11
    // rutnät
    for (let gx = px0; gx < px0 + pw; gx += 3) { rect(c, gx, py0, 1, 1, '#22343a'); rect(c, gx, py0 + Math.floor(ph / 2), 1, 1, '#22343a'); rect(c, gx, py0 + ph - 1, 1, 1, '#2b4046') }
    if (pts.length < 2) {
      const sweep = Math.floor((this.t * 20) % pw)
      rect(c, px0, py0 + Math.floor(ph / 2), sweep, 1, '#35545c')
      return
    }
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0]
    let lo = Infinity, hi = -Infinity
    for (const [, v] of pts) { if (v < lo) lo = v; if (v > hi) hi = v }
    if (hi - lo < 1e-6) { hi += 1; lo -= 1 }
    const pad = (hi - lo) * 0.12
    lo -= pad; hi += pad
    const win = this.screen.window
    if (win) {
      const a = Math.max(0, Math.floor(((win[0] - t0) / (t1 - t0)) * pw)), b = Math.min(pw, Math.ceil(((win[1] - t0) / (t1 - t0)) * pw))
      if (b > a) for (let i = a; i < b; i++) rect(c, px0 + i, py0, 1, ph, i % 2 ? '#3a2326' : '#33202a')
    }
    const cols: [number, number][] = new Array(pw).fill(null).map(() => [Infinity, -Infinity])
    for (const [ts, v] of pts) {
      const i = Math.min(pw - 1, Math.max(0, Math.floor(((ts - t0) / (t1 - t0 || 1)) * (pw - 1))))
      const yv = py0 + ph - 1 - ((v - lo) / (hi - lo)) * (ph - 1)
      cols[i][0] = Math.min(cols[i][0], yv); cols[i][1] = Math.max(cols[i][1], yv)
    }
    // en "svepande" ritning som på en patientmonitor när skärmen visar live
    const reveal = this.screen.live ? pw : pw
    let prev: number | null = null
    for (let i = 0; i < reveal; i++) {
      const [a, b] = cols[i]
      if (a === Infinity) continue
      const top = Math.round(a), bot = Math.round(b)
      if (prev != null) {
        const lo2 = Math.min(prev, top), hi2 = Math.max(prev, bot)
        rect(c, px0 + i, lo2, 1, hi2 - lo2 + 1, col)
      } else rect(c, px0 + i, top, 1, bot - top + 1, col)
      prev = Math.round((a + b) / 2)
    }
    // senaste värdet
    const lastV = pts[pts.length - 1][1]
    const s = lastV.toFixed(meta.digits > 0 && lastV < 20 ? 1 : 0)
    text3(c, s, X + W - 3 - s.length * 4, Y + 2, '#e6ecee')
    if (this.screen.live && Math.floor(this.t * 2) % 2) rect(c, X + W - 5 - s.length * 4 - 2, Y + 4, 2, 1, col)
  }

  private drawStatusScreen(c: Ctx) {
    const X = 271, Y = 12
    rect(c, X, Y, 20, 23, '#142024')
    const ids = this.members.length ? this.members : []
    if (!ids.length) {
      // viloläge: klockan
      const d = new Date()
      const s = `${String(d.getHours()).padStart(2, '0')}${d.getSeconds() % 2 ? ':' : ' '}${String(d.getMinutes()).padStart(2, '0')}`
      text3(c, s.slice(0, 2), X + 3, Y + 5, '#8fb0b8')
      text3(c, s.slice(3, 5), X + 10, Y + 13, '#8fb0b8')
      if (s[2] === ':') rect(c, X + 10, Y + 8, 1, 1, '#8fb0b8')
      return
    }
    ids.slice(0, 8).forEach((id, i) => {
      const yy = Y + 2 + i * 2.6
      const col = agentInfo(id).color
      rect(c, X + 2, Math.round(yy), 2, 2, col)
      const n = Math.min(4, this.spoken.get(id) ?? 0)
      for (let j = 0; j < n; j++) rect(c, X + 6 + j * 3, Math.round(yy), 2, 2, '#4f6d74')
    })
  }

  private placeOverlays() {
    const W = this.layer.clientWidth
    for (const a of this.actors.values()) {
      const headTop = a.y - FOOT_Y + (a.pose === 'sit' ? 3 : 1)
      const p = this.toCss(a.x, headTop)
      const b = a.els.bubble
      if (b) {
        const bw = b.offsetWidth
        const left = clamp(p.x - bw / 2, 4, Math.max(4, W - bw - 4))
        // håll bubblan inom scenen även när figuren står högt upp
        const top = Math.max(4, p.y - 6 - b.offsetHeight)
        b.style.transform = `translate(${left}px, ${top}px)`
        ;(b.querySelector('.tail') as HTMLElement).style.left = `${clamp(p.x - left, 10, bw - 10)}px`
      }
      if (a.els.think) a.els.think.style.transform = `translate(${p.x}px, ${p.y - 4}px) translate(-50%, -100%)`
      if (a.els.chip) {
        const q = this.toCss(a.x, a.y + 3)
        a.els.chip.style.transform = `translate(${q.x}px, ${q.y}px) translateX(-50%)`
      }
    }
    this.layer.querySelectorAll<HTMLElement>('.ob-strike').forEach((card) => {
      const a = this.actors.get(card.dataset.anchor ?? '')
      if (!a) return
      const p = this.toCss(a.x, a.y - FOOT_Y)
      const w = card.offsetWidth
      card.style.transform = `translate(${clamp(p.x - w / 2, 4, Math.max(4, W - w - 4))}px, ${Math.max(4, p.y - card.offsetHeight - 10)}px)`
    })
  }

  // ------------------------------------------------------------ pekare: namn vid hovring, panorering på mobil

  private bindPointer() {
    let dragX: number | null = null, cam0 = 0
    this.cv.addEventListener('pointerdown', (e) => {
      if (this.viewW >= MAP_W) return
      dragX = e.clientX; cam0 = this.camX
      this.cv.setPointerCapture(e.pointerId)
    })
    this.cv.addEventListener('pointermove', (e) => {
      const r = this.cv.getBoundingClientRect()
      const s = this.k / this.dpr
      if (dragX != null) {
        this.camTarget = this.camX = clamp(cam0 - (e.clientX - dragX) / s, 0, MAP_W - this.viewW)
        this.userPanUntil = performance.now() + 6000
      }
      const lx = (e.clientX - r.left) / s + this.camX, ly = (e.clientY - r.top) / s
      let hit: Actor | null = null
      for (const a of this.actors.values()) if (Math.abs(lx - a.x) < 7 && ly > a.y - 21 && ly < a.y + 1) hit = a
      if (hit) {
        this.hoverEl.innerHTML = `<b>${esc(hit.info.name)}</b> ${esc(hit.info.role)}`
        const p = this.toCss(hit.x, hit.y + 2)
        this.hoverEl.style.transform = `translate(${p.x}px, ${p.y}px) translateX(-50%)`
        this.hoverEl.classList.add('on')
        this.cv.style.cursor = 'default'
      } else this.hoverEl.classList.remove('on')
    })
    const up = () => { dragX = null }
    this.cv.addEventListener('pointerup', up)
    this.cv.addEventListener('pointercancel', up)
    this.cv.addEventListener('pointerleave', () => this.hoverEl.classList.remove('on'))
  }
}

const METRIC_PIX: Record<string, string> = {
  hr: '#4cc38a', hrv_rmssd: '#e0905e', spo2: '#4fb3d9', resp_rate: '#dcc05a', skin_temp: '#c9cdd0', steps: '#9fb0bb',
}

function clamp(v: number, a: number, b: number) { return Math.max(a, Math.min(b, v)) }

export function esc(s: string) {
  return String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch]!)
}

export function chipHtml(c: Cite) {
  return `<span class="chip k-${c.kind}" title="${esc(c.title)}"><i></i>${esc(c.label)}</span>`
}

/** Delar lång text i bubbelstora bitar, helst vid meningsslut. */
function splitChunks(text: string, max: number): string[] {
  const t = text.trim().replace(/\s+/g, ' ')
  if (t.length <= max) return [t]
  const sentences = t.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g) ?? [t]
  const out: string[] = []
  let cur = ''
  for (const s of sentences) {
    if ((cur + s).length > max && cur) { out.push(cur.trim()); cur = '' }
    if (s.length > max) {
      const words = s.split(' ')
      for (const w of words) {
        if ((cur + ' ' + w).length > max && cur) { out.push(cur.trim()); cur = '' }
        cur += (cur ? ' ' : '') + w
      }
    } else cur += s
  }
  if (cur.trim()) out.push(cur.trim())
  return out
}
