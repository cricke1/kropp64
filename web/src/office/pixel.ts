// Små verktyg för pixelgrafik: färger, automatisk kontur och ett 3x5-typsnitt för skärmarna i kontoret.

export type Ctx = CanvasRenderingContext2D

export function rect(c: Ctx, x: number, y: number, w: number, h: number, col: string) {
  c.fillStyle = col
  c.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h))
}

export function canvas(w: number, h: number): [HTMLCanvasElement, Ctx] {
  const cv = document.createElement('canvas')
  cv.width = w
  cv.height = h
  const c = cv.getContext('2d')!
  c.imageSmoothingEnabled = false
  return [cv, c]
}

export function hexToRgb(h: string): [number, number, number] {
  const s = h.replace('#', '')
  const n = parseInt(s.length === 3 ? s.split('').map((x) => x + x).join('') : s, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

export function rgbToHex(r: number, g: number, b: number) {
  const f = (v: number) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')
  return `#${f(r)}${f(g)}${f(b)}`
}

/** Mörkare eller ljusare variant. Skiftar mot varmt i skuggor, så att det inte blir grått och dött. */
export function shade(h: string, amt: number) {
  const [r, g, b] = hexToRgb(h)
  if (amt < 0) {
    const k = 1 + amt
    return rgbToHex(r * k + 6 * -amt, g * k, b * k + 14 * -amt)
  }
  return rgbToHex(r + (255 - r) * amt, g + (255 - g) * amt, b + (255 - b) * amt * 0.9)
}

export function mix(a: string, b: string, t: number) {
  const [r1, g1, b1] = hexToRgb(a)
  const [r2, g2, b2] = hexToRgb(b)
  return rgbToHex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)
}

/** Ritar en mall där varje tecken är en färgnyckel. '.' är genomskinligt. */
export function paint(c: Ctx, rows: string[], ox: number, oy: number, pal: Record<string, string | undefined>, flip = false) {
  for (let y = 0; y < rows.length; y++) {
    const row = rows[y]
    for (let x = 0; x < row.length; x++) {
      const k = row[x]
      if (k === '.' || k === ' ') continue
      const col = pal[k]
      if (!col) continue
      c.fillStyle = col
      c.fillRect(flip ? ox + row.length - 1 - x : ox + x, oy + y, 1, 1)
    }
  }
}

/** Lägger en 1 px kontur runt allt som inte är genomskinligt. */
export function outline(c: Ctx, w: number, h: number, col: string) {
  const img = c.getImageData(0, 0, w, h)
  const d = img.data
  const solid = (x: number, y: number) => x >= 0 && y >= 0 && x < w && y < h && d[(y * w + x) * 4 + 3] > 0
  const [r, g, b] = hexToRgb(col)
  const out: number[] = []
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      if (solid(x, y)) continue
      if (solid(x - 1, y) || solid(x + 1, y) || solid(x, y - 1) || solid(x, y + 1)) out.push(x, y)
    }
  for (let i = 0; i < out.length; i += 2) {
    const o = (out[i + 1] * w + out[i]) * 4
    d[o] = r; d[o + 1] = g; d[o + 2] = b; d[o + 3] = 255
  }
  c.putImageData(img, 0, 0)
}

// 3x5-typsnitt för siffror och några bokstäver på skärmarna.
const GLYPHS: Record<string, string> = {
  '0': '111101101101111', '1': '010110010010111', '2': '111001111100111', '3': '111001111001111',
  '4': '101101111001001', '5': '111100111001111', '6': '111100111101111', '7': '111001010010010',
  '8': '111101111101111', '9': '111101111001111', ':': '000010000010000', '.': '000000000000010',
  '-': '000000111000000', '%': '101001010100101', ' ': '000000000000000', '/': '001001010100100',
  'H': '101101111101101', 'R': '110101110101101', 'V': '101101101101010', 'S': '111100111001111',
  'P': '111101111100100', 'O': '111101101101111', 'Z': '111001010100111', 'h': '100100111101101',
  'm': '000000111111101', 's': '000011010001110', 'D': '110101101101110', 'E': '111100110100111',
  'A': '010101111101101', 'B': '110101110101110', 'T': '111010010010010', 'L': '100100100100111',
  'N': '101111111111101', 'K': '101101110101101', 'U': '101101101101111', 'M': '101111111101101',
  'I': '111010010010111', 'F': '111100110100100', 'G': '111100101101111', 'C': '111100100100111',
}

export function text3(c: Ctx, s: string, x: number, y: number, col: string) {
  c.fillStyle = col
  let cx = x
  for (const ch of s) {
    const g = GLYPHS[ch] ?? GLYPHS[ch.toUpperCase()]
    if (g) for (let i = 0; i < 15; i++) if (g[i] === '1') c.fillRect(cx + (i % 3), y + Math.floor(i / 3), 1, 1)
    cx += 4
  }
  return cx - x
}
