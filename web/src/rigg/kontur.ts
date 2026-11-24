// Kontur runt en markerad komponent. Billigare än OutlinePass: de markerade delarna ritas som vit mask
// (bara de, utan skuggor) och en helskärmsruta lägger en skarp linje utanför maskens kant ovanpå bilden.
// Konturen ritas även där komponenten skyms, så att den alltid syns genom glaset och fläktarna.

import * as THREE from 'three'

const LAGER = 1

export class Kontur {
  private rt: THREE.WebGLRenderTarget
  private mask = new THREE.MeshBasicMaterial({ color: 0xffffff })
  private quad: THREE.Mesh
  private ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
  private valda: THREE.Object3D[] = []
  private mat: THREE.ShaderMaterial

  constructor() {
    this.rt = new THREE.WebGLRenderTarget(4, 4, { depthBuffer: true, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter })
    this.mat = new THREE.ShaderMaterial({
      uniforms: { tMask: { value: this.rt.texture }, uTexel: { value: new THREE.Vector2() }, uFarg: { value: new THREE.Vector3(1, 1, 1) }, uTjock: { value: 2 } },
      vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
      fragmentShader: `
        uniform sampler2D tMask; uniform vec2 uTexel; uniform vec3 uFarg; uniform float uTjock;
        varying vec2 vUv;
        void main() {
          float m = texture2D(tMask, vUv).r;
          float n = 0.0;
          for (int i = 0; i < 8; i++) {
            float a = float(i) * 0.7853982;
            vec2 d = vec2(cos(a), sin(a)) * uTexel * uTjock;
            n = max(n, texture2D(tMask, vUv + d).r);
            n = max(n, texture2D(tMask, vUv + d * 0.5).r);
          }
          float kant = n * (1.0 - m);
          if (kant < 0.01) discard;
          gl_FragColor = vec4(uFarg, kant);
        }`,
      transparent: true, depthTest: false, depthWrite: false, toneMapped: false,
    })
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.mat)
    this.quad.frustumCulled = false
  }

  get aktiv() { return this.valda.length > 0 }

  valj(obj: THREE.Object3D[], hex: string) {
    const ny = obj.filter(Boolean)
    if (ny.length !== this.valda.length || ny.some((o, i) => o !== this.valda[i])) {
      for (const o of this.valda) o.traverse((x) => x.layers.disable(LAGER))
      for (const o of ny) o.traverse((x) => x.layers.enable(LAGER))
      this.valda = ny
    }
    // färgen skrivs rakt till skärmen (sRGB), utan tonmappning
    const c = parseInt(hex.slice(1), 16)
    this.mat.uniforms.uFarg.value.set((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)
  }

  storlek(w: number, h: number, dpr: number) {
    // masken i halv upplösning med linjär filtrering: mjuk kant och en fjärdedel av pixlarna
    this.rt.setSize(Math.max(1, Math.round(w * dpr / 2)), Math.max(1, Math.round(h * dpr / 2)))
    this.mat.uniforms.uTexel.value.set(1 / (w * dpr), 1 / (h * dpr))
    this.mat.uniforms.uTjock.value = 2.6 * dpr
  }

  /** Efter att scenen ritats till skärmen: rita masken och lägg konturen ovanpå. */
  rita(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.Camera) {
    if (!this.valda.length) return
    const bg = scene.background, om = scene.overrideMaterial, lager = camera.layers.mask, skugga = renderer.shadowMap.needsUpdate
    const autoClear = renderer.autoClear, tm = renderer.toneMapping
    scene.background = null
    scene.overrideMaterial = this.mask
    camera.layers.set(LAGER)
    renderer.shadowMap.needsUpdate = false
    renderer.toneMapping = THREE.NoToneMapping
    renderer.setRenderTarget(this.rt)
    renderer.setClearColor(0x000000, 1)
    renderer.clear()
    renderer.render(scene, camera)
    renderer.setRenderTarget(null)
    scene.background = bg
    scene.overrideMaterial = om
    camera.layers.mask = lager
    renderer.shadowMap.needsUpdate = skugga
    renderer.toneMapping = tm
    renderer.autoClear = false
    renderer.render(this.quad, this.ortho)
    renderer.autoClear = autoClear
  }

  dispose() {
    this.rt.dispose()
    this.mat.dispose()
    this.mask.dispose()
    this.quad.geometry.dispose()
  }
}
