// Riggvyns 3D-motor (three.js). Laddas lat från Riggvyn.tsx så att resten av sidan förblir snabb.
// Modellen byggs i Blender (render/rigg/rigg.py) och exporteras som Draco-komprimerad glb med bakad AO.

import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { Kontur } from './kontur'
import type { Kalla, Komp, RiggData } from './data'
import { Overlay } from './overlay'

export interface MotorOpt {
  kalla: Kalla
  /** 'full': dra och zooma fritt (Riggen). 'inbaddad': zoom först efter klick, ingen enfingersrotation på pekskärm (Översikt). */
  lage: 'full' | 'inbaddad'
  /** Inspelning: ingen egen bildloop, tiden stegas med stega(). */
  capture?: boolean
  onKlar?: () => void
  /** Bildtakten räcker inte ens på lägsta kvalitet. */
  onForLangsam?: () => void
}

const FARG = {
  hjarta: '#4cc38a', resp: '#dcc05a', neutral: '#d6dadc', akut: '#e5574e',
  kall: new THREE.Color('#5b84a8'), varm: new THREE.Color('#d9a03f'),
}

// Kroppens komponenter i modellen. Vänster och höger är kroppens egna.
const NOD = { hjarta: 'hjarta_cpu', flaktV: 'flakt_vanster', flaktH: 'flakt_hoger', rotorV: 'flakt_vanster_rotor', rotorH: 'flakt_hoger_rotor', kylflans: 'kylflans', psu: 'psu_matare', chassi: 'chassi', glas: 'glas' }

/** Pulsslagets form: snabb sammandragning (ease-in-out) och långsammare avslappning. */
export function slag(fas: number) {
  const ease = (x: number) => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2
  if (fas < 0.13) return ease(fas / 0.13)
  if (fas < 0.55) return 1 - ease((fas - 0.13) / 0.42)
  return 0
}

/** Kritiskt dämpad fjäder (SmoothDamp): mjuk start och mjuk inbromsning. */
class Fjader {
  v = 0
  constructor(public x: number) {}
  mot(mal: number, tid: number, dt: number) {
    const w = 2 / Math.max(1e-4, tid), x = w * dt
    const e = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x)
    const c = this.x - mal
    const t = (this.v + w * c) * dt
    this.v = (this.v - w * t) * e
    this.x = mal + (c + t) * e
    return this.x
  }
  satt(x: number) { this.x = x; this.v = 0 }
}

// ?kvalitet=last stänger av den automatiska sänkningen (för mätningar)
const LAST_KVALITET = typeof location !== 'undefined' && /kvalitet=last/.test(location.hash + location.search)
const ARBETE = typeof window !== 'undefined' ? (window as any) : {}

export class Motor {
  readonly canvas: HTMLCanvasElement
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera = new THREE.PerspectiveCamera(30, 1, 0.05, 20)
  private controls: OrbitControls
  private kontur = new Kontur()
  private overlay: Overlay
  private klocka = 0
  private raf = 0
  private kor = false
  private synlig = true
  private reducera: boolean
  private mobil: boolean
  private dprTak: number
  private kvalitet = 3
  private ro: ResizeObserver
  private io: IntersectionObserver
  private mq: MediaQueryList
  private disposed = false

  // modellen
  private nod: Record<string, THREE.Object3D> = {}
  private glod: THREE.MeshStandardMaterial[] = []
  private ledList: THREE.MeshStandardMaterial[] = []
  private ledStrom: THREE.MeshStandardMaterial[] = []
  private varme: { mat: THREE.Material; u: Record<string, THREE.IUniform> }[] = []
  private skarm?: { canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; sig: string }
  private bbox: Record<string, THREE.Box3> = {}
  private nyckel!: THREE.DirectionalLight
  private kant!: THREE.DirectionalLight
  private inne!: THREE.PointLight
  private hjartLjus!: THREE.PointLight

  // tillstånd som glider mjukt
  private hr = new Fjader(62)
  private resp = new Fjader(14)
  private varmeF = new Fjader(0)
  private vila = new Fjader(0)
  private slagFas = 0
  private andFas = 0
  private rotV = 0
  private rotH = 0

  // kameran
  private hem = { mal: new THREE.Vector3(0, 0.31, 0), az: 0.36, pol: 1.39, dist: 2.1 }
  private kam = { mx: new Fjader(0), my: new Fjader(0.31), mz: new Fjader(0), az: new Fjader(0.36), pol: new Fjader(1.39), dist: new Fjader(2.1) }
  private anvandare = -1e9
  private interaktion = false
  private kalla: Kalla
  private data: RiggData | null = null

  // mätning
  private bilder: number[] = []
  fps = 0

  constructor(private host: HTMLElement, private opt: MotorOpt) {
    this.kalla = opt.kalla
    this.mq = matchMedia('(prefers-reduced-motion: reduce)')
    this.reducera = this.mq.matches
    this.mq.addEventListener('change', this.paRorelse)
    this.mobil = matchMedia('(pointer: coarse)').matches || Math.min(screen.width, screen.height) < 700
    this.dprTak = this.mobil ? 1.5 : 1.75

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: !!opt.capture })
    this.canvas = this.renderer.domElement
    this.canvas.className = 'rigg-canvas'
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.0
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    // skuggkartan ritas en gång per bild, inte en gång per renderingspass (konturen ritar scenen flera gånger)
    this.renderer.shadowMap.autoUpdate = false
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, this.dprTak))
    host.appendChild(this.canvas)
    // Mjukvaru-WebGL (SwiftShader, llvmpipe): börja direkt på lägsta kvalitet
    try {
      const gl = this.renderer.getContext()
      const ext = gl.getExtension('WEBGL_debug_renderer_info')
      const namn = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : ''
      ARBETE.__riggGpu = namn
      if (/swiftshader|llvmpipe|software/i.test(namn)) { this.kvalitet = 0; this.dprTak = 0.75; this.renderer.shadowMap.enabled = false }
    } catch { /* okänd GPU */ }

    this.scene.background = new THREE.Color('#0e1113')
    const pmrem = new THREE.PMREMGenerator(this.renderer)
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    this.scene.environmentIntensity = 0.85
    pmrem.dispose()

    this.ljus()
    this.golv()

    this.controls = new OrbitControls(this.camera, this.canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.enablePan = false
    this.controls.minDistance = 0.45
    this.controls.maxDistance = 3.2
    this.controls.minPolarAngle = 0.35
    this.controls.maxPolarAngle = 1.62
    this.controls.rotateSpeed = 0.6
    this.controls.zoomSpeed = 0.7
    this.controls.addEventListener('start', () => { this.interaktion = true; this.anvandare = this.klocka })
    this.controls.addEventListener('end', () => { this.interaktion = false; this.anvandare = this.klocka; this.lasKamera() })
    if (opt.lage === 'inbaddad') {
      this.controls.enableZoom = false
      if (this.mobil) { this.controls.enableRotate = false; this.canvas.style.touchAction = 'pan-y' }
      this.canvas.addEventListener('pointerdown', () => { this.controls.enableZoom = true })
      this.canvas.addEventListener('pointerleave', () => { this.controls.enableZoom = false })
    }


    this.overlay = new Overlay(host)
    this.overlay.onKvittera = () => this.kalla.kvitteraAkut()

    this.ro = new ResizeObserver(() => this.storlek())
    this.ro.observe(host)
    this.io = new IntersectionObserver((e) => { this.synlig = e[0]?.isIntersecting ?? true; this.planera() }, { rootMargin: '80px' })
    this.io.observe(host)
    document.addEventListener('visibilitychange', this.planera)
    this.storlek()
    ARBETE.__rigg = { motor: this, fps: 0, kvalitet: this.kvalitet, dpr: this.renderer.getPixelRatio(), stega: (n: number, dt: number) => this.stega(n, dt) }
  }

  private paRorelse = () => { this.reducera = this.mq.matches }

  setKalla(k: Kalla) { this.kalla = k }

  async ladda(url: string) {
    // Draco-avkodaren följer med three (standardsökvägen buntas av Vite)
    const draco = new DRACOLoader()
    const loader = new GLTFLoader()
    loader.setDRACOLoader(draco)
    const gltf = await loader.loadAsync(url)
    draco.dispose()
    if (this.disposed) return
    const rot = gltf.scene
    rot.traverse((o) => { if (o.name) this.nod[o.name] = o })
    // Meshar med flera material blir en grupp med barn (kylflans_1, kylflans_2). Använd närmaste namngivna nod.
    const kanda = new Set(Object.values(NOD))
    const nodnamn = (o: THREE.Object3D) => { let x: THREE.Object3D | null = o; while (x && !kanda.has(x.name)) x = x.parent; return x?.name ?? '' }
    rot.traverse((o) => {
      const m = o as THREE.Mesh
      if (!m.isMesh) return
      const nn = nodnamn(o)
      m.castShadow = nn !== NOD.glas
      m.receiveShadow = nn === NOD.chassi || nn === NOD.kylflans || nn === NOD.psu
      const mats = Array.isArray(m.material) ? m.material : [m.material]
      const nya = mats.map((mat) => this.material(mat as THREE.MeshStandardMaterial, nn))
      m.material = Array.isArray(m.material) ? nya : nya[0]
    })
    // Djupförpass för delar som ligger i många lager (30 kylfenor bakom locket, revbenen, fläktbladen):
    // först bara djup, sedan skuggas varje pixel en gång. Utan det föll bildtakten till 15-20 fps i närbild.
    const djup = new THREE.MeshBasicMaterial({ colorWrite: false })
    const lagerdelar: THREE.Mesh[] = []
    for (const namn of [NOD.hjarta, NOD.kylflans, NOD.rotorV, NOD.rotorH]) {
      this.nod[namn]?.traverse((o) => { const m = o as THREE.Mesh; if (m.isMesh && !lagerdelar.includes(m)) lagerdelar.push(m) })
    }
    for (const m of lagerdelar) {
      const f = new THREE.Mesh(m.geometry, djup)
      f.renderOrder = -1
      f.name = m.name + '_djup'
      m.add(f)
    }
    this.scene.add(rot)
    rot.updateMatrixWorld(true)
    for (const k of Object.keys(NOD) as (keyof typeof NOD)[]) {
      const n = this.nod[NOD[k]]
      if (n) this.bbox[k] = new THREE.Box3().setFromObject(n)
    }
    const hb = this.bbox.hjarta
    if (hb) {
      const c = hb.getCenter(new THREE.Vector3())
      this.hjartLjus.position.set(c.x, c.y, hb.max.z - 0.03)
      for (const v of this.varme) v.u.uVarmeCentrum.value.copy(c)
    }
    this.overlay.ankare = this.ankare()
    this.storlek()
    this.hemNu()
    // kompilera konturens shaders redan nu, annars hackar första tråden
    const h0 = this.nod[NOD.hjarta]
    if (h0) {
      this.kontur.valj([h0], FARG.hjarta)
      this.renderer.shadowMap.needsUpdate = true
      this.renderer.render(this.scene, this.camera)
      this.kontur.rita(this.renderer, this.scene, this.camera)
      this.kontur.valj([], FARG.hjarta)
    }
    this.planera()
    this.renderaEn(0)
    this.opt.onKlar?.()
  }

  // -------------------------------------------------------------- material

  private material(mat: THREE.MeshStandardMaterial, objekt: string): THREE.Material {
    const n = mat.name || ''
    if (n.startsWith('glas')) {
      // Härdat glas: bara reflexerna läggs på (additivt), så att det syns som glas utan dyr transmission.
      // MeshBasic med miljökarta: ingen ljusberäkning, så glaset kostar nästan ingenting att rita över hela bilden.
      return new THREE.MeshBasicMaterial({ name: 'glas', color: 0x000000, envMap: this.scene.environment, combine: THREE.AddOperation, reflectivity: 0.07, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })
    }
    if (n.startsWith('psu_skarm')) {
      const canvas = document.createElement('canvas')
      canvas.width = 512; canvas.height = 232
      const tex = new THREE.CanvasTexture(canvas)
      tex.colorSpace = THREE.SRGBColorSpace
      tex.flipY = false
      tex.anisotropy = 4
      this.skarm = { canvas, tex, sig: '' }
      return new THREE.MeshStandardMaterial({ name: n, color: 0x050607, roughness: 0.18, metalness: 0, emissive: 0xffffff, emissiveMap: tex, emissiveIntensity: 1 })
    }
    if (n.startsWith('hjarta_glod')) { mat.emissive.set(FARG.hjarta); this.glod.push(mat); return mat }
    if (n.startsWith('led_list')) { this.ledList.push(mat); return mat }
    if (n.startsWith('led_strom')) { mat.emissive.set(FARG.hjarta); this.ledStrom.push(mat); return mat }
    if (objekt === NOD.kylflans) { if (n.startsWith('flans')) mat.roughness = 0.26; this.varmeShader(mat, 1) }
    else if (objekt === NOD.chassi && n.startsWith('alu_borstad')) this.varmeShader(mat, 0.35)
    if (mat.aoMap) mat.aoMapIntensity = 0.9
    if (n.startsWith('alu_borstad')) { mat.color.multiplyScalar(0.68); mat.roughness = 0.33; mat.envMapIntensity = 0.62 }
    if (n.startsWith('flakt_blad')) mat.envMapIntensity = 0.45
    return mat
  }

  /** Termisk färgkarta: kall stålblå till varm bärnsten, starkast nära hjärtat. */
  private varmeShader(mat: THREE.MeshStandardMaterial, styrka: number) {
    const u = {
      uVarme: { value: 0 }, uVarmeStyrka: { value: styrka },
      uVarmeCentrum: { value: new THREE.Vector3(0.024, 0.30, -0.06) },
      uKall: { value: new THREE.Color(0.66, 0.80, 1.0) }, uVarm: { value: new THREE.Color(1.06, 0.64, 0.30) },
      uGlod: { value: FARG.varm.clone() },
    }
    mat.onBeforeCompile = (sh) => {
      Object.assign(sh.uniforms, u)
      sh.vertexShader = sh.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vVarmePos;')
        .replace('#include <project_vertex>', '#include <project_vertex>\nvVarmePos = (modelMatrix * vec4(transformed, 1.0)).xyz;')
      sh.fragmentShader = sh.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vVarmePos;\nuniform float uVarme;\nuniform float uVarmeStyrka;\nuniform vec3 uVarmeCentrum;\nuniform vec3 uKall;\nuniform vec3 uVarm;\nuniform vec3 uGlod;')
        .replace('#include <color_fragment>', `#include <color_fragment>
          float vNar = 1.0 - smoothstep(0.04, 0.40, distance(vVarmePos, uVarmeCentrum));
          float vLok = clamp(uVarme * (0.45 + 0.75 * vNar), 0.0, 1.0);
          vec3 vTon = mix(uKall, uVarm, vLok);
          diffuseColor.rgb *= mix(vec3(1.0), vTon, uVarmeStyrka);`)
        .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
          totalEmissiveRadiance += uGlod * uVarmeStyrka * 0.32 * smoothstep(0.35, 1.0, vLok) * vNar;`)
    }
    mat.customProgramCacheKey = () => 'varme'
    this.varme.push({ mat, u })
  }

  // -------------------------------------------------------------- scen

  private ljus() {
    const key = new THREE.DirectionalLight(0xfff4e8, 2.4)
    key.position.set(-1.1, 1.6, 1.4)
    key.target.position.set(0, 0.3, 0)
    key.castShadow = true
    const s = this.mobil ? 512 : 1024
    key.shadow.mapSize.set(s, s)
    const c = key.shadow.camera as THREE.OrthographicCamera
    c.left = -0.5; c.right = 0.5; c.top = 0.55; c.bottom = -0.45; c.near = 0.5; c.far = 4.5
    key.shadow.bias = -0.0004
    key.shadow.normalBias = 0.012
    key.shadow.radius = 4
    this.scene.add(key, key.target)
    this.nyckel = key
    const rim = new THREE.DirectionalLight(0xd8e6ff, 1.3)
    rim.position.set(1.3, 0.9, -1.2)
    this.scene.add(rim)
    this.kant = rim
    this.inne = new THREE.PointLight(0xffeedd, 0.3, 0.9, 1.4)
    this.inne.position.set(0, 0.53, 0.09)
    this.scene.add(this.inne)
    this.hjartLjus = new THREE.PointLight(FARG.hjarta, 0, 0.3, 2)
    this.hjartLjus.position.set(0.024, 0.30, 0.08)
    this.scene.add(this.hjartLjus)
  }

  private golv() {
    const skugga = new THREE.Mesh(new THREE.CircleGeometry(2.2, 64), new THREE.ShadowMaterial({ opacity: 0.45 }))
    skugga.rotation.x = -Math.PI / 2
    skugga.position.y = -0.0719
    skugga.receiveShadow = true
    this.scene.add(skugga)
    // svag ljusfläck under riggen så att den står på något
    const c = document.createElement('canvas')
    c.width = c.height = 256
    const g = c.getContext('2d')!
    const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128)
    gr.addColorStop(0, 'rgba(60,70,78,0.55)')
    gr.addColorStop(0.5, 'rgba(40,48,54,0.22)')
    gr.addColorStop(1, 'rgba(14,17,19,0)')
    g.fillStyle = gr
    g.fillRect(0, 0, 256, 256)
    const t = new THREE.CanvasTexture(c)
    t.colorSpace = THREE.SRGBColorSpace
    const flack = new THREE.Mesh(new THREE.CircleGeometry(1.1, 64), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false }))
    flack.rotation.x = -Math.PI / 2
    flack.position.y = -0.072
    this.scene.add(flack)
  }

  private ankare() {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z)
    const b = this.bbox
    const out: Record<string, THREE.Vector3> = {}
    if (b.hjarta) out.hjarta = v(b.hjarta.max.x - 0.01, b.hjarta.max.y - 0.02, b.hjarta.max.z)
    if (b.flaktH) { const c = b.flaktH.getCenter(new THREE.Vector3()); out.flaktar = v(c.x - 0.02, c.y + 0.03, b.flaktH.max.z) }
    if (b.kylflans) { const c = b.kylflans.getCenter(new THREE.Vector3()); out.kylflans = v(b.kylflans.min.x + 0.05, c.y - 0.05, b.kylflans.max.z - 0.03) }
    if (b.psu) { const c = b.psu.getCenter(new THREE.Vector3()); out.psu = v(c.x + 0.04, c.y, b.psu.max.z) }
    return out
  }

  private komponent(k: Komp): { obj: THREE.Object3D[]; box: THREE.Box3 | null } {
    const n = this.nod
    switch (k) {
      case 'hjarta': return { obj: [n[NOD.hjarta]], box: this.bbox.hjarta }
      case 'flaktar': return { obj: [n[NOD.flaktH], n[NOD.flaktV]], box: this.bbox.flaktH && this.bbox.flaktV ? this.bbox.flaktH.clone().union(this.bbox.flaktV) : null }
      case 'kylflans': return { obj: [n[NOD.kylflans]], box: this.bbox.kylflans }
      case 'psu': return { obj: [n[NOD.psu]], box: this.bbox.psu }
      default: return { obj: [n[NOD.chassi]], box: this.bbox.chassi }
    }
  }

  // -------------------------------------------------------------- loop

  private planera = () => {
    const ska = !this.opt.capture && !this.disposed && this.synlig && !document.hidden && Object.keys(this.nod).length > 0
    if (ska && !this.kor) {
      this.kor = true
      let forra = performance.now()
      const loop = (nu: number) => {
        if (!this.kor) return
        const dt = Math.min(0.1, (nu - forra) / 1000)
        forra = nu
        this.mat(nu)
        this.renderaEn(dt)
        this.raf = requestAnimationFrame(loop)
      }
      this.raf = requestAnimationFrame(loop)
    } else if (!ska && this.kor) {
      this.kor = false
      cancelAnimationFrame(this.raf)
    }
  }

  /** Inspelning: rendera n bilder med fast tidssteg. */
  stega(n: number, dt: number) {
    for (let i = 0; i < n; i++) this.renderaEn(dt)
  }

  private mat(nu: number) {
    this.bilder.push(nu)
    while (this.bilder.length && this.bilder[0] < nu - 1000) this.bilder.shift()
    this.fps = this.bilder.length
    ARBETE.__rigg.fps = this.fps
    // Anpassa kvaliteten efter väggklockan (inte riggens klocka, som står nästan still när det går trögt):
    // ett värde per sekund från sekund 3, sänk ett steg när bildtakten ligger under 48 fps.
    if (!this.startTid) this.startTid = nu
    const sek = (nu - this.startTid) / 1000
    if (sek > 3 && sek < 40 && Math.floor(sek) !== this.senastProv) {
      this.senastProv = Math.floor(sek)
      this.prov.push(this.fps)
      ;(ARBETE.__riggHist ||= []).push([Math.floor(sek), this.fps, this.kvalitet, this.renderer.getPixelRatio()])
    }
    // medianen av de fyra senaste sekunderna (det högre av de två mittvärdena), så att ett enstaka hack inte räknas
    const med = this.prov.length >= 4 ? [...this.prov.slice(-4)].sort((a, b) => a - b)[2] : 99
    if (med < 48 && this.kvalitet > 0 && !LAST_KVALITET) this.sank()
    else if (med < 12 && this.kvalitet === 0 && !LAST_KVALITET) {
      // Även lägsta kvalitet är för tungt (till exempel mjukvaru-WebGL): visa stillbilden och värdena som text.
      this.prov = []
      this.opt.onForLangsam?.()
    }
    ARBETE.__rigg.kvalitet = this.kvalitet
    ARBETE.__rigg.dpr = this.renderer.getPixelRatio()
  }

  private sank() {
    this.prov = []
    this.kvalitet--
    if (this.kvalitet === 2) this.dprTak = Math.min(this.dprTak, 1.25)
    if (this.kvalitet === 1) this.dprTak = 1
    if (this.kvalitet === 0) { this.renderer.shadowMap.enabled = false; this.nyckel.castShadow = false; this.dprTak = 0.75 }
    this.storlek()
  }
  private startTid = 0
  private senastProv = -1
  private bildNr = 0
  private prov: number[] = []

  private renderaEn(dt: number) {
    this.klocka += dt
    const d = this.kalla.sample(this.klocka)
    this.data = d
    this.animera(d, dt)
    this.kamera(d, dt)
    this.controls.update(dt)
    this.bildNr++
    // skuggorna rör sig knappt (hjärtat växer 3 %, fläktbladen snurrar): uppdatera varannan/var tredje bild
    this.renderer.shadowMap.needsUpdate = this.bildNr % (this.mobil ? 3 : 2) === 0 || dt === 0
    this.renderer.render(this.scene, this.camera)
    this.kontur.rita(this.renderer, this.scene, this.camera)
    this.overlay.uppdatera(this.camera, d, this.kalla.demo, this.fps)
  }

  private animera(d: RiggData, dt: number) {
    const rm = this.reducera
    const vila = this.vila.mot(d.vilolage ? 1 : 0, 1.4, dt)
    const hr = this.hr.mot(d.hr ?? this.hr.x, 1.2, dt)
    const resp = this.resp.mot(d.resp ?? this.resp.x, 1.5, dt)
    const varme = this.varmeF.mot(Math.min(1, 0.8 * d.strypning + 0.25 * Math.max(0, ((d.hud ?? 0) - (d.hudBas ?? d.hud ?? 0)) / 0.8)), 1.8, dt)

    // hjärtat: slår exakt i pulsen
    this.slagFas = (this.slagFas + dt * (d.hr != null ? hr : 0) / 60) % 1
    const p = d.hr != null ? slag(this.slagFas) : 0
    const h = this.nod[NOD.hjarta]
    if (h) h.scale.setScalar(rm ? 1 : 1 + 0.03 * p)
    const ljus = 1 - 0.6 * vila
    for (const m of this.glod) m.emissiveIntensity = (0.5 + (rm ? 1.2 : 3.2) * p) * (1 - 0.4 * vila)
    this.hjartLjus.intensity = (rm ? 0.02 : 0.06) * p * (1 - 0.4 * vila)

    // lungorna: fläktarna varvar med andningen, varvet ökar vid inandning
    this.andFas = (this.andFas + dt * resp / 60) % 1
    const and = rm ? 1 : 0.55 + 0.45 * Math.sin(Math.PI * this.andFas) ** 2
    const w = (d.resp != null ? 0.34 * resp : 0.8) * and * (1 - 0.45 * vila) * (rm ? 0.35 : 1)
    this.rotV += w * dt
    this.rotH += w * dt * 0.92
    const rv = this.nod[NOD.rotorV], rh = this.nod[NOD.rotorH]
    if (rv) rv.rotation.z = -this.rotV
    if (rh) rh.rotation.z = this.rotH

    // kylningen
    for (const v of this.varme) v.u.uVarme.value = varme

    // viloläge: ljuset dämpas
    this.scene.environmentIntensity = 0.85 * (1 - 0.55 * vila)
    this.nyckel.intensity = 2.4 * (1 - 0.6 * vila)
    this.kant.intensity = 1.3 * (1 - 0.45 * vila)
    this.inne.intensity = 0.3 * ljus
    for (const m of this.ledList) m.emissiveIntensity = 1 - 0.85 * vila
    const andas = rm ? 0.5 : 0.5 + 0.5 * Math.sin(this.klocka * 1.3)
    for (const m of this.ledStrom) m.emissiveIntensity = vila > 0.5 ? 0.3 + 1.2 * andas : 2
    this.ritaSkarm(d, vila)
  }

  private ritaSkarm(d: RiggData, vila: number) {
    const s = this.skarm
    if (!s) return
    const sig = `${d.headroom}|${vila > 0.5}`
    if (sig === s.sig) return
    s.sig = sig
    const g = s.canvas.getContext('2d')!
    const W = s.canvas.width, H = s.canvas.height
    const dim = vila > 0.5 ? 0.45 : 1
    g.fillStyle = '#050607'
    g.fillRect(0, 0, W, H)
    g.globalAlpha = dim
    const v = d.headroom
    const farg = v == null ? '#6a747a' : v >= 60 ? '#4cc38a' : v >= 35 ? '#d9a03f' : '#e0905e'
    g.font = '500 34px "IBM Plex Sans", system-ui, sans-serif'
    g.fillStyle = '#9ba4a9'
    g.textBaseline = 'alphabetic'
    g.fillText('Headroom', 34, 62)
    g.font = '600 92px "IBM Plex Sans", system-ui, sans-serif'
    g.fillStyle = farg
    const txt = v == null ? '-' : String(v)
    g.fillText(txt, 32, 160)
    const tw = g.measureText(txt).width
    g.font = '500 38px "IBM Plex Sans", system-ui, sans-serif'
    g.fillStyle = '#9ba4a9'
    g.fillText('/100', 40 + tw, 160)
    // stapel 0-100 med streck var tionde
    const x0 = 34, x1 = W - 34, y = 196
    g.fillStyle = '#1d2327'
    g.fillRect(x0, y, x1 - x0, 12)
    if (v != null) { g.fillStyle = farg; g.fillRect(x0, y, (x1 - x0) * v / 100, 12) }
    g.fillStyle = '#050607'
    for (let i = 1; i < 10; i++) g.fillRect(x0 + (x1 - x0) * i / 10 - 1, y, 2, 12)
    g.globalAlpha = 1
    s.tex.needsUpdate = true
  }

  // -------------------------------------------------------------- kamera

  private storlek() {
    const w = Math.max(1, this.host.clientWidth), h = Math.max(1, this.host.clientHeight)
    const dpr = Math.min(devicePixelRatio || 1, this.dprTak)
    this.renderer.setPixelRatio(dpr)
    this.renderer.setSize(w, h, false)
    this.kontur.storlek(w, h, dpr)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    // avstånd så att hela riggen (0,85 m hög, 0,6 m bred) får plats
    const vfov = THREE.MathUtils.degToRad(this.camera.fov)
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.camera.aspect)
    this.hem.dist = Math.max(0.43 / Math.tan(vfov / 2), 0.33 / Math.tan(hfov / 2)) + 0.05
    // smal skärm: mätarraden ligger längst ner, så riggen ritas högre upp och lite mindre
    const smal = w < 600
    this.hem.mal.y = smal ? 0.2 : 0.31
    if (smal) this.hem.dist *= 1.1
    this.overlay.storlek(w, h)
    if (!this.kor && Object.keys(this.nod).length) this.renderaEn(0)
  }

  private lasKamera() {
    const off = this.camera.position.clone().sub(this.controls.target)
    const s = new THREE.Spherical().setFromVector3(off)
    this.kam.az.satt(s.theta); this.kam.pol.satt(s.phi); this.kam.dist.satt(s.radius)
    this.kam.mx.satt(this.controls.target.x); this.kam.my.satt(this.controls.target.y); this.kam.mz.satt(this.controls.target.z)
  }

  private kamera(d: RiggData, dt: number) {
    let fokus: Komp | null = null, farg = FARG.neutral
    if (d.akut) { fokus = d.akut.komp; farg = FARG.akut } else if (d.trad) { fokus = d.trad.komp; farg = d.trad.komp === 'hjarta' ? FARG.hjarta : d.trad.komp === 'flaktar' ? FARG.resp : FARG.neutral }
    // konturen
    if (fokus) {
      const k = this.komponent(fokus)
      this.kontur.valj(k.obj, farg)
    } else {
      this.kontur.valj([], farg)
    }
    if (this.interaktion) return
    // målet: hem med långsam pendling, eller nära komponenten under en tråd (vid akut: hemvyn, stilla)
    const pend = this.reducera || d.akut ? 0 : 1
    let mal = this.hem.mal, az = this.hem.az + pend * 0.3 * Math.sin(this.klocka * 0.11), pol = this.hem.pol + pend * 0.05 * Math.sin(this.klocka * 0.07), dist = this.hem.dist
    let tid = 2.2
    if (d.trad && !d.akut) {
      const k = this.komponent(d.trad.komp)
      if (k.box) {
        mal = k.box.getCenter(new THREE.Vector3())
        const sz = k.box.getSize(new THREE.Vector3())
        const vfov = THREE.MathUtils.degToRad(this.camera.fov)
        dist = Math.max(0.78, (Math.max(sz.y, sz.x / Math.max(0.6, this.camera.aspect)) * 3.6) / (2 * Math.tan(vfov / 2)))
        az = 0.22 + pend * 0.08 * Math.sin(this.klocka * 0.2)
        pol = 1.36
        tid = 0.75
      }
    }
    // användaren har nyss dragit: låt kameran ligga kvar en stund innan den glider hem
    const sedan = this.klocka - this.anvandare
    if (sedan < 6 && !d.trad && !d.akut) return
    const K = this.kam
    if (this.reducera) {
      K.mx.satt(mal.x); K.my.satt(mal.y); K.mz.satt(mal.z); K.az.satt(az); K.pol.satt(pol); K.dist.satt(dist)
    } else {
      const t = sedan < 9 ? tid * 2 : tid
      K.mx.mot(mal.x, t, dt); K.my.mot(mal.y, t, dt); K.mz.mot(mal.z, t, dt)
      K.az.mot(az, t, dt); K.pol.mot(pol, t, dt); K.dist.mot(dist, t, dt)
    }
    this.controls.target.set(K.mx.x, K.my.x, K.mz.x)
    const off = new THREE.Vector3().setFromSpherical(new THREE.Spherical(K.dist.x, K.pol.x, K.az.x))
    this.camera.position.copy(this.controls.target).add(off)
  }

  /** Startläget: kameran direkt i hemvyn. */
  hemNu() {
    const K = this.kam, h = this.hem
    K.mx.satt(h.mal.x); K.my.satt(h.mal.y); K.mz.satt(h.mal.z); K.az.satt(h.az); K.pol.satt(h.pol); K.dist.satt(h.dist)
  }

  get senasteData() { return this.data }

  dispose() {
    this.disposed = true
    this.kor = false
    cancelAnimationFrame(this.raf)
    this.ro.disconnect()
    this.io.disconnect()
    this.mq.removeEventListener('change', this.paRorelse)
    document.removeEventListener('visibilitychange', this.planera)
    this.controls.dispose()
    this.overlay.dispose()
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh
      if (m.geometry) m.geometry.dispose()
      const mats = m.material ? (Array.isArray(m.material) ? m.material : [m.material]) : []
      for (const x of mats) {
        for (const v of Object.values(x)) if (v && (v as THREE.Texture).isTexture) (v as THREE.Texture).dispose()
        x.dispose()
      }
    })
    this.kontur.dispose()
    this.renderer.dispose()
    this.canvas.remove()
    if (ARBETE.__rigg?.motor === this) delete ARBETE.__rigg
  }
}
