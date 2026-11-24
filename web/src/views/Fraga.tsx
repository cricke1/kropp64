import { useState } from 'preact/hooks'
import { api } from '../api'
import { go } from '../store'

const EXAMPLES = [
  'Varför var min puls hög i natt?',
  'Hur har min återhämtning sett ut den här veckan?',
  'Sover jag sämre efter kvällsträning?',
]

export function Fraga() {
  const [q, setQ] = useState('')
  const [hours, setHours] = useState(72)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit(e: Event) {
    e.preventDefault()
    const text = q.trim()
    if (!text) return
    setBusy(true); setErr(null)
    try {
      await api.ask(text, hours)
      go('kontoret')
    } catch (x: any) {
      setErr(x?.status === 401 ? 'Servern nekade frågan (ej behörig).' : `Kunde inte starta tråden: ${x?.message ?? x}`)
    } finally { setBusy(false) }
  }

  return (
    <div class="fraga">
      <div class="pagehead">
        <h1>Ny tråd</h1>
        <p>Starta en tråd så svarar läkarteamet utifrån din data och journal. Du kan följa tråden live i kontoret.</p>
      </div>
      <form class="panel ask" onSubmit={submit}>
        <div class="body">
          <label for="q" class="lbl">Din fråga</label>
          <textarea id="q" rows={4} value={q} maxLength={600} placeholder="Skriv en fråga om din hälsodata"
            onInput={(e) => setQ((e.target as HTMLTextAreaElement).value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e) }} />
          <div class="examples">
            {EXAMPLES.map((x) => <button type="button" class="linkish" onClick={() => setQ(x)}>{x}</button>)}
          </div>
          <div class="ask-row">
            <label class="inline">
              <span class="muted">Underlag</span>
              <select value={hours} onChange={(e) => setHours(Number((e.target as HTMLSelectElement).value))}>
                <option value={24}>senaste dygnet</option>
                <option value={72}>senaste tre dygnen</option>
                <option value={168}>senaste veckan</option>
                <option value={720}>senaste 30 dagarna</option>
              </select>
            </label>
            <span style="flex:1" />
            <span class="faint num">{q.length}/600</span>
            <button class="btn primary" disabled={busy || !q.trim()}>{busy ? 'Skickar' : 'Starta tråden'}</button>
          </div>
          {err && <div class="err">{err}</div>}
        </div>
      </form>
      <p class="faint small note">Läkarteamet ställer inga diagnoser. Svaret är ett underlag med frågor att ta med till vården. Vid akuta besvär, ring 112. Vid frågor om vård, ring 1177.</p>
    </div>
  )
}
