// Kontoret: mått, zoner, platser, hinder och all statisk grafik.
// Koordinater är i logiska pixlar. Allt ritas i 3/4-vy: golvet ses uppifrån, väggar och möbler framifrån.

import type { Dir } from './sprites'
import { canvas, rect, shade, type Ctx } from './pixel'

export const MAP_W = 416
export const MAP_H = 288
export const WALL = 44 // bakväggens höjd

export interface Spot { x: number; y: number; dir: Dir; sit?: boolean; approach?: { x: number; y: number } }
export interface Drawable { depth: number; draw: (c: Ctx) => void }

// ---------------------------------------------------------------- slumptal med frö

function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// ---------------------------------------------------------------- färger

const C = {
  cap: '#232a2c',
  wall: '#4b5a57', wallHi: '#55655f', wallLo: '#41504d', base: '#2f3837',
  archWall: '#44514a', labWall: '#8a9e99', labWallLine: '#7b8f8a',
  wood: '#7d5e45', woodLine: '#694e39', woodHi: '#88684d',
  carpet: '#3d524e', carpetDot: '#455b56',
  tile: '#a9b3af', tile2: '#a0aaa6', tileLine: '#8d9894',
  rug: '#6b4739', rugBorder: '#56382d', rugLine: '#79523f',
  desk: '#a47a51', deskHi: '#b38a5f', deskFace: '#835f3e', deskDark: '#6a4b31',
  metal: '#4a545a', metalHi: '#69757b', metalDark: '#353d42',
  screenOff: '#1d2629', screenGlow: '#2b4248',
  chair: '#36414a', chairHi: '#45525b', chairDark: '#283038',
  paper: '#efebe0', paperLine: '#c4bdac',
  leaf: '#4f7f4a', leafHi: '#64994f', leafDark: '#3b6238', pot: '#b2643c', potDark: '#8f4d2d',
  shadow: 'rgba(20,16,24,0.28)',
}

// ---------------------------------------------------------------- möbler och platser

export const DESKS: { id: string; x: number; y: number }[] = [
  { id: 'ordforande', x: 16, y: 172 },
  { id: 'kardiolog', x: 92, y: 172 },
  { id: 'somn', x: 280, y: 172 },
  { id: 'idrott', x: 356, y: 172 },
  { id: 'stress', x: 16, y: 228 },
  { id: 'labb', x: 92, y: 228 },
  { id: 'advokat', x: 280, y: 228 },
  { id: 'granskare', x: 356, y: 228 },
]
export const DESK_W = 44

export function deskSeat(i: number): Spot {
  const d = DESKS[i % DESKS.length]
  return { x: d.x + 22, y: d.y + 34, dir: 'up', sit: true }
}

export const TABLE = { x: 152, y: 92, w: 112, h: 28 }

// Ordförandens plats är vänstra kortsidan, granskaren sitter vid högra.
export const TABLE_SEATS: Spot[] = [
  { x: 142, y: 116, dir: 'right', sit: true, approach: { x: 138, y: 116 } },  // 0 ordförande
  { x: 178, y: 99, dir: 'down', sit: true, approach: { x: 178, y: 84 } },
  { x: 208, y: 99, dir: 'down', sit: true, approach: { x: 208, y: 84 } },
  { x: 238, y: 99, dir: 'down', sit: true, approach: { x: 238, y: 84 } },
  { x: 178, y: 141, dir: 'up', sit: true },
  { x: 208, y: 141, dir: 'up', sit: true },
  { x: 238, y: 141, dir: 'up', sit: true },
  { x: 274, y: 116, dir: 'left', sit: true, approach: { x: 278, y: 116 } },   // 7 granskare
]

export const ZONES: Record<string, Spot[]> = {
  arkiv: [
    { x: 34, y: 70, dir: 'up' }, { x: 82, y: 70, dir: 'up' }, { x: 100, y: 128, dir: 'up' }, { x: 58, y: 72, dir: 'up' },
  ],
  labb: [
    { x: 318, y: 86, dir: 'up' }, { x: 356, y: 86, dir: 'up' }, { x: 338, y: 88, dir: 'up' }, { x: 378, y: 88, dir: 'up' },
  ],
  tavla: [
    { x: 196, y: 64, dir: 'up' }, { x: 226, y: 64, dir: 'up' }, { x: 168, y: 66, dir: 'up' }, { x: 252, y: 66, dir: 'up' },
  ],
  kaffe: [
    { x: 194, y: 264, dir: 'up' }, { x: 222, y: 264, dir: 'up' },
  ],
  dorr: [{ x: 138, y: 56, dir: 'down' }],
}

// Vad på skärmen i hörnet visar: terminalen i arkivet där journalen från 1177 slås upp.
export const TERMINAL = { x: 82, y: 96, w: 36 }

// Hinder för fötterna (x, y, w, h).
const OBSTACLES: [number, number, number, number][] = [
  [0, 0, MAP_W, 52],                 // bakvägg
  [0, 0, 8, MAP_H], [MAP_W - 8, 0, 8, MAP_H], [0, MAP_H - 10, MAP_W, 10],
  [8, 44, 104, 16],                  // bokhyllor
  [TERMINAL.x - 2, 96, TERMINAL.w + 4, 22],
  [8, 102, 22, 30],                  // arkivskåp
  [298, 44, 112, 30],                // labbänk och kyl
  [TABLE.x - 2, TABLE.y + 2, TABLE.w + 4, TABLE.h + 8],
  [178, 222, 62, 30],                // kaffehörna
  [124, 144, 14, 10], [282, 144, 14, 10], // stora växter
  [10, 270, 12, 10], [396, 270, 12, 10], [112, 62, 12, 10], [286, 88, 12, 10],
]
for (const d of DESKS) OBSTACLES.push([d.x - 2, d.y - 2, DESK_W + 4, 26])

export const CELL = 8
export const GW = MAP_W / CELL
export const GH = MAP_H / CELL

export function buildGrid(): Uint8Array {
  const g = new Uint8Array(GW * GH)
  for (let gy = 0; gy < GH; gy++)
    for (let gx = 0; gx < GW; gx++) {
      const cx = gx * CELL + CELL / 2, cy = gy * CELL + CELL / 2
      for (const [x, y, w, h] of OBSTACLES) {
        if (cx > x - 3 && cx < x + w + 3 && cy > y - 3 && cy < y + h + 3) { g[gy * GW + gx] = 1; break }
      }
    }
  return g
}

// ---------------------------------------------------------------- statisk bakgrund

export function drawBackground(): HTMLCanvasElement {
  const [cv, c] = canvas(MAP_W, MAP_H)
  const r = rng(7)

  // trägolv: plankor 6 px höga med förskjutna skarvar
  rect(c, 0, WALL, MAP_W, MAP_H - WALL, C.wood)
  for (let y = WALL, row = 0; y < MAP_H; y += 6, row++) {
    rect(c, 0, y, MAP_W, 1, C.woodLine)
    let x = -((row * 37) % 48)
    while (x < MAP_W) {
      const len = 34 + Math.floor(r() * 30)
      const tone = r()
      if (tone > 0.7) rect(c, x + 1, y + 1, len - 1, 5, C.woodHi)
      else if (tone < 0.18) rect(c, x + 1, y + 1, len - 1, 5, shade(C.wood, -0.05))
      rect(c, x, y + 1, 1, 5, C.woodLine)
      x += len
    }
  }

  // arkivets matta
  rect(c, 4, WALL, 120, 108, C.carpet)
  for (let y = WALL + 3; y < WALL + 106; y += 4) for (let x = 6 + ((y / 4) % 2) * 2; x < 122; x += 4) rect(c, x, y, 1, 1, C.carpetDot)
  rect(c, 4, WALL + 107, 120, 1, shade(C.carpet, -0.25))
  rect(c, 123, WALL, 1, 108, shade(C.carpet, -0.25))

  // labbets kakel
  for (let y = WALL; y < WALL + 108; y += 8)
    for (let x = 296; x < 412; x += 8) {
      rect(c, x, y, 8, 8, ((x + y) / 8) % 2 ? C.tile : C.tile2)
      rect(c, x, y, 8, 1, C.tileLine); rect(c, x, y, 1, 8, C.tileLine)
    }
  rect(c, 296, WALL + 107, 116, 1, shade(C.tileLine, -0.2))
  rect(c, 296, WALL, 1, 108, shade(C.tileLine, -0.2))

  // matta under konferensbordet
  rect(c, 128, 76, 160, 80, C.rugBorder)
  rect(c, 131, 79, 154, 74, C.rug)
  for (let x = 134; x < 283; x += 6) { rect(c, x, 81, 3, 1, C.rugLine); rect(c, x, 150, 3, 1, C.rugLine) }
  rect(c, 134, 84, 148, 1, C.rugLine); rect(c, 134, 147, 148, 1, C.rugLine)

  // bakväggen, tre avsnitt
  rect(c, 0, 0, MAP_W, 4, C.cap)
  rect(c, 4, 4, 120, WALL - 8, C.archWall)
  rect(c, 124, 4, 172, WALL - 8, C.wall)
  for (let x = 128; x < 296; x += 24) rect(c, x, 4, 1, WALL - 8, C.wallLo)
  rect(c, 124, 4, 172, 2, C.wallHi)
  // labbet: kakel på väggen
  rect(c, 296, 4, 116, WALL - 8, C.labWall)
  for (let y = 8; y < WALL - 4; y += 6) rect(c, 296, y, 116, 1, C.labWallLine)
  for (let y = 4, row = 0; y < WALL - 4; y += 6, row++) for (let x = 296 + (row % 2) * 6; x < 412; x += 12) rect(c, x, y, 1, 6, C.labWallLine)
  rect(c, 4, WALL - 4, MAP_W - 8, 4, C.base)
  rect(c, 4, WALL, MAP_W - 8, 2, 'rgba(20,16,24,0.25)')

  // sidoväggar och nederkant
  rect(c, 0, 0, 4, MAP_H, C.cap)
  rect(c, MAP_W - 4, 0, 4, MAP_H, C.cap)
  rect(c, 0, MAP_H - 4, MAP_W, 4, C.cap)
  rect(c, 4, WALL, 2, MAP_H - WALL - 4, 'rgba(20,16,24,0.18)')

  // dörr till vänster om skärmväggen
  rect(c, 129, 9, 18, 35, C.cap)
  rect(c, 130, 10, 16, 34, '#6a5643')
  rect(c, 132, 12, 12, 13, '#7a6450'); rect(c, 132, 27, 12, 15, '#7a6450')
  rect(c, 142, 27, 2, 2, '#d0c08a')

  // skärmväggens ram (innehållet ritas varje bildruta)
  rect(c, 152, 7, 114, 33, C.cap)
  rect(c, 154, 9, 110, 29, C.screenOff)
  rect(c, 205, 40, 8, 2, C.metalDark)
  // liten statusskärm
  rect(c, 270, 11, 22, 25, C.cap)
  rect(c, 271, 12, 20, 23, C.screenOff)

  return cv
}

// ---------------------------------------------------------------- möbler

function shadowRect(c: Ctx, x: number, y: number, w: number, h: number) {
  c.fillStyle = C.shadow
  c.fillRect(x, y, w, h)
}

function bookcase(c: Ctx, x: number, w: number, seed: number) {
  const r = rng(seed)
  const top = 8, bottom = 58
  shadowRect(c, x + 1, bottom, w, 3)
  rect(c, x, top, w, bottom - top, '#5b4433')
  rect(c, x, top, w, 3, '#6f5541')
  rect(c, x + 2, top + 3, w - 4, bottom - top - 5, '#3c2d23')
  const binders = ['#a5523c', '#3f7f7a', '#c79a45', '#506a86', '#6f8b5a', '#d9d1bd', '#8a4a4a', '#3d5b70']
  for (let s = 0; s < 4; s++) {
    const sy = top + 4 + s * 12
    let bx = x + 3
    while (bx < x + w - 4) {
      const bw = 2 + Math.floor(r() * 3)
      if (bx + bw > x + w - 3) break
      const bh = 8 + Math.floor(r() * 3)
      const col = binders[Math.floor(r() * binders.length)]
      if (r() > 0.1) {
        rect(c, bx, sy + 10 - bh, bw, bh, col)
        rect(c, bx, sy + 10 - bh, 1, bh, shade(col, 0.15))
        if (bw > 2) rect(c, bx + 1, sy + 10 - bh + 2, bw - 2, 1, shade(col, 0.35))
      }
      bx += bw + (r() > 0.85 ? 2 : 0)
    }
    rect(c, x + 2, sy + 10, w - 4, 2, '#6f5541')
  }
}

function plant(c: Ctx, x: number, y: number, big = false) {
  // x,y = krukans nederkant mitt
  const pw = big ? 12 : 8
  shadowRect(c, x - pw / 2, y, pw + 2, 2)
  rect(c, x - pw / 2, y - 8, pw, 8, C.pot)
  rect(c, x - pw / 2, y - 8, pw, 2, shade(C.pot, 0.15))
  rect(c, x - pw / 2 + pw - 2, y - 6, 2, 6, C.potDark)
  const leaves = big
    ? [[-7, -22, 5, 9], [2, -24, 5, 10], [-3, -28, 6, 10], [-9, -14, 6, 6], [4, -15, 6, 6], [-2, -18, 5, 8]]
    : [[-5, -16, 4, 7], [1, -17, 4, 8], [-2, -20, 4, 8], [-6, -11, 4, 4], [2, -11, 4, 4]]
  for (const [lx, ly, lw, lh] of leaves) {
    rect(c, x + lx, y + ly, lw, lh, C.leaf)
    rect(c, x + lx, y + ly, lw - 1, 2, C.leafHi)
    rect(c, x + lx + lw - 1, y + ly + 2, 1, lh - 2, C.leafDark)
  }
}

function desk(c: Ctx, d: { id: string; x: number; y: number }, accent: string) {
  const { x, y } = d
  shadowRect(c, x + 2, y + 22, DESK_W, 3)
  // skiva
  rect(c, x, y, DESK_W, 14, C.desk)
  rect(c, x, y, DESK_W, 1, C.deskHi)
  rect(c, x, y + 13, DESK_W, 1, C.deskDark)
  // front
  rect(c, x, y + 14, DESK_W, 8, C.deskFace)
  rect(c, x + 2, y + 16, 12, 4, C.deskDark)  // låda
  rect(c, x + 6, y + 17, 4, 1, '#c7b27a')
  // namnskylt i agentens färg
  rect(c, x + 28, y + 16, 12, 4, accent)
  rect(c, x + 29, y + 17, 10, 1, shade(accent, 0.35))
  // tangentbord och mus
  rect(c, x + 13, y + 9, 16, 3, '#2c3236')
  rect(c, x + 14, y + 9, 14, 1, '#4a5258')
  rect(c, x + 32, y + 9, 3, 3, '#2c3236')
  // pappershög eller mugg beroende på bord
  const r = rng(d.x * 7 + d.y)
  if (r() > 0.4) { rect(c, x + 3, y + 4, 8, 6, C.paper); rect(c, x + 4, y + 3, 8, 6, C.paper); rect(c, x + 5, y + 5, 5, 1, C.paperLine); rect(c, x + 5, y + 7, 4, 1, C.paperLine) }
  else { rect(c, x + 4, y + 3, 5, 6, '#e6e1d4'); rect(c, x + 4, y + 3, 5, 1, '#3a2a20'); rect(c, x + 9, y + 5, 1, 2, '#e6e1d4') }
  if (r() > 0.5) { rect(c, x + 37, y + 3, 4, 4, C.pot); rect(c, x + 36, y - 1, 6, 4, C.leaf); rect(c, x + 37, y - 2, 3, 2, C.leafHi) }
  // skärmfot
  rect(c, x + 20, y + 3, 4, 4, C.metalDark)
  rect(c, x + 17, y + 6, 10, 2, C.metal)
}

/** Skärmen på skrivbordet (dynamisk, ritas varje bildruta). */
export function deskMonitor(c: Ctx, d: { x: number; y: number }, content: (c: Ctx, x: number, y: number, w: number, h: number) => void) {
  const mx = d.x + 10, my = d.y - 12
  rect(c, mx, my, 24, 16, C.metalDark)
  rect(c, mx + 1, my + 1, 22, 13, C.screenOff)
  content(c, mx + 1, my + 1, 22, 13)
  rect(c, mx, my + 15, 24, 1, C.metal)
}

function deskChair(c: Ctx, x: number, footY: number) {
  // ryggstöd framför en sittande figur som vänder ryggen mot oss
  const top = footY - 9
  rect(c, x - 6, top, 12, 8, C.chair)
  rect(c, x - 6, top, 12, 1, C.chairHi)
  rect(c, x - 5, top + 7, 10, 1, C.chairDark)
  rect(c, x - 1, top + 8, 2, 3, C.metalDark)
  rect(c, x - 5, top + 11, 10, 1, C.metalDark)
}

function tableChairBack(c: Ctx, s: Spot) {
  if (s.dir === 'down') {
    // ryggstöd bakom figuren
    rect(c, s.x - 6, s.y - 20, 12, 10, C.chair)
    rect(c, s.x - 6, s.y - 20, 12, 1, C.chairHi)
    rect(c, s.x - 6, s.y - 11, 12, 2, C.chairDark)
  } else if (s.dir === 'left' || s.dir === 'right') {
    const bx = s.dir === 'right' ? s.x - 7 : s.x + 5
    rect(c, bx, s.y - 18, 3, 13, C.chair)
    rect(c, bx, s.y - 18, 3, 1, C.chairHi)
    rect(c, s.x - 5, s.y - 6, 10, 3, C.chairDark)
    rect(c, s.x - 1, s.y - 3, 2, 3, C.metalDark)
  }
}
function tableChairFront(c: Ctx, s: Spot) {
  // ryggstöd framför figuren (nedre raden)
  rect(c, s.x - 6, s.y - 9, 12, 8, C.chair)
  rect(c, s.x - 6, s.y - 9, 12, 1, C.chairHi)
  rect(c, s.x - 5, s.y - 2, 10, 1, C.chairDark)
  rect(c, s.x - 1, s.y - 1, 2, 3, C.metalDark)
}

function table(c: Ctx) {
  const { x, y, w, h } = TABLE
  shadowRect(c, x + 3, y + h + 7, w, 4)
  rect(c, x + 1, y, w - 2, h, '#8e6a49')
  rect(c, x, y + 1, w, h - 2, '#8e6a49')
  rect(c, x + 2, y + 1, w - 4, 1, '#a07a56')
  for (let i = 0; i < 5; i++) rect(c, x + 6 + i * 22, y + 4 + (i % 2) * 10, 14, 1, '#86634a')
  rect(c, x, y + h - 1, w, 1, '#6c4f36')
  // front
  rect(c, x + 1, y + h, w - 2, 7, '#6f5139')
  rect(c, x + 1, y + h, w - 2, 1, '#5b412e')
  rect(c, x + 4, y + h + 7, 3, 4, '#4d3828'); rect(c, x + w - 7, y + h + 7, 3, 4, '#4d3828')
  // på bordet: papper, karaff, muggar
  rect(c, x + 20, y + 8, 9, 7, C.paper); rect(c, x + 22, y + 10, 5, 1, C.paperLine); rect(c, x + 22, y + 12, 4, 1, C.paperLine)
  rect(c, x + 82, y + 14, 8, 6, C.paper); rect(c, x + 83, y + 16, 5, 1, C.paperLine)
  rect(c, x + 53, y + 6, 5, 9, '#a9cfd6'); rect(c, x + 54, y + 7, 3, 7, '#c6e3e8'); rect(c, x + 54, y + 5, 3, 2, '#7da6ae')
  rect(c, x + 61, y + 11, 3, 4, '#e6e1d4'); rect(c, x + 47, y + 13, 3, 4, '#e6e1d4')
  rect(c, x + 36, y + 17, 10, 6, '#2c3236'); rect(c, x + 37, y + 17, 8, 4, '#3f6a70') // surfplatta
}

function terminal(c: Ctx) {
  const { x, y, w } = TERMINAL
  shadowRect(c, x + 2, y + 20, w, 3)
  rect(c, x, y + 4, w, 10, C.desk); rect(c, x, y + 4, w, 1, C.deskHi)
  rect(c, x, y + 14, w, 6, C.deskFace)
  rect(c, x + 8, y - 12, 20, 15, C.metalDark)
  rect(c, x + 9, y - 11, 18, 12, '#1d3a52')
  rect(c, x + 16, y + 3, 4, 2, C.metal)
}
export function terminalScreen(c: Ctx, active: number, t: number) {
  const { x, y } = TERMINAL
  const sx = x + 9, sy = y - 11
  rect(c, sx, sy, 18, 12, active ? '#1f4a6b' : '#1d3a52')
  rect(c, sx + 1, sy + 1, 16, 2, '#3c7db0')
  for (let i = 0; i < 4; i++) {
    const wv = active ? 6 + ((i * 5 + Math.floor(t * 4)) % 9) : 6 + ((i * 5) % 9)
    rect(c, sx + 2, sy + 4 + i * 2, wv, 1, active ? '#a9cbe6' : '#5c88aa')
  }
}

function cabinet(c: Ctx) {
  shadowRect(c, 10, 132, 22, 3)
  rect(c, 8, 98, 22, 34, '#6d7b80')
  rect(c, 8, 98, 22, 4, '#87959a')
  for (let i = 0; i < 3; i++) {
    rect(c, 10, 104 + i * 9, 18, 8, '#5f6c71')
    rect(c, 16, 107 + i * 9, 6, 2, '#b8c2c5')
  }
}

function labBench(c: Ctx) {
  shadowRect(c, 300, 74, 92, 3)
  rect(c, 298, 50, 94, 10, '#d8dedd'); rect(c, 298, 50, 94, 1, '#eef2f1')
  rect(c, 298, 60, 94, 14, '#7f9a98')
  for (let i = 0; i < 4; i++) { rect(c, 301 + i * 23, 62, 20, 10, '#6f8a88'); rect(c, 309 + i * 23, 66, 5, 1, '#c7d2d1') }
  // mikroskop
  rect(c, 304, 46, 10, 4, '#2f3a40'); rect(c, 308, 34, 3, 13, '#3d4a52'); rect(c, 306, 32, 6, 4, '#2f3a40'); rect(c, 311, 40, 3, 2, '#9bb');
  // centrifug
  rect(c, 322, 42, 16, 9, '#e8ecec'); rect(c, 322, 42, 16, 2, '#ffffff'); rect(c, 325, 45, 10, 3, '#b6c2c4'); rect(c, 334, 48, 2, 1, '#4cc38a')
  // provrörsställ
  rect(c, 344, 46, 18, 5, '#6a7a80')
  const tubes = ['#c9473c', '#d9b24a', '#5b8fc0', '#c9473c', '#6faa6a', '#d9b24a']
  tubes.forEach((col, i) => { rect(c, 345 + i * 3, 38, 2, 9, '#e9f1f2'); rect(c, 345 + i * 3, 42, 2, 5, col) })
  // analysator med skärm (innehåll ritas dynamiskt)
  rect(c, 366, 30, 22, 21, '#e1e6e5'); rect(c, 366, 30, 22, 2, '#f5f8f7'); rect(c, 368, 33, 18, 10, '#1d2629')
  rect(c, 369, 45, 4, 3, '#9aa6a8'); rect(c, 375, 45, 4, 3, '#9aa6a8')
}
export function analyzerScreen(c: Ctx, active: number, t: number) {
  rect(c, 368, 33, 18, 10, active ? '#203a33' : '#1d2629')
  const n = active ? 6 : 3
  for (let i = 0; i < n; i++) {
    const h = active ? 1 + ((i * 7 + Math.floor(t * 6)) % 7) : 1 + ((i * 3) % 4)
    rect(c, 369 + i * 3, 42 - h, 2, h, active ? '#4cc38a' : '#35554b')
  }
}

function fridge(c: Ctx) {
  shadowRect(c, 394, 74, 16, 3)
  rect(c, 392, 18, 18, 56, '#e5eae9'); rect(c, 392, 18, 18, 2, '#ffffff')
  rect(c, 392, 40, 18, 1, '#b9c2c1'); rect(c, 406, 26, 2, 8, '#9aa6a8'); rect(c, 406, 46, 2, 10, '#9aa6a8')
  rect(c, 395, 22, 8, 5, '#5b8fc0') // etikett
}

function coffee(c: Ctx) {
  shadowRect(c, 180, 252, 60, 3)
  rect(c, 178, 226, 62, 10, '#b9bfc0'); rect(c, 178, 226, 62, 1, '#d6dbdb')
  rect(c, 178, 236, 62, 16, '#5b6a70'); rect(c, 180, 238, 28, 12, '#51606a'); rect(c, 210, 238, 28, 12, '#51606a')
  rect(c, 192, 243, 4, 1, '#aab'); rect(c, 222, 243, 4, 1, '#aab')
  // kaffemaskin
  rect(c, 184, 210, 14, 18, '#2e3438'); rect(c, 184, 210, 14, 2, '#454d52'); rect(c, 187, 214, 8, 4, '#1a1e21'); rect(c, 189, 215, 2, 1, '#d9a03f')
  rect(c, 188, 222, 6, 4, '#1a1e21'); rect(c, 189, 223, 4, 3, '#e6e1d4')
  // muggar
  rect(c, 202, 222, 3, 4, '#e6e1d4'); rect(c, 206, 222, 3, 4, '#c9473c')
  // vattenautomat
  rect(c, 222, 196, 10, 12, '#9fd0e6'); rect(c, 223, 197, 8, 10, '#bfe0ee'); rect(c, 221, 207, 12, 21, '#d6dbdb'); rect(c, 223, 214, 3, 2, '#5b8fc0')
}

export function staticDrawables(accentFor: (id: string) => string): Drawable[] {
  const list: Drawable[] = []
  list.push({ depth: 58, draw: (c) => { bookcase(c, 8, 50, 3); bookcase(c, 60, 52, 11) } })
  list.push({ depth: 116, draw: terminal })
  list.push({ depth: 132, draw: cabinet })
  list.push({ depth: 74, draw: (c) => { labBench(c); fridge(c) } })
  list.push({ depth: TABLE.y + TABLE.h + 7, draw: table })
  list.push({ depth: 252, draw: coffee })
  for (const [x, y, big] of [[130, 154, true], [289, 154, true], [16, 280, false], [402, 280, false], [118, 70, false], [292, 96, false]] as const)
    list.push({ depth: y, draw: (c) => plant(c, x, y, big) })
  DESKS.forEach((d, i) => {
    list.push({ depth: d.y + 22, draw: (c) => desk(c, d, accentFor(d.id)) })
    const s = deskSeat(i)
    list.push({ depth: s.y + 0.5, draw: (c) => deskChair(c, s.x, s.y) })
  })
  for (const s of TABLE_SEATS) {
    if (s.dir === 'up') list.push({ depth: s.y + 0.5, draw: (c) => tableChairFront(c, s) })
    else list.push({ depth: s.y - 0.5, draw: (c) => tableChairBack(c, s) })
  }
  return list
}

export const PALETTE = C
