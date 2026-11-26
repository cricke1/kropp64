// Filmstudion: kontoret med en manuell klocka och några extra effekter (ilska, ånga, svett, bordsvältning)
// för trailern. Spelas in bildruta för bildruta av render/media/kontorsfilm.py via window.filmStep().
// Manuset är ett påhittat gräl i den anda läkarteamet faktiskt arbetar: alla har en egen tolkning,
// Trollet ifrågasätter, Kardiologen går för långt och moderatorn stryker det som saknar källa.

import '../styles.css'
import './office.css'
import { Scene } from './scene'
import { TABLE, TABLE_SEATS } from './map'
import { rect, type Ctx } from './pixel'
import { demoScreen } from './demo'

const css = document.createElement('style')
css.textContent = `
  .ob-bubble { transition: none !important; font-size: 13.5px; max-width: 250px; }
  .ob-bubble.rage { background: #fff1ec; border-color: #8a1c16; }
  .ob-bubble.rage .txt { color: #b4302a; font-weight: 600; }
  .ob-bubble.rage .tail { background: #fff1ec; border-color: #8a1c16; }
  .ob-card, .ob-strike .claim span { transition: none !important; }
  .ob-strike { font-size: 14px; max-width: 270px; }
  .ob-doc { font-size: 12px !important; padding: 3px 6px 4px !important; }
`
document.head.appendChild(css)

const s = new Scene()
const S = s as any
S.destroy()            // ingen egen animationsloop, klockan stegas utifrån
s.ambient = false
s.screen = demoScreen('hr')
document.getElementById('stage')!.appendChild(s.root)
S.resize()

// ------------------------------------------------------------------ platser
const PLATS: Record<string, number> = { ordforande: 0, kardiolog: 1, advokat: 2, somn: 3, idrott: 4, stress: 5, labb: 6, granskare: 7 }
const ids = Object.keys(PLATS)
s.setMembers(ids)
for (const id of ids) {
  const a = s.ensure(id)
  a.tableSeat = TABLE_SEATS[PLATS[id]]
  s.walkTo(id, a.tableSeat, true)
}

// ------------------------------------------------------------------ effekter
interface Fx { arg?: number; anga?: number; svett?: number; utrop?: number; skak?: number; hopp?: number }
const fx: Record<string, Fx> = {}
const bas: Record<string, { x: number; y: number }> = {}
for (const id of ids) { fx[id] = {}; const a = s.ensure(id); bas[id] = { x: a.x, y: a.y } }
const rod = new Set<string>()

interface Partikel { x: number; y: number; vx: number; vy: number; golv: number; w: number; h: number; col: string; rot: number }
const partiklar: Partikel[] = []

let bordFlyg = -1   // scentid när bordet välts
const BORDSKUGGA = '#3d2d22'

function ilskeTecken(c: Ctx, x: number, y: number, t: number) {
  // det klassiska "pulserande ådern"-tecknet, rött
  const p = Math.floor(t * 8) % 2
  const R = '#e0302a'
  const d = p ? 1 : 0
  rect(c, x - 2 - d, y - 2 - d, 2, 1, R); rect(c, x - 2 - d, y - 2 - d, 1, 2, R)
  rect(c, x + 1 + d, y - 2 - d, 2, 1, R); rect(c, x + 2 + d, y - 2 - d, 1, 2, R)
  rect(c, x - 2 - d, y + 2 + d, 2, 1, R); rect(c, x - 2 - d, y + 1 + d, 1, 2, R)
  rect(c, x + 1 + d, y + 2 + d, 2, 1, R); rect(c, x + 2 + d, y + 1 + d, 1, 2, R)
}

function rita(c: Ctx) {
  const t = s.t
  for (const id of ids) {
    const a = s.ensure(id), f = fx[id]
    const huvud = a.y - 22 + (a.pose === 'sit' ? 2 : 0)
    if (f.arg && t < f.arg) ilskeTecken(c, a.x + 7, huvud + 1, t)
    if (f.anga && t < f.anga) {
      for (let i = 0; i < 3; i++) {
        const u = ((t * 1.6 + i / 3) % 1)
        const x = a.x + (i - 1) * 5 + Math.sin(u * 6 + i) * 1.5, y = huvud - 2 - u * 12
        const col = u < 0.5 ? '#f2f2f0' : '#c9cccd'
        rect(c, x, y, u < 0.6 ? 2 : 1, u < 0.6 ? 2 : 1, col)
      }
    }
    if (f.svett && t < f.svett) {
      const u = (t * 1.2) % 1
      rect(c, a.x - 7, huvud + 3 + u * 5, 2, 3, '#7fc4ec'); rect(c, a.x - 7, huvud + 3 + u * 5, 1, 1, '#d9f0fb')
    }
    if (f.utrop && t < f.utrop) {
      rect(c, a.x - 1, huvud - 9, 2, 5, '#1b1820'); rect(c, a.x - 1, huvud - 3, 2, 2, '#1b1820')
      rect(c, a.x, huvud - 9, 1, 4, '#ffd23a')
    }
  }
  for (const p of partiklar) {
    c.save(); c.translate(Math.round(p.x), Math.round(p.y)); c.rotate(p.rot)
    c.fillStyle = '#1b1820'; c.fillRect(-p.w / 2 - 1, -p.h / 2 - 1, p.w + 2, p.h + 2)
    c.fillStyle = p.col; c.fillRect(-p.w / 2, -p.h / 2, p.w, p.h)
    c.restore()
  }
}

// bordet: ritas om ur en egen bild så att det kan flyga
let bordBild: HTMLCanvasElement | null = null
let bordPost: any = null
function forberedBord() {
  S.render()
  const lista: any[] = S.statics
  bordPost = lista.find((d) => Math.abs(d.depth - (TABLE.y + TABLE.h + 7)) < 0.01)
  const orig = bordPost.draw
  const [cv, c] = ((): [HTMLCanvasElement, Ctx] => { const e = document.createElement('canvas'); e.width = TABLE.w + 16; e.height = TABLE.h + 24; return [e, e.getContext('2d')!] })()
  c.translate(-TABLE.x + 4, -TABLE.y + 4); orig(c)
  bordBild = cv
  bordPost.draw = (cc: Ctx) => {
    if (bordFlyg < 0 || s.t < bordFlyg) { cc.drawImage(bordBild!, TABLE.x - 4, TABLE.y - 4); return }
    const u = Math.min(1, (s.t - bordFlyg) / 0.75)
    const e = 1 - (1 - u) ** 2
    const cx = TABLE.x + TABLE.w / 2 + 40 * e, cy = TABLE.y + TABLE.h / 2 - 38 * e + Math.sin(u * Math.PI) * -26
    cc.save(); cc.translate(Math.round(cx), Math.round(cy))
    cc.rotate(-Math.PI * 1.08 * e)
    cc.drawImage(bordBild!, -bordBild!.width / 2, -bordBild!.height / 2)
    cc.restore()
    if (u >= 1) rect(cc, cx - 50, cy + 14, 100, 2, BORDSKUGGA)
  }
  // effektlagret överst
  lista.push({ depth: 9999, draw: rita })
}

function valtBordet() {
  bordFlyg = s.t
  bordPost.depth = 300
  // allt som låg på bordet flyger
  const saker = [[20, 8, 9, 7, '#f4f1e8'], [82, 14, 8, 6, '#f4f1e8'], [53, 6, 5, 9, '#a9cfd6'], [61, 11, 3, 4, '#e6e1d4'],
    [47, 13, 3, 4, '#e6e1d4'], [36, 17, 10, 6, '#3f6a70'], [70, 6, 7, 5, '#f4f1e8'], [10, 18, 6, 5, '#f4f1e8']] as const
  for (const [dx, dy, w, h, col] of saker) {
    partiklar.push({ x: TABLE.x + dx, y: TABLE.y + dy, vx: (dx - 56) * 2.2 + (Math.random() - 0.5) * 60, vy: -120 - Math.random() * 90,
      golv: TABLE.y + 40 + Math.random() * 60, w, h, col, rot: 0 })
  }
  for (const id of ids) {
    if (id === 'kardiolog') continue
    fx[id].utrop = s.t + 1.6; fx[id].hopp = s.t
  }
}

function ilska(id: string, sek: number, anga = false) {
  fx[id].arg = s.t + sek
  if (anga) fx[id].anga = s.t + sek
  fx[id].skak = s.t + sek
  if (!rod.has(id)) {
    rod.add(id)
    const a = s.ensure(id)
    a.info = { ...a.info, look: { ...a.info.look, skin: '#e07a5f' } }
  }
}

function lugna(id: string) {
  const a = s.ensure(id)
  fx[id].arg = fx[id].anga = fx[id].skak = 0
  if (rod.has(id)) { rod.delete(id); a.info = { ...a.info, look: { ...a.info.look, skin: AGENT_HUD[id] } } }
}
const AGENT_HUD: Record<string, string> = {}
for (const id of ids) AGENT_HUD[id] = s.ensure(id).info.look.skin

function stall(id: string, mot?: string) {
  const a = s.ensure(id)
  a.pose = 'stand'
  bas[id] = { x: a.x, y: a.y }
  if (mot) s.face(id, mot)
}

function satt(id: string) {
  const a = s.ensure(id)
  s.walkTo(id, a.tableSeat!, true)
  bas[id] = { x: a.x, y: a.y }
}

/** Pratbubbla. arg=true ger röd text. behall=true låter andras bubblor stå kvar (alla pratar i mun på varandra). */
function sag(id: string, text: string, opt: { till?: string; kallor?: any; arg?: boolean; behall?: boolean } = {}) {
  const spara = S.fadeBubble
  if (opt.behall) S.fadeBubble = () => {}
  s.say(id, text, opt.kallor ?? [], opt.till)
  S.fadeBubble = spara
  const b = s.ensure(id).els.bubble
  if (b && opt.arg) b.classList.add('rage')
}

function tyst(id: string) {
  const a = s.ensure(id); a.els.bubble?.remove(); a.els.bubble = undefined
}
function tystAlla(utom?: string) { for (const id of ids) if (id !== utom) tyst(id) }

// ------------------------------------------------------------------ manus (sekunder i scenklockan)
const now = Math.floor(Date.now() / 1000)
const puls = { kind: 'series', metric: 'hr', start: now - 5 * 3600, end: now - 4.7 * 3600 }
const MANUS: [number, () => void][] = [
  [0.3, () => sag('ordforande', 'Vilopulsen låg över baslinjen i natt. Varför?', { kallor: [puls] })],
  [2.4, () => sag('kardiolog', '68 till 74 slag i minuten. Normalt är 57.', { kallor: [puls, 'Puls baslinje 28 d'] })],
  [4.6, () => { stall('advokat', 'kardiolog'); sag('advokat', 'Har du testat att dra åt armbandet?', { till: 'kardiolog' }) }],
  [6.4, () => { stall('kardiolog', 'advokat'); ilska('kardiolog', 30, true); sag('kardiolog', 'ARMBANDET SITTER FAST!', { till: 'advokat', arg: true }) }],
  [8.4, () => { stall('somn', 'kardiolog'); sag('somn', 'Han sov 5 h 40. Det är sömnen.', { kallor: ['Sömn i natt'], behall: true }) }],
  [10.0, () => { stall('idrott', 'somn'); ilska('idrott', 20); sag('idrott', 'Nej! Hårt pass 20:05 i går!', { till: 'somn', kallor: ['Puls 20:05-21:10'], arg: true, behall: true }) }],
  [11.5, () => { stall('stress', 'idrott'); ilska('stress', 20); sag('stress', 'HRV lågt tre nätter i rad!', { kallor: ['HRV 3 d'], arg: true, behall: true }) }],
  [12.9, () => { tyst('ordforande'); sag('advokat', 'Eller så är klockan trasig.', { behall: true }); ilska('somn', 20, true) }],
  [14.4, () => { tystAlla('kardiolog'); ilska('kardiolog', 30, true); fx.kardiolog.skak = s.t + 30
    sag('kardiolog', 'SAMMANTAGET: HJÄRTMUSKEL­INFLAMMATION!', { arg: true }) }],
  [18.6, () => { tystAlla(); valtBordet() }],
  [19.4, () => {
    const g = s.ensure('granskare'); stall('granskare', 'kardiolog'); g.penUp = true
    s.strike('tyder det på en begynnande hjärtmuskelinflammation', 'Ingen källa. Inget i datan pekar dit.', 'kardiolog')
  }],
  [20.0, () => { for (const id of ids) if (id !== 'kardiolog') { lugna(id) } }],
  [21.6, () => { lugna('kardiolog'); fx.kardiolog.svett = s.t + 20 }],
  [23.6, () => { sag('ordforande', 'Ingen åtgärd. Vi bevakar i natt.') }],
]
// Först flyger datan från skärmväggen till var och en: klockan, 1177 och datorn är underlaget för allt de säger.
const FORSKJ = 2.0
const DATA: [string, string][] = [
  ['kardiolog', 'Puls 30 d'], ['somn', 'Sömn'], ['idrott', 'Träningspass'], ['stress', 'HRV'],
  ['labb', 'Provsvar 1177'], ['ordforande', 'Journal 1177'], ['advokat', 'Skärmtid'], ['granskare', 'Alla källor'],
]
DATA.forEach(([id, etikett], i) => s.after(0.7 + i * 0.15, () => {
  const a = s.ensure(id)
  const label = S.el('ob-doc', etikett)
  S.flights.push({ from: { x: 209 + (i - 3.5) * 6, y: 40 }, to: { x: a.x + 2, y: a.y - 10 }, t0: s.t, dur: 0.85, label,
    done: () => { a.holdUntil = s.t + 1.5 } })
}))
for (const [t, fn] of MANUS) s.after(t + FORSKJ, fn)

// skakning och hopp läggs på positionen varje bildruta
function rorelse() {
  for (const id of ids) {
    const a = s.ensure(id), f = fx[id], b = bas[id]
    if (a.path.length) continue
    let dx = 0, dy = 0
    if (f.skak && s.t < f.skak) { dx = Math.round(Math.sin(s.t * 47 + id.length) * 1); dy = Math.round(Math.cos(s.t * 31) * 0.6) }
    if (f.hopp !== undefined && s.t - f.hopp < 0.35) dy -= Math.round(Math.sin(((s.t - f.hopp) / 0.35) * Math.PI) * 4)
    a.x = b.x + dx; a.y = b.y + dy
  }
  // papperen faller till golvet
  for (const p of partiklar) {
    if (p.y >= p.golv && p.vy > 0) { p.vx *= 0.6; p.vy = 0; p.y = p.golv; continue }
    p.vy += 340 / 30; p.x += p.vx / 30; p.y += p.vy / 30; p.rot += p.vx / 900
  }
  // strykningen ritas i scenens takt (CSS-övergångar följer inte den manuella klockan)
  document.querySelectorAll<HTMLElement>('.ob-strike .claim span.struck').forEach((el) => {
    const t0 = Number(el.dataset.t0 ?? (el.dataset.t0 = String(s.t)))
    el.style.backgroundSize = `${Math.min(100, ((s.t - t0) / 0.5) * 100)}% 2px`
  })
}

forberedBord()

;(window as any).filmStep = async (dt: number) => {
  S.update(dt)
  for (let i = 0; i < 4; i++) await new Promise((r) => setTimeout(r, 0))
  rorelse()
  S.render()
  return s.t
}
;(window as any).filmReady = true
