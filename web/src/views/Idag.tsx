// Idag: svaret på morgonfrågan på fem sekunder. Träna, ta det lugnt eller vila, varför på en rad och planen.
// Allt räknas på servern med regler i koden (server/src/konsiliet/vardag.py), ingen språkmodell fattar beslutet.

import { useState } from 'preact/hooks'
import { api } from '../api'
import { dayMonth, duration, hm } from '../format'
import { go, useAsync, useSide } from '../store'

const KLASS: Record<string, string> = { trana: 'ok', klart: 'ok', lugnt: 'warn', vila: 'danger' }

export const FRAGOR = [
  'Varför är jag så trött i dag?',
  'Kan jag köra ett hårdare pass i veckan?',
  'Hur påverkar sena spelkvällar min sömn?',
]

function tid(h: number) { return duration(h * 3600) }

export function Idag() {
  const q = useAsync(() => api.idag(), [])
  const vecka = useAsync(() => api.vecka(), [])
  const pass = useAsync(() => api.pass(7), [])
  const [n, setN] = useState(0)
  const notiser = useAsync(() => api.notiser(1), [n])
  const s = useSide()
  const [ord, setOrd] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const i = q.data

  async function fraga(text: string) {
    setBusy(true); setErr(null)
    try { const r = await api.ask(text, 72); go(`konsilier/${encodeURIComponent(r.consult_id)}`) }
    catch (e: any) { setErr(`Kunde inte starta tråden: ${e?.message ?? e}`) } finally { setBusy(false) }
  }
  async function fokus(av: boolean) {
    try { await api.knuffSvar('fokus', av ? 'av' : 'fokus', 120); setN((x) => x + 1) } catch (e: any) { setErr(String(e?.message ?? e)) }
  }

  if (q.error) return <div class="idag"><div class="pagehead"><h1>Idag</h1></div><div class="panel"><div class="empty">Ingen kontakt med servern ({q.error}).</div></div></div>
  if (!i) return <div class="idag"><div class="pagehead"><h1>Idag</h1></div><div class="panel"><div class="empty">Hämtar dagens svar.</div></div></div>
  const plan = i.plan ?? {}
  const sm = i.somn ?? {}
  const vk = i.veckan ?? {}
  const senaste = pass.data?.[pass.data.length - 1]
  const brief = s.brief?.payload?.datum === i.datum ? s.brief?.payload : null
  const nt = notiser.data
  const fokusTill = nt?.fokus_till as number | null

  return (
    <div class="idag">
      <div class="pagehead"><h1>Idag</h1><p class="faint">{dayMonth(i.ts)}, uppdaterat {hm(i.ts)}</p></div>
      <section class={`panel beslut ${KLASS[i.beslut] ?? ''}`} aria-label={`${i.rubrik}. ${plan.text}. ${i.varfor}`}>
        <div class="body">
          <h2 class="beslut-rubrik">{i.rubrik}</h2>
          {plan.text && <p class="beslut-plan num">{plan.text}</p>}
          {plan.forslag && <p class="muted">{plan.forslag[0].toUpperCase() + plan.forslag.slice(1)}</p>}
          {i.varfor && <p><b>Varför:</b> {i.varfor}.</p>}
          {i.matt && <p class="faint small">Mätt: {i.matt}.</p>}
          {i.oppet?.consult_id && <button class="btn small" onClick={() => go(`konsilier/${encodeURIComponent(i.oppet.consult_id)}`)}>Öppna tråden</button>}
          <button class="linkish" aria-expanded={ord} onClick={() => setOrd(!ord)}>{ord ? 'Dölj förklaringarna' : 'Vad betyder Headroom och zon?'}</button>
          {ord && (
            <dl class="ordlista">
              {Object.entries(i.ordlista ?? {}).map(([k, v]) => <><dt>{k}</dt><dd>{String(v)}</dd></>)}
              <dt>Reglerna</dt><dd>{i.regler}</dd>
              <dt>Pulszoner</dt><dd class="num">{(i.zoner?.zoner ?? []).map((z: any) => `zon ${z.zon}: ${z.lo}-${z.hi} BPM (${z.betyder})`).join('; ')}</dd>
            </dl>
          )}
        </div>
      </section>

      {i.headroom == null && !sm.natt && (
        <section class="panel">
          <header><h2>Kom igång</h2></header>
          <div class="body">
            <ol class="plain">
              <li>Ge Health Connect behörighet i mobilappen, så läses de senaste 30 dagarna in som baslinje.</li>
              <li>Öppna Kropp64 på klockan och tillåt puls i bakgrunden.</li>
              <li>Sov en natt med klockan. Då kommer Headroom och dagens råd bygger på din sömn.</li>
            </ol>
          </div>
        </section>
      )}

      <div class="grid two">
        <section class="panel">
          <header><h2>Veckans pass</h2><span class="meta">plan vecka {i.niva?.vecka_nr}, nivå {i.niva?.niva} av 4</span></header>
          <div class="body">
            <div class="pass-rad" aria-label={`${vk.pass} av ${vk.mal} pass den här veckan`}>
              {Array.from({ length: vk.mal ?? 3 }, (_, k) => <i class={k < vk.pass ? 'klar' : ''} />)}
              <b class="num">{vk.pass} av {vk.mal}</b>
            </div>
            <p class="faint small">Passdagar: {(vk.passdagar ?? []).join(', ')}. {vk.veckor_i_rad > 0 ? `${vk.veckor_i_rad} veckor i rad med målet nått.` : 'Nivån höjs när minst två pass blir av en vecka.'}</p>
            {senaste && (
              <div class="senaste-pass">
                <b>Senaste pass: {senaste.minuter} min {senaste.typ}, {dayMonth(senaste.start)}</b>
                {senaste.puls_medel != null && <div class="small num">Medelpuls {senaste.puls_medel} BPM, max {senaste.puls_max} BPM. {senaste.zon_minuter.map((m: number, k: number) => m ? `zon ${k + 1}: ${m} min` : '').filter(Boolean).join(', ')}{senaste.andel_i_malzon != null ? `. ${senaste.andel_i_malzon} % i målzon ${senaste.malzon}` : ''}.</div>}
                <div class="faint small">{senaste.rad}</div>
              </div>
            )}
          </div>
        </section>
        <section class="panel">
          <header><h2>Viloläge (sömn)</h2>{sm.natt && <span class="meta num">i natt {tid(sm.natt.timmar)}</span>}</header>
          <div class="body">
            <p>{sm.laggdags_text}.</p>
            <p class={`small ${sm.skuld_h >= 5 ? 'warn-text' : 'faint'}`}>Sömnskuld {tid(sm.skuld_h ?? 0)} på {sm.natter_med_data} nätter, mot behovet {tid(sm.behov_h ?? 8)} per natt.</p>
            {sm.sena_natter_vid_datorn > 0 && <p class="faint small">Vid datorn efter midnatt {sm.sena_natter_vid_datorn} av 7 nätter.</p>}
          </div>
        </section>
      </div>

      {brief?.text && (
        <section class="panel">
          <header><h2>POST-skärmen</h2><span class="meta">{brief.skrivet_av ?? 'idrottsläkaren'}</span></header>
          <div class="body"><p class="lead">{brief.text}</p></div>
        </section>
      )}

      <div class="grid two">
        <section class="panel">
          <header><h2>Fråga teamet</h2><span class="meta">snabbsvar direkt, tråden på några minuter</span></header>
          <div class="body fragor">
            {FRAGOR.map((f) => <button class="btn" disabled={busy} onClick={() => fraga(f)}>{f}</button>)}
            <a href="#/fraga" class="linkish">Egen fråga</a>
            {err && <div class="err small">{err}</div>}
          </div>
        </section>
        <section class="panel">
          <header><h2>Knuffar</h2>{nt && <span class="meta num">{nt.idag} av {nt.budget} i dag</span>}</header>
          <div class="body">
            <p class="faint small">{fokusTill ? `Fokusläge till ${hm(fokusTill)}: inga AFK- eller stressknuffar.` : `Tysta timmar ${nt?.tysta ?? '23:00-08:00'}. Akuta larm går alltid fram.`}</p>
            <button class="btn small" onClick={() => fokus(!!fokusTill)}>{fokusTill ? 'Avsluta fokusläge' : 'Jag är mitt i ett pass (2 h)'}</button>
            {' '}<a class="btn small" href="api/besoksunderlag.pdf" target="_blank" rel="noopener">Besöksunderlag (PDF)</a>
          </div>
        </section>
      </div>

      {vecka.data && (
        <section class="panel">
          <header><h2>Veckan hittills</h2><span class="meta">från {vecka.data.vecka_start}</span></header>
          <div class="body">
            <ul class="plain">{vecka.data.rader.map((r: string) => <li>{r}</li>)}</ul>
            <p><b>{vecka.data.nasta}</b></p>
          </div>
        </section>
      )}
    </div>
  )
}
