// Röster i kontoret. Varje replik kan läsas upp med läkarens egen röst, genererad lokalt i hemnätet
// (server/src/konsiliet/rost.py). Av som standard. Slås på med knappen i kontoret eller ?ljud=1 i adressen.
// Servern läser bara upp repliker som finns i händelseloggen (GET /api/rost/{id}), aldrig fri text.
// I demoläget spelas förgenererade filer från public/demo-rost/ (byggs med web/dev/rost-demo.mjs), och den
// publika demon har ingen talsyntes alls.

const KEY = 'kropp64.ljud'
const base = new URL('.', location.href).pathname.replace(/\/$/, '')

function fromQuery(): boolean | null {
  const q = new URLSearchParams(location.hash.split('?')[1] ?? location.search)
  const v = q.get('ljud') ?? new URLSearchParams(location.search).get('ljud')
  return v === '1' ? true : v === '0' ? false : null
}

function stored(): boolean {
  try { return localStorage.getItem(KEY) === '1' } catch { return false }
}

export interface Line {
  id: number | null        // händelsens id i serverns logg
  agent: string
  text: string
  demo: boolean
}

interface DemoRad { nr: number; agent: string; text: string; fil: string }

export interface SpeakOpts {
  rate: number                 // uppspelningshastighet, följer scenens hastighet
  onFrame?: () => void         // anropas medan rösten hörs (munrörelser)
}

class Rost {
  on = fromQuery() ?? stored()
  volume = 0.9
  private audio: HTMLAudioElement | null = null
  private finish: (() => void) | null = null
  private manifest: Promise<DemoRad[]> | null = null
  private listeners = new Set<() => void>()

  subscribe(l: () => void) { this.listeners.add(l); return () => { this.listeners.delete(l) } }

  set(on: boolean) {
    this.on = on
    try { localStorage.setItem(KEY, on ? '1' : '0') } catch { /* privat läge */ }
    if (!on) this.stop()
    // Ett tyst klipp i samma klick låser upp uppspelning i webbläsare som kräver en användarhandling.
    if (on) { const a = new Audio(); a.muted = true; a.play().catch(() => {}) }
    this.listeners.forEach((l) => l())
  }

  /** Demons fil spelas bara om agent och text stämmer exakt med manuset (annars är filen inaktuell). */
  private async demoFile(l: Line): Promise<string | null> {
    this.manifest ??= fetch(`${base}/demo-rost/index.json`).then((r) => (r.ok ? r.json() : [])).catch(() => [])
    const rad = (await this.manifest).find((r) => r.agent === l.agent && r.text === l.text)
    return rad ? `${base}/demo-rost/${rad.fil}` : null
  }

  async url(l: Line): Promise<string | null> {
    if (l.demo) return this.demoFile(l)
    if (__PUBLIK_DEMO__ || l.id == null || l.id < 0) return null
    return `${base}/api/rost/${l.id}`
  }

  /** Be servern generera i förväg, så att nästa replik är klar när den behövs. */
  async prefetch(l: Line) {
    if (!this.on) return
    const u = await this.url(l)
    if (u) fetch(u).catch(() => {})
  }

  /** Spelar repliken. Löser när den är slut, avbruten, eller om ljudet inte hunnit börja inom 8 s. */
  async speak(l: Line, o: SpeakOpts): Promise<void> {
    if (!this.on) return
    this.stop()
    const u = await this.url(l)
    if (!u || !this.on) return
    const a = new Audio(u)
    a.volume = this.volume
    a.playbackRate = o.rate
    a.preservesPitch = true
    this.audio = a
    await new Promise<void>((resolve) => {
      let tick = 0
      const done = () => {
        clearTimeout(slow); clearInterval(tick)
        if (this.audio === a) { this.audio = null; this.finish = null }
        resolve()
      }
      this.finish = () => { a.pause(); done() }
      const slow = setTimeout(() => { if (a.currentTime === 0) this.finish?.() }, 8000)
      a.addEventListener('ended', done)
      a.addEventListener('error', done)
      a.addEventListener('playing', () => { if (o.onFrame && !tick) tick = window.setInterval(() => { if (!a.paused) o.onFrame!() }, 80) })
      a.play().catch(done)   // t.ex. autoplay spärrad: hoppa över rösten, bubblan går ändå
    })
  }

  stop() { this.finish?.() }
  pause() { this.audio?.pause() }
  resume() { this.audio?.play().catch(() => this.stop()) }
  setRate(r: number) { if (this.audio) this.audio.playbackRate = r }
}

export const rost = new Rost()
