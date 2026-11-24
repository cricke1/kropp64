// Riggvyn för landningssidan (site/, kropp64.se). Byggs till site/dist/rigg/rigg.js med vite.sajt.config.ts
// och laddas av site/sida.js först när besökaren startar riggen. Alltid demoläge med syntetiska värden.

import riggCss from './rigg.css?inline'
import plex400 from '@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2?url'
import plex600 from '@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff2?url'
import { DemoKalla } from './data'
import { Motor } from './motor'

const SAJT_CSS = `
@font-face { font-family: 'IBM Plex Sans'; font-weight: 400; font-display: swap; src: url(${plex400}) format('woff2'); }
@font-face { font-family: 'IBM Plex Sans'; font-weight: 600; font-display: swap; src: url(${plex600}) format('woff2'); }
.bild .rigg-scen {
  --font: 'IBM Plex Sans', system-ui, sans-serif; --mono: ui-monospace, Menlo, monospace; --line: #262d32; --radius: 0px;
  height: auto; aspect-ratio: 3 / 2; border: 0; border-radius: 0; line-height: 1.4; font-size: 14px;
}
@media (max-width: 699px) { .bild .rigg-scen { height: auto; aspect-ratio: 4 / 5; } }
.bild .rigg-scen .rigg-poster { opacity: 1; }
.bild .rigg-scen.klar .rigg-poster { opacity: 0; pointer-events: none; }
`

let stil = false
function css() {
  if (stil) return
  stil = true
  const s = document.createElement('style')
  s.textContent = riggCss + SAJT_CSS
  document.head.appendChild(s)
}

function harWebGL() {
  try { return !!document.createElement('canvas').getContext('webgl2') } catch { return false }
}

/**
 * Startar riggen i elementet scen (som ska vara tomt). bas = katalogen med kropp64-rigg.glb och rigg-still.webp.
 * Returnerar en funktion som stänger riggen. onFel anropas om WebGL saknas eller ritar för långsamt.
 */
async function starta(scen: HTMLElement, bas: string, onFel: () => void): Promise<() => void> {
  css()
  scen.classList.add('rigg-scen')
  const poster = document.createElement('img')
  poster.className = 'rigg-poster'
  poster.alt = 'Riggen: överkroppen byggd som ett PC-chassi, renderad i Blender'
  poster.src = new URL('rigg-still.webp', bas).href
  scen.appendChild(poster)
  if (!harWebGL()) { onFel(); return () => scen.replaceChildren() }
  const kalla = new DemoKalla()
  let motor: Motor | null = null
  const stang = () => { motor?.dispose(); motor = null }
  try {
    motor = new Motor(scen, {
      kalla, lage: 'inbaddad',
      onKlar: () => scen.classList.add('klar'),
      onForLangsam: () => { stang(); onFel() },
    })
    await motor.ladda(new URL('kropp64-rigg.glb', bas).href)
  } catch (e) {
    console.error('Riggen', e)
    stang()
    onFel()
  }
  return () => { stang(); scen.replaceChildren(); scen.classList.remove('klar') }
}

;(window as any).Kropp64Rigg = { starta }
