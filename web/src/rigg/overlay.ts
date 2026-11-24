// Etiketter, ledlinjer och statusrader ovanpå riggen. Vanlig DOM (skarp text i IBM Plex Sans) som flyttas
// varje bild utan att Preact behöver rendera om.

import type { Camera, Vector3 } from 'three'
import { fmtNum } from '../format'
import { strypningsord, type RiggData } from './data'

type Nyckel = 'hjarta' | 'flaktar' | 'kylflans' | 'psu'
const SIDA: Record<Nyckel, 'v' | 'h'> = { hjarta: 'h', psu: 'h', flaktar: 'v', kylflans: 'v' }
const ORDNING: Nyckel[] = ['hjarta', 'flaktar', 'kylflans', 'psu']

export interface Rader { namn: string; varde: string; enhet: string; sub: string; farg: string }

/** Texterna för varje komponent. Delas av etiketterna och den kompakta mätarraden. */
export function rader(d: RiggData): Record<Nyckel, Rader> {
  const s = strypningsord(d.strypning, d.last)
  const varmeFarg = d.last ? '#9ba4a9' : d.strypning < 0.15 ? '#8fb0cc' : d.strypning < 0.45 ? '#c9b48a' : '#d9a03f'
  return {
    hjarta: { namn: 'Klockfrekvens', varde: fmtNum(d.hr, 0), enhet: 'BPM', sub: d.idle != null ? `Idle-klock ${fmtNum(d.idle, 0)} BPM` : d.hr == null ? 'Ingen puls senaste 10 min' : '', farg: '#4cc38a' },
    flaktar: { namn: 'Andning', varde: fmtNum(d.resp, 0), enhet: '/min', sub: d.vilolage ? 'Fläktarna i viloläge' : '', farg: '#dcc05a' },
    kylflans: { namn: 'Termisk strypning', varde: s, enhet: '', sub: d.hud != null ? `Hudtemp ${fmtNum(d.hud, 1)} °C` : 'Hudtemp - °C', farg: varmeFarg },
    psu: { namn: 'Headroom', varde: fmtNum(d.headroom, 0), enhet: '/100', sub: 'återhämtning', farg: d.headroom == null ? '#9ba4a9' : d.headroom >= 60 ? '#4cc38a' : '#d9a03f' },
  }
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, parent?: HTMLElement) {
  const e = document.createElement(tag)
  e.className = cls
  parent?.appendChild(e)
  return e
}

const SVGNS = 'http://www.w3.org/2000/svg'

export class Overlay {
  ankare: Partial<Record<Nyckel, Vector3>> = {}
  onKvittera?: () => void
  private lager: HTMLDivElement
  private svg: SVGSVGElement
  private et: Record<Nyckel, { box: HTMLDivElement; namn: HTMLElement; varde: HTMLElement; enhet: HTMLElement; sub: HTMLElement; linje: SVGLineElement; prick: SVGCircleElement; w: number; h: number; text: string }>
  private kompakt: HTMLDivElement
  private kompaktCeller: Record<Nyckel, HTMLDivElement>
  private chips: HTMLDivElement
  private demo: HTMLDivElement
  private akut: HTMLDivElement
  private akutText: HTMLSpanElement
  private fps: HTMLDivElement
  private w = 1
  private h = 1
  private smal = false
  private sig = ''
  private visaFps = /fps=1/.test(location.hash + location.search)

  constructor(host: HTMLElement) {
    this.lager = el('div', 'rigg-lager', host)
    this.svg = document.createElementNS(SVGNS, 'svg')
    this.svg.setAttribute('class', 'rigg-linjer')
    this.svg.setAttribute('aria-hidden', 'true')
    this.lager.appendChild(this.svg)
    this.et = {} as any
    for (const k of ORDNING) {
      const box = el('div', `rigg-etikett ${SIDA[k]}`, this.lager)
      const namn = el('span', 'namn', box)
      const rad = el('span', 'varde', box)
      const varde = el('b', '', rad)
      const enhet = el('span', 'enhet', rad)
      const sub = el('span', 'sub', box)
      const linje = document.createElementNS(SVGNS, 'line')
      const prick = document.createElementNS(SVGNS, 'circle')
      prick.setAttribute('r', '3')
      this.svg.append(linje, prick)
      this.et[k] = { box, namn, varde, enhet, sub, linje, prick, w: 0, h: 0, text: '' }
    }
    this.kompakt = el('div', 'rigg-kompakt', this.lager)
    this.kompaktCeller = {} as any
    for (const k of ORDNING) this.kompaktCeller[k] = el('div', 'cell', this.kompakt)
    this.chips = el('div', 'rigg-chips', this.lager)
    this.demo = el('div', 'rigg-demo', this.lager)
    this.demo.textContent = 'Demo - syntetisk data'
    this.akut = el('div', 'rigg-akut', this.lager)
    this.akut.setAttribute('role', 'alert')
    this.akutText = el('span', '', this.akut)
    const knapp = el('button', '', this.akut)
    knapp.type = 'button'
    knapp.textContent = 'Stäng'
    knapp.addEventListener('click', () => this.onKvittera?.())
    this.fps = el('div', 'rigg-fps', this.lager)
  }

  storlek(w: number, h: number) {
    this.w = w
    this.h = h
    this.smal = w < 600
    this.lager.classList.toggle('smal', this.smal)
    this.svg.setAttribute('viewBox', `0 0 ${w} ${h}`)
    for (const k of ORDNING) this.et[k].w = 0
  }

  /** Uppdatera texter (bara när de ändrats) och flytta etiketterna efter kameran. Kamera null = bara mätarraden. */
  uppdatera(camera: Camera | null, d: RiggData, demo: boolean, fps: number) {
    const r = rader(d)
    const sig = JSON.stringify(r) + `|${d.vilolage}|${d.trad?.titel}|${d.akut?.titel}|${demo}`
    if (sig !== this.sig) {
      this.sig = sig
      for (const k of ORDNING) {
        const e = this.et[k], x = r[k]
        e.namn.textContent = x.namn
        e.varde.textContent = x.varde
        e.enhet.textContent = x.enhet ? (x.enhet.startsWith('/') ? x.enhet : ' ' + x.enhet) : ''
        e.sub.textContent = x.sub
        e.sub.hidden = !x.sub
        e.box.style.setProperty('--c', x.farg)
        e.linje.setAttribute('stroke', 'rgba(214,218,220,0.55)')
        e.prick.setAttribute('fill', x.farg)
        e.w = 0
        const c = this.kompaktCeller[k]
        c.innerHTML = ''
        el('span', 'namn', c).textContent = x.namn
        const v = el('span', 'varde', c)
        v.style.color = x.farg
        el('b', '', v).textContent = x.varde
        if (x.enhet) el('span', 'enhet', v).textContent = x.enhet.startsWith('/') ? x.enhet : ' ' + x.enhet
      }
      this.chips.innerHTML = ''
      if (d.vilolage) el('span', 'chip', this.chips).textContent = 'Viloläge'
      if (d.trad && !d.akut) el('span', 'chip trad', this.chips).textContent = `Tråd pågår: ${d.trad.titel}`
      this.demo.hidden = !demo
      this.akut.hidden = !d.akut
      if (d.akut) this.akutText.innerHTML = `<strong>Akut: ${esc(d.akut.titel)}.</strong> ${esc(d.akut.text)}`
    }
    if (this.visaFps) this.fps.textContent = `${fps} fps`
    if (!camera || this.smal) return

    // placera etiketterna i två spalter, i höjd med sina ankare
    const pos: Partial<Record<Nyckel, { ax: number; ay: number; ok: boolean }>> = {}
    for (const k of ORDNING) {
      const a = this.ankare[k]
      if (!a) { pos[k] = { ax: 0, ay: 0, ok: false }; continue }
      const p = a.clone().project(camera)
      pos[k] = { ax: (p.x + 1) / 2 * this.w, ay: (1 - p.y) / 2 * this.h, ok: p.z < 1 && Math.abs(p.x) < 1.2 && Math.abs(p.y) < 1.2 }
    }
    for (const sida of ['v', 'h'] as const) {
      const ks = ORDNING.filter((k) => SIDA[k] === sida && pos[k]!.ok).sort((a, b) => pos[a]!.ay - pos[b]!.ay)
      let golv = 44
      for (const k of ks) {
        const e = this.et[k]
        if (!e.w) { e.w = e.box.offsetWidth; e.h = e.box.offsetHeight }
        let y = Math.max(golv, pos[k]!.ay - e.h / 2)
        y = Math.min(y, this.h - e.h - 12)
        golv = y + e.h + 10
        const x = sida === 'v' ? 16 : this.w - 16 - e.w
        e.box.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`
        e.box.style.opacity = '1'
        const lx = sida === 'v' ? x + e.w + 6 : x - 6
        e.linje.setAttribute('x1', String(lx)); e.linje.setAttribute('y1', String(y + e.h / 2))
        e.linje.setAttribute('x2', String(pos[k]!.ax)); e.linje.setAttribute('y2', String(pos[k]!.ay))
        e.prick.setAttribute('cx', String(pos[k]!.ax)); e.prick.setAttribute('cy', String(pos[k]!.ay))
        e.linje.style.opacity = e.prick.style.opacity = '1'
      }
      for (const k of ORDNING.filter((k) => SIDA[k] === sida && !pos[k]!.ok)) {
        const e = this.et[k]
        e.box.style.opacity = '0'
        e.linje.style.opacity = e.prick.style.opacity = '0'
      }
    }
  }

  dispose() { this.lager.remove() }
}

function esc(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!))
}
