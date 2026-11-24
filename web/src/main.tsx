import { render } from 'preact'
import { useEffect, useState } from 'preact/hooks'
import './styles.css'
import './office/office.css'
import './views/views.css'
import { api, live } from './api'
import { dismissToast, useLive, useRoute, useSide } from './store'
import { Kontoret } from './views/Kontoret'
import { Oversikt } from './views/Oversikt'
import { Konsilier } from './views/Konsilier'
import { Fraga } from './views/Fraga'
import { Systemet } from './views/Systemet'

type Theme = 'system' | 'light' | 'dark'

function readTheme(): Theme {
  try { return (localStorage.getItem('konsiliet.theme') as Theme) || 'system' } catch { return 'system' }
}
function applyTheme(t: Theme) {
  const dark = t === 'dark' || (t === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

// I den publika demon finns inga sparade konsilier och inget som startar språkmodellen.
const NAV: [string, string][] = __PUBLIK_DEMO__
  ? [['kontoret', 'Kontoret'], ['oversikt', 'Översikt'], ['systemet', 'Systemet']]
  : [
      ['kontoret', 'Kontoret'],
      ['oversikt', 'Översikt'],
      ['konsilier', 'Trådar'],
      ['fraga', 'Ny tråd'],
      ['systemet', 'Systemet'],
    ]

const TESTMONSTER = /emulator|syntetisk|test/i

/** Syns på alla sidor så fort databasen har punkter från en testkälla (emulator, dev-syntetisk, test). */
function TestdataBanner() {
  const [k, setK] = useState<{ source: string; n: number }[]>([])
  useEffect(() => {
    let alive = true
    const load = () => api.kallor().then((rows) => { if (alive) setK(rows.filter((r) => r.test || TESTMONSTER.test(r.source))) }).catch(() => {})
    load()
    const t = setInterval(load, 120000)
    return () => { alive = false; clearInterval(t) }
  }, [])
  if (!k.length) return null
  return (
    <div class="demo-banner publik" role="note">
      <strong>Syntetisk testdata i databasen.</strong>
      <span>Källor: {k.map((r) => `${r.source} (${r.n.toLocaleString('sv-SE')} punkter)`).join(', ')}. Värden från de källorna är inte uppmätta på en människa.</span>
    </div>
  )
}

function DemoBanner() {
  return (
    <div class="demo-banner publik" role="note">
      <strong>Demo - syntetisk data.</strong>
      <span>Mätvärdena kommer från ett testskript och tråden i kontoret är ett manus. Inga riktiga hälsodata finns på den här servern.</span>
    </div>
  )
}

/** Ett chip med pinnar och en pulskurva: kroppen som hårdvara. */
function Logo() {
  return (
    <svg width="20" height="20" viewBox="0 0 16 16" aria-hidden="true">
      <g fill="var(--text-3)">
        <rect x="5" y="0" width="1" height="2" /><rect x="7.5" y="0" width="1" height="2" /><rect x="10" y="0" width="1" height="2" />
        <rect x="5" y="14" width="1" height="2" /><rect x="7.5" y="14" width="1" height="2" /><rect x="10" y="14" width="1" height="2" />
        <rect x="0" y="5" width="2" height="1" /><rect x="0" y="7.5" width="2" height="1" /><rect x="0" y="10" width="2" height="1" />
        <rect x="14" y="5" width="2" height="1" /><rect x="14" y="7.5" width="2" height="1" /><rect x="14" y="10" width="2" height="1" />
      </g>
      <rect x="2.5" y="2.5" width="11" height="11" rx="1.5" fill="var(--surface-2)" stroke="var(--line-2)" />
      <path d="M3.8 8.6h1.9l1-2.1 1.5 4 1.5-5.4 1 3.5h1.5" fill="none" stroke="var(--hr)" stroke-width="1.2" stroke-linejoin="round" stroke-linecap="round" />
    </svg>
  )
}

function ThemeButton() {
  const [t, setT] = useState<Theme>(readTheme())
  useEffect(() => {
    applyTheme(t)
    try { localStorage.setItem('konsiliet.theme', t) } catch { /* privat läge */ }
    const mq = matchMedia('(prefers-color-scheme: dark)')
    const f = () => applyTheme(t)
    mq.addEventListener('change', f)
    return () => mq.removeEventListener('change', f)
  }, [t])
  const next: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
  const label: Record<Theme, string> = { system: 'Tema: system', light: 'Tema: ljust', dark: 'Tema: mörkt' }
  return (
    <button class="iconbtn" onClick={() => setT(next[t])} title={label[t]} aria-label={label[t]}>
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5" />
        {t !== 'light' && <path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" />}
        {t === 'system' && <path d="M8 2a6 6 0 0 0 0 12z" fill="none" />}
      </svg>
    </button>
  )
}

function Conn() {
  if (__PUBLIK_DEMO__) return <span class="conn" title="Publik demo utan live-ström"><span class="dot demo" /><span class="label">Demo</span></span>
  const l = useLive()
  const cls = l.state === 'open' ? 'on' : l.state === 'closed' ? 'off' : ''
  const txt = l.state === 'open' ? 'Ansluten' : l.state === 'closed' ? 'Ingen anslutning' : 'Ansluter'
  return <span class="conn" title={`Live-ström: ${txt.toLowerCase()}`}><span class={`dot ${cls}`} /><span class="label">{txt}</span></span>
}

function Toasts() {
  const s = useSide()
  if (!s.toasts.length) return null
  return (
    <div class="toasts" role="status">
      {s.toasts.map((t) => <div class="toast"><b>{t.title}</b><span>{t.body}</span><button class="iconbtn" onClick={() => dismissToast(t.id)}>Ok</button></div>)}
    </div>
  )
}

function App() {
  const r = useRoute()
  useEffect(() => { if (!__PUBLIK_DEMO__) live.start() }, [])
  const view = NAV.some(([k]) => k === r.view) ? r.view : 'kontoret'
  return (
    <div class="app">
      <header class="topbar">
        <a class="brand" href="#/kontoret"><Logo /><span>Kropp64</span></a>
        <nav class="nav" aria-label="Huvudmeny">
          {NAV.map(([k, label]) => <a href={`#/${k}`} aria-current={view === k ? 'page' : undefined}>{label}</a>)}
        </nav>
        <span class="spacer" />
        <Conn />
        <ThemeButton />
      </header>
      {__PUBLIK_DEMO__ ? <DemoBanner /> : <TestdataBanner />}
      <main class="page">
        {view === 'kontoret' && <Kontoret query={r.query} />}
        {view === 'oversikt' && <Oversikt />}
        {view === 'konsilier' && <Konsilier id={r.arg} />}
        {view === 'fraga' && <Fraga />}
        {view === 'systemet' && <Systemet />}
      </main>
      <Toasts />
    </div>
  )
}

applyTheme(readTheme())
render(<App />, document.getElementById('app')!)
