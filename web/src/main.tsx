import { render } from 'preact'
import { useEffect, useState } from 'preact/hooks'
import './styles.css'
import './office/office.css'
import './views/views.css'
import { live } from './api'
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

const NAV: [string, string][] = [
  ['kontoret', 'Kontoret'],
  ['oversikt', 'Översikt'],
  ['konsilier', 'Konsilier'],
  ['fraga', 'Fråga'],
  ['systemet', 'Systemet'],
]

function Logo() {
  return (
    <svg width="20" height="20" viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
      <rect width="16" height="16" rx="3" fill="var(--surface-2)" stroke="var(--line-2)" />
      <path fill="var(--hr)" d="M2 9h3l1-3 2 6 2-8 1 5h3v1h-3.8l-.4-2-2 7.6-2-6.2-.6 1.6H2z" />
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
  useEffect(() => { live.start() }, [])
  const view = NAV.some(([k]) => k === r.view) ? r.view : 'kontoret'
  return (
    <div class="app">
      <header class="topbar">
        <a class="brand" href="#/kontoret"><Logo /><span>Konsiliet</span></a>
        <nav class="nav" aria-label="Huvudmeny">
          {NAV.map(([k, label]) => <a href={`#/${k}`} aria-current={view === k ? 'page' : undefined}>{label}</a>)}
        </nav>
        <span class="spacer" />
        <Conn />
        <ThemeButton />
      </header>
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
