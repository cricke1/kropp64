// Läkarteamet. Listan är provisorisk: okända agent-id ritas med en reservprofil.

export interface Look {
  skin: string
  hair: string
  hairStyle: 'short' | 'bob' | 'bun' | 'bald' | 'curly' | 'long' | 'side'
  coat: string        // rock eller överdel
  shirt: string       // det som syns i halsen
  pants: string
  glasses?: boolean
  beard?: boolean
  stethoscope?: boolean
}

export interface AgentInfo {
  id: string
  name: string        // kort namn i scenen
  role: string        // yrkesroll
  color: string       // identitetsfärg i transkriptet
  look: Look
}

const coatWhite = '#e9ecea'

export const AGENTS: Record<string, AgentInfo> = {
  ordforande: {
    id: 'ordforande', name: 'Ordföranden', role: 'Allmänläkare', color: '#5b8bc9',
    look: { skin: '#e8b996', hair: '#b9b4ad', hairStyle: 'side', coat: coatWhite, shirt: '#2f4f7a', pants: '#3a4150', stethoscope: true, beard: true },
  },
  kardiolog: {
    id: 'kardiolog', name: 'Kardiologen', role: 'Kardiolog', color: '#d0605a',
    look: { skin: '#c98d68', hair: '#2b211c', hairStyle: 'bun', coat: coatWhite, shirt: '#a33a3a', pants: '#2e3440', stethoscope: true },
  },
  somn: {
    id: 'somn', name: 'Sömnläkaren', role: 'Sömnläkare', color: '#6f8fd8',
    look: { skin: '#f0c9a8', hair: '#d8b46a', hairStyle: 'bob', coat: coatWhite, shirt: '#2c3f73', pants: '#2c3242', glasses: true },
  },
  idrott: {
    id: 'idrott', name: 'Idrottsläkaren', role: 'Idrottsläkare', color: '#4cae7a',
    look: { skin: '#a8714f', hair: '#1d1a18', hairStyle: 'short', coat: '#2f7d57', shirt: '#e8ebe9', pants: '#2b3a33' },
  },
  stress: {
    id: 'stress', name: 'Stressläkaren', role: 'Stressmedicin', color: '#c9a043',
    look: { skin: '#e2ad88', hair: '#7a3f22', hairStyle: 'long', coat: '#c6a04a', shirt: '#efe6d2', pants: '#4a3f33' },
  },
  labb: {
    id: 'labb', name: 'Kemisten', role: 'Klinisk kemist', color: '#3fa6a0',
    look: { skin: '#f2cfb3', hair: '#5a3a26', hairStyle: 'curly', coat: coatWhite, shirt: '#2f8f8a', pants: '#35403f', glasses: true },
  },
  advokat: {
    id: 'advokat', name: 'Advokaten', role: 'Djävulens advokat', color: '#9aa3a8',
    look: { skin: '#d9a27c', hair: '#141414', hairStyle: 'short', coat: '#363c42', shirt: '#b23b33', pants: '#2a2e33', beard: true },
  },
  granskare: {
    id: 'granskare', name: 'Granskaren', role: 'Faktagranskare', color: '#e5574e',
    look: { skin: '#eec3a2', hair: '#8c8c88', hairStyle: 'bald', coat: '#8f8467', shirt: '#e9e4d6', pants: '#3d3a33', glasses: true },
  },
}

export const DEFAULT_ORDER = ['ordforande', 'kardiolog', 'somn', 'idrott', 'stress', 'labb', 'advokat', 'granskare']

const fallbackColors = ['#7fa0b4', '#b48a6a', '#8fae8a', '#b08f99', '#a3a37a']
const fallbackSkins = ['#e8b996', '#c98d68', '#a8714f', '#f0c9a8']
const cache = new Map<string, AgentInfo>()

function hash(s: string) {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return h >>> 0
}

export function agentInfo(id: string): AgentInfo {
  if (AGENTS[id]) return AGENTS[id]
  let a = cache.get(id)
  if (!a) {
    const h = hash(id)
    const nice = id.charAt(0).toUpperCase() + id.slice(1).replace(/[_-]+/g, ' ')
    a = {
      id, name: nice, role: nice, color: fallbackColors[h % fallbackColors.length],
      look: {
        skin: fallbackSkins[(h >> 3) % fallbackSkins.length], hair: ['#2b211c', '#6b4a2e', '#c9b27a'][(h >> 5) % 3],
        hairStyle: (['short', 'bob', 'curly'] as const)[(h >> 7) % 3], coat: coatWhite, shirt: fallbackColors[(h >> 2) % fallbackColors.length], pants: '#353b43',
      },
    }
    cache.set(id, a)
  }
  return a
}
