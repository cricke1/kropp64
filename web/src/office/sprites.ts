// Figurerna i kontoret. Ritas pixel för pixel ur mallar, får automatisk kontur och cachas per pose.
// En figur är 16x24 px. Fötterna står på rad 22.

import type { Look } from '../agents'
import { canvas, outline, paint, shade, type Ctx } from './pixel'

export type Dir = 'down' | 'up' | 'right' | 'left'
export interface PoseOpts {
  dir: Dir
  pose: 'stand' | 'walk' | 'sit'
  frame: number        // 0..3 för gång
  blink?: boolean
  mouth?: boolean      // munnen öppen (pratar)
  busy?: number        // 0/1, armrörelse vid skrivbordet
  hold?: boolean       // håller ett papper
  pen?: boolean        // röd penna (granskaren)
  penUp?: boolean
}

export const SPRITE_W = 16
export const SPRITE_H = 24
export const FOOT_Y = 22

const OUTLINE = '#1b1820'
const EYE = '#231c26'

// ---------------------------------------------------------------- mallar

const HEAD_DOWN = [
  '....SSSSSSSS....',
  '...SSSSSSSSSS...',
  '...SSSSSSSSSS...',
  '...SSSSSSSSSS...',
  '...SSESSSSESS...',
  '...SSSSSSSSSS...',
  '...sSSSMMSSSs...',
  '....ssssssss....',
]
const HEAD_UP = [
  '....SSSSSSSS....',
  '...SSSSSSSSSS...',
  '...SSSSSSSSSS...',
  '...SSSSSSSSSS...',
  '...SSSSSSSSSS...',
  '...SSSSSSSSSS...',
  '...sSSSSSSSSs...',
  '....ssssssss....',
]
const HEAD_RIGHT = [
  '.....SSSSSS.....',
  '....SSSSSSSS....',
  '....SSSSSSSS....',
  '....SSSSSSSSS...',
  '....SSSSSSESS...',
  '....SSSSSSSSS...',
  '....sSSSSSSMs...',
  '.....sssssss....',
]

const BODY_DOWN = [
  '....CCTTTTCC....',
  '...CCCcTTcCCC...',
  '...CcCCTTCCcC...',
  '...CcCCTTCCcC...',
  '...CcCCCCCCcC...',
  '...CcCCCCCCcC...',
  '...SccCCCCccS...',
  '....cCCCCCCc....',
  '....cCCccCCc....',
]
const BODY_UP = [
  '....CCCCCCCC....',
  '...CCCCCCCCCC...',
  '...CcCCCCCCcC...',
  '...CcCCCCCCcC...',
  '...CcCCCCCCcC...',
  '...CcCCCCCCcC...',
  '...SccCCCCccS...',
  '....cCCCCCCc....',
  '....cCCccCCc....',
]
const BODY_RIGHT = [
  '.....CCCCTT.....',
  '.....CCCCCT.....',
  '.....CCCCCC.....',
  '.....CCCCCC.....',
  '.....CCCCCC.....',
  '.....CCCCCC.....',
  '.....cCCCCc.....',
  '.....cCCCCc.....',
  '.....cCCCCc.....',
]

type HairSet = { down: string[]; up: string[]; right: string[] }
// Rad 0 i mallarna motsvarar rad 0 i figuren.
const HAIR: Record<Look['hairStyle'], HairSet> = {
  short: {
    down: ['', '', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHhHHHHHhHH..'.slice(0, 16), '...H........H...'],
    up: ['', '', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHhhHHHH...', '...HHHHHHHHHH...', '...hHHHHHHHHh...', '...hhHHHHHHhh...'],
    right: ['', '', '.....HHHHHH.....', '....HHHHHHHH....', '....HHHHHHHHH...', '....HHHH........', '....HHH.........', '....HH..........'],
  },
  side: {
    down: ['', '', '....HHHHHHHH....', '...HHHHHhHHHH...', '...HHHHHH.HHH...', '...H........H...', '...H........H...'],
    up: ['', '', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...hHHHHHHHHh...', '...hhHHHHHHhh...'],
    right: ['', '', '.....HHHHHH.....', '....HHHHHHHH....', '....HHHHHHH.H...', '....HHHHH.......', '....HHHH........', '....HHH.........'],
  },
  bob: {
    down: ['', '.....HHHHHH.....', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HH......HH...', '...H........H...', '...H........H...', '..HHh......hHH..', '..Hh........hH..'],
    up: ['', '.....HHHHHH.....', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '..HHHHHHHHHHHH..', '..hHHHHHHHHHHh..'],
    right: ['', '.....HHHHHH.....', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHH.......', '...HHHHH........', '...HHHHH........', '...HHHHh........', '...hHHh.........'],
  },
  bun: {
    down: ['......HHHH......', '.....HhhhhH.....', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...H........H...', '...H........H...'],
    up: ['......HHHH......', '.....HHhhHH.....', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...hHHHHHHHHh...', '...hhHHHHHHhh...'],
    right: ['....HHH.........', '...HHhhH........', '...HHHHHHHH.....', '....HHHHHHHH....', '....HHHHHHHHH...', '....HHHH........', '....HHH.........', '....HH..........'],
  },
  long: {
    down: ['', '.....HHHHHH.....', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HH......HH...', '...H........H...', '..HH........HH..', '..HH........HH..', '..HH........HH..', '..Hh........hH..', '..hh........hh..', '...h........h...'],
    up: ['', '.....HHHHHH.....', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '..HHHHHHHHHHHH..', '..HHHHHHHHHHHH..', '..HHHHHHHHHHHH..', '...HHHHHHHHHH...', '...hHHHHHHHHh...', '....hHHHHHHh....'],
    right: ['', '.....HHHHHH.....', '....HHHHHHHH....', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...HHHHHH.......', '...HHHHH........', '...HHHHH........', '...HHHHH........', '...HHHHh........', '...HHHh.........', '...hHh..........', '....h...........'],
  },
  curly: {
    down: ['', '....HH.HH.HH....', '...HHHHHHHHHH...', '..HHHHHHHHHHHH..', '..HHhHHhHHhHHH..', '..HH........HH..', '..H..........H..', '..h..........h..'],
    up: ['', '....HH.HH.HH....', '...HHHHHHHHHH...', '..HHHHHHHHHHHH..', '..HHhHHhHHhHHH..', '..HHHHHHHHHHHH..', '..HhHHhHHhHHhH..', '..HHHHHHHHHHHH..', '...hHHHHHHHHh...'],
    right: ['', '....HH.HH.H.....', '...HHHHHHHHH....', '..HHHHHHHHHHH...', '..HHhHHhHHhHH...', '..HHHHHH........', '..HhHHH.........', '..HHHH..........', '...hh...........'],
  },
  bald: {
    down: ['', '', '', '', '', '...H........H...', '...H........H...', '...h........h...'],
    up: ['', '', '', '', '', '...HHHHHHHHHH...', '...HHHHHHHHHH...', '...hHHHHHHHHh...', '....hHHHHHHh....'],
    right: ['', '', '', '', '', '....HHH.........', '....HHH.........', '....hh..........'],
  },
}

// ---------------------------------------------------------------- byggare

function legs(c: Ctx, dir: Dir, frame: number, pal: Record<string, string>, y0: number) {
  const P = pal.P, p = pal.p, B = pal.B
  const px = (x: number, y: number, col: string) => { c.fillStyle = col; c.fillRect(x, y0 + y, 1, 1) }
  if (dir === 'down' || dir === 'up') {
    // vänster ben x 5-6, höger 9-10. Vid gång lyfts ett ben en pixel.
    const liftL = frame === 1 ? 1 : 0
    const liftR = frame === 3 ? 1 : 0
    for (let y = 0; y < 2 - liftL; y++) { px(5, y, P); px(6, y, p) }
    px(5, 2 - liftL, B); px(6, 2 - liftL, B)
    for (let y = 0; y < 2 - liftR; y++) { px(9, y, p); px(10, y, P) }
    px(9, 2 - liftR, B); px(10, 2 - liftR, B)
  } else {
    // sidovy: ben isär vid gång
    const spread = frame === 1 ? 2 : frame === 3 ? -2 : 0
    const back = 7 - Math.max(0, spread) + Math.max(0, -spread) * 0
    const front = 8 + Math.max(0, spread)
    if (spread === 0) {
      for (let y = 0; y < 2; y++) { px(7, y, p); px(8, y, P) }
      px(7, 2, B); px(8, 2, B); px(9, 2, B)
    } else {
      const bx = spread > 0 ? 6 : 9, fx = spread > 0 ? 9 : 6
      for (let y = 0; y < 2; y++) { px(bx, y, p); px(fx, y, P) }
      px(7, 0, P); px(8, 0, P)
      px(bx, 2, B); px(bx + 1, 2, B); px(fx, 2, B); px(fx + 1, 2, B)
      void back; void front
    }
  }
}

function sideArm(c: Ctx, frame: number, pal: Record<string, string>, y0: number, opts: PoseOpts) {
  const swing = opts.pose === 'walk' ? (frame === 1 ? 1 : frame === 3 ? -1 : 0) : 0
  const x = 7 + swing
  c.fillStyle = pal.c
  for (let y = 1; y < 6; y++) c.fillRect(y > 3 ? x + swing * 0 : 7, y0 + y, 2, 1)
  if (opts.pose === 'sit') {
    c.fillStyle = pal.c; c.fillRect(8, y0 + 4, 3, 1)
    c.fillStyle = pal.S; c.fillRect(11, y0 + 4, 1, 1)
  } else {
    c.fillStyle = pal.c; c.fillRect(x, y0 + 4, 2, 2)
    c.fillStyle = pal.S; c.fillRect(x, y0 + 6, 2, 1)
  }
}

const cache = new Map<string, HTMLCanvasElement>()

export function sprite(look: Look, o: PoseOpts): HTMLCanvasElement {
  const key = [look.skin, look.hair, look.hairStyle, look.coat, look.shirt, look.pants, look.glasses, look.beard, look.stethoscope,
    o.dir, o.pose, o.pose === 'walk' ? o.frame : 0, o.blink, o.mouth, o.busy, o.hold, o.pen, o.penUp].join('|')
  const hit = cache.get(key)
  if (hit) return hit
  const [cv, c] = canvas(SPRITE_W, SPRITE_H)
  const flip = o.dir === 'left'
  const d: 'down' | 'up' | 'right' = o.dir === 'left' ? 'right' : o.dir
  const pal: Record<string, string> = {
    S: look.skin, s: shade(look.skin, -0.14),
    H: look.hair, h: isDark(look.hair) ? shade(look.hair, 0.22) : shade(look.hair, -0.22),
    C: look.coat, c: shade(look.coat, isLight(look.coat) ? -0.16 : -0.22),
    T: look.shirt, P: look.pants, p: shade(look.pants, -0.25), B: '#2a2524',
    E: o.blink ? shade(look.skin, -0.2) : EYE,
    M: o.mouth ? '#7a3434' : shade(look.skin, -0.18),
  }

  const sitDrop = o.pose === 'sit' ? 2 : 0
  const bob = o.pose === 'walk' && (o.frame === 1 || o.frame === 3) ? -1 : 0
  const headY = 2 + sitDrop + bob + (o.busy ? 1 : 0) * (d === 'up' ? 1 : 0)
  const bodyY = 10 + sitDrop + bob

  // ben
  if (o.pose !== 'sit') legs(c, d, o.pose === 'walk' ? o.frame : 0, pal, 19 + bob)
  else if (d === 'right') {
    c.fillStyle = pal.P; c.fillRect(8, bodyY + 8, 4, 2)
    c.fillStyle = pal.p; c.fillRect(11, bodyY + 10, 1, 1)
    c.fillStyle = pal.B; c.fillRect(11, bodyY + 11, 2, 1)
  }

  // kropp
  const body = d === 'down' ? BODY_DOWN : d === 'up' ? BODY_UP : BODY_RIGHT
  const bodyRows = o.pose === 'sit' && d !== 'right' ? body.slice(0, 8) : body
  // armrörelse vid skrivbordet: händerna försvinner fram mot tangentbordet
  let rows = bodyRows
  if (o.pose === 'sit' && d === 'up') {
    rows = bodyRows.map((r, i) => (i === 6 ? (o.busy ? '...cccCCCCcccC..'.slice(0, 16) : '...cccCCCCccc...') : r))
  }
  if (o.pose === 'sit' && d === 'down') {
    rows = bodyRows.map((r, i) => (i === 6 ? '...cSSCCCCSSc...' : r))
  }
  if (o.pose === 'walk' && d !== 'right') {
    // armpendling: händerna växelvis en rad upp
    rows = bodyRows.map((r, i) => {
      if (i === 6) return o.frame === 1 ? '...cccCCCCccS...' : o.frame === 3 ? '...SccCCCCccc...' : r
      if (i === 5) return o.frame === 1 ? '...SccCCCCccC...' : o.frame === 3 ? '...CccCCCCccS...' : r
      return r
    })
  }
  paint(c, rows, 0, bodyY, pal)
  if (d === 'right') sideArm(c, o.frame, pal, bodyY, o)

  // huvud
  const head = d === 'down' ? HEAD_DOWN : d === 'up' ? HEAD_UP : HEAD_RIGHT
  paint(c, head, 0, headY, pal)
  // hår (mallens rad 0 = huvudets rad -2)
  const hair = HAIR[look.hairStyle][d]
  paint(c, hair, 0, headY - 2, pal)

  if (look.beard && d !== 'up') {
    const b = d === 'down'
      ? ['', '', '', '', '', '', '...hH......Hh...', '....HHHHHHHH....', '.....hhhhhh.....']
      : ['', '', '', '', '', '', '....hHHHHHH.....', '.....HHHHHHH....', '......hhhh......']
    paint(c, b.map((r) => r.slice(0, 16)), 0, headY - 2 + 2, { ...pal, H: pal.H, h: pal.h })
    // munnen ska synas genom skägget
    c.fillStyle = pal.M
    if (d === 'down') c.fillRect(7, headY + 6, 2, 1)
    else c.fillRect(11, headY + 6, 1, 1)
  }
  if (look.glasses && d !== 'up') {
    c.fillStyle = '#3a3f46'
    if (d === 'down') {
      for (const x of [4, 6, 9, 11]) c.fillRect(x, headY + 4, 1, 1)
      c.fillRect(7, headY + 4, 2, 1)
      c.fillStyle = '#9fd0e6'; c.fillRect(4, headY + 3, 3, 1); c.fillRect(9, headY + 3, 3, 1)
    } else {
      c.fillRect(9, headY + 4, 1, 1); c.fillRect(11, headY + 4, 1, 1); c.fillRect(6, headY + 4, 3, 1)
      c.fillStyle = '#9fd0e6'; c.fillRect(9, headY + 3, 3, 1)
    }
  }
  if (look.stethoscope && d === 'down') {
    c.fillStyle = '#3b4148'
    for (const [x, y] of [[5, 0], [5, 1], [6, 2], [6, 3], [10, 0], [10, 1], [9, 2], [9, 3], [7, 4], [8, 4]]) c.fillRect(x, bodyY + y, 1, 1)
    c.fillStyle = '#c9d1d6'; c.fillRect(8, bodyY + 5, 1, 1)
  }
  if (look.stethoscope && d === 'right') {
    c.fillStyle = '#3b4148'; c.fillRect(9, bodyY, 1, 3); c.fillStyle = '#c9d1d6'; c.fillRect(9, bodyY + 3, 1, 1)
  }

  if (o.hold) {
    const hx = d === 'right' ? 10 : 11, hy = bodyY + 4
    c.fillStyle = '#f4f1e8'; c.fillRect(hx, hy, 4, 5)
    c.fillStyle = '#b9b4a6'; c.fillRect(hx + 1, hy + 1, 2, 1); c.fillRect(hx + 1, hy + 3, 2, 1)
  }
  if (o.pen) {
    const up = o.penUp
    const hx = d === 'right' ? 10 : 13, hy = bodyY + (up ? 0 : 5)
    c.fillStyle = '#d23a32'; c.fillRect(hx, hy - 3, 1, 4)
    c.fillStyle = '#f2e9e0'; c.fillRect(hx, hy - 4, 1, 1)
    c.fillStyle = pal.S; c.fillRect(hx - 1, hy, 2, 1)
  }

  outline(c, SPRITE_W, SPRITE_H, OUTLINE)

  if (flip) {
    const [fc, f] = canvas(SPRITE_W, SPRITE_H)
    f.translate(SPRITE_W, 0)
    f.scale(-1, 1)
    f.drawImage(cv, 0, 0)
    cache.set(key, fc)
    return fc
  }
  cache.set(key, cv)
  return cv
}

function lum(h: string) {
  const n = parseInt(h.slice(1), 16)
  return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255
}
const isDark = (h: string) => lum(h) < 0.25
const isLight = (h: string) => lum(h) > 0.8
