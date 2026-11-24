// A* på ett rutnät med 8 px rutor, följt av utjämning så att figurerna går raka linjer där det går.

import { CELL, GH, GW } from './map'

export type Pt = { x: number; y: number }

export class Pathfinder {
  constructor(private grid: Uint8Array) {}

  blocked(gx: number, gy: number) {
    return gx < 0 || gy < 0 || gx >= GW || gy >= GH || this.grid[gy * GW + gx] === 1
  }

  private nearestFree(gx: number, gy: number): [number, number] {
    if (!this.blocked(gx, gy)) return [gx, gy]
    for (let r = 1; r < 12; r++)
      for (let dy = -r; dy <= r; dy++)
        for (let dx = -r; dx <= r; dx++) {
          if (Math.abs(dx) !== r && Math.abs(dy) !== r) continue
          if (!this.blocked(gx + dx, gy + dy)) return [gx + dx, gy + dy]
        }
    return [gx, gy]
  }

  find(from: Pt, to: Pt): Pt[] {
    const [sx, sy] = this.nearestFree(Math.floor(from.x / CELL), Math.floor(from.y / CELL))
    const [tx, ty] = this.nearestFree(Math.floor(to.x / CELL), Math.floor(to.y / CELL))
    const N = GW * GH
    const g = new Float32Array(N).fill(Infinity)
    const came = new Int32Array(N).fill(-1)
    const closed = new Uint8Array(N)
    const open: number[] = []
    const f = new Float32Array(N).fill(Infinity)
    const h = (i: number) => {
      const dx = Math.abs((i % GW) - tx), dy = Math.abs(Math.floor(i / GW) - ty)
      return dx + dy + (Math.SQRT2 - 2) * Math.min(dx, dy)
    }
    const start = sy * GW + sx, goal = ty * GW + tx
    g[start] = 0; f[start] = h(start); open.push(start)
    while (open.length) {
      let bi = 0
      for (let i = 1; i < open.length; i++) if (f[open[i]] < f[open[bi]]) bi = i
      const cur = open[bi]
      open[bi] = open[open.length - 1]; open.pop()
      if (cur === goal) break
      if (closed[cur]) continue
      closed[cur] = 1
      const cx = cur % GW, cy = Math.floor(cur / GW)
      for (let dy = -1; dy <= 1; dy++)
        for (let dx = -1; dx <= 1; dx++) {
          if (!dx && !dy) continue
          const nx = cx + dx, ny = cy + dy
          if (this.blocked(nx, ny)) continue
          if (dx && dy && (this.blocked(cx + dx, cy) || this.blocked(cx, cy + dy))) continue
          const ni = ny * GW + nx
          const ng = g[cur] + (dx && dy ? Math.SQRT2 : 1)
          if (ng < g[ni]) { g[ni] = ng; f[ni] = ng + h(ni); came[ni] = cur; open.push(ni) }
        }
    }
    if (came[goal] === -1 && goal !== start) return [to]
    const cells: number[] = []
    for (let i = goal; i !== -1; i = came[i]) { cells.push(i); if (i === start) break }
    cells.reverse()
    const pts = cells.map((i) => ({ x: (i % GW) * CELL + CELL / 2, y: Math.floor(i / GW) * CELL + CELL / 2 }))
    pts[pts.length - 1] = { x: to.x, y: to.y }
    return this.smooth([from, ...pts.slice(1)])
  }

  private los(a: Pt, b: Pt) {
    const d = Math.hypot(b.x - a.x, b.y - a.y)
    const n = Math.ceil(d / 3)
    for (let i = 1; i < n; i++) {
      const x = a.x + ((b.x - a.x) * i) / n, y = a.y + ((b.y - a.y) * i) / n
      // figurerna är lite breda: kontrollera en bit åt sidorna också
      for (const ox of [-3, 0, 3]) if (this.blocked(Math.floor((x + ox) / CELL), Math.floor(y / CELL))) return false
    }
    return true
  }

  private smooth(pts: Pt[]): Pt[] {
    if (pts.length < 3) return pts
    const out = [pts[0]]
    let i = 0
    while (i < pts.length - 1) {
      let j = pts.length - 1
      while (j > i + 1 && !this.los(pts[i], pts[j])) j--
      out.push(pts[j])
      i = j
    }
    return out
  }
}
