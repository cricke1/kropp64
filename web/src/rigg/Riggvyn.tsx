// Riggvyn: kroppen som ett PC-chassi i 3D, styrd av sensorerna. Three.js laddas först när vyn syns.
// Utan WebGL visas en stillbild renderad i Blender (samma modell) och mätvärdena som text.

import { useEffect, useRef, useState } from 'preact/hooks'
import './rigg.css'
import { DemoKalla, LiveKalla, type Kalla } from './data'
import { rader } from './overlay'

const url = (p: string) => new URL(p, document.baseURI).href

function harWebGL() {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch { return false }
}

function hashParam(namn: string) {
  const q = location.hash.split('?')[1] ?? ''
  return new URLSearchParams(q).get(namn)
}

export function Riggvyn({ lage = 'inbaddad', demo = false }: { lage?: 'full' | 'inbaddad'; demo?: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'vantar' | 'laddar' | 'klar' | 'fel'>('vantar')
  const [kalla, setKalla] = useState<Kalla | null>(null)
  const capture = hashParam('capture') === '1'

  // datakällan: demo-manus eller live
  useEffect(() => {
    const k: Kalla = demo ? new DemoKalla(Number(hashParam('demostart') ?? 0) || 0, hashParam('akut') === '1') : new LiveKalla()
    k.start()
    setKalla(k)
    return () => k.stop()
  }, [demo])

  // ladda 3D först när vyn närmar sig skärmen
  useEffect(() => {
    if (!kalla || !host.current) return
    if (!harWebGL()) { setStatus('fel'); return }
    let motor: any = null, dod = false
    const el = host.current
    const io = new IntersectionObserver((e) => {
      if (!e[0]?.isIntersecting || motor || dod) return
      io.disconnect()
      setStatus('laddar')
      import('./motor').then(async ({ Motor }) => {
        if (dod) return
        motor = new Motor(el, { kalla, lage, capture, onKlar: () => !dod && setStatus('klar'),
          onForLangsam: () => { if (dod) return; motor?.dispose(); motor = null; setStatus('fel') } })
        await motor.ladda(url('rigg/kropp64-rigg.glb'))
      }).catch((err) => { console.error('Riggvyn', err); motor?.dispose(); motor = null; if (!dod) setStatus('fel') })
    }, { rootMargin: '200px' })
    io.observe(el)
    return () => { dod = true; io.disconnect(); motor?.dispose() }
  }, [kalla])

  return (
    <section class={`rigg rigg-${lage} ${status}`} aria-label="Riggen: kroppen som PC-chassi, styrd av sensorerna">
      <div class="rigg-scen" ref={host}>
        <img class="rigg-poster" src={url('rigg/rigg-still.webp')} alt="Riggen: överkroppen byggd som ett PC-chassi med processor som hjärta och fläktar som lungor" />
        {status === 'laddar' && <div class="rigg-laddar">Laddar 3D</div>}
        {status === 'fel' && kalla && <Reserv kalla={kalla} />}
      </div>
    </section>
  )
}

/** Utan WebGL: stillbilden och mätvärdena som text. */
function Reserv({ kalla }: { kalla: Kalla }) {
  const [, setN] = useState(0)
  const t0 = useRef(performance.now())
  useEffect(() => { const t = setInterval(() => setN((n) => n + 1), 1000); return () => clearInterval(t) }, [])
  const d = kalla.sample((performance.now() - t0.current) / 1000)
  const r = rader(d)
  return (
    <div class="rigg-lager smal">
      {kalla.demo && <div class="rigg-demo">Demo - syntetisk data</div>}
      {d.akut && <div class="rigg-akut" role="alert"><span><strong>Akut: {d.akut.titel}.</strong> {d.akut.text}</span><button type="button" onClick={() => kalla.kvitteraAkut()}>Stäng</button></div>}
      <div class="rigg-kompakt">
        {Object.values(r).map((x) => (
          <div class="cell"><span class="namn">{x.namn}</span><span class="varde" style={{ color: x.farg }}><b>{x.varde}</b>{x.enhet && <span class="enhet">{x.enhet.startsWith('/') ? x.enhet : ' ' + x.enhet}</span>}</span></div>
        ))}
      </div>
      <div class="rigg-info">3D-vyn går inte att visa här (WebGL saknas eller ritar för långsamt). Här visas en stillbild av riggen och mätvärdena som text.</div>
    </div>
  )
}
