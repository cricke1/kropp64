// Förgenererar rösterna till demomanuset (src/office/demo.ts) till public/demo-rost/, så att demoläget
// och den publika demon kan låta utan att servern behöver köra talsyntes. Kör igen när manuset ändras:
//
//   node dev/rost-demo.mjs
//
// Kräver rösttjänsten på Lenovon (drift/rost_tjanst.py) eller Parambe på Macen, och ffmpeg.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const web = join(dirname(fileURLToPath(import.meta.url)), '..')
const { demoEvents } = await import(join(web, 'src/office/demo.ts'))
const rader = demoEvents().filter((e) => e.kind === 'agent.say').map((e) => ({ agent: e.payload.agent, text: e.payload.text }))

const ut = join(web, 'public/demo-rost')
rmSync(ut, { recursive: true, force: true })
const tmp = mkdtempSync(join(tmpdir(), 'rost-demo-'))
const fil = join(tmp, 'rader.json')
writeFileSync(fil, JSON.stringify(rader))
execFileSync('uv', ['run', '--quiet', 'python', '-m', 'konsiliet.rost', '--forbered', fil, '--utkatalog', ut],
  { cwd: join(web, '../server'), stdio: 'inherit' })
rmSync(tmp, { recursive: true, force: true })
console.log(`${readdirSync(ut).length - 1} ljudfiler (Ogg Opus) i public/demo-rost`)
