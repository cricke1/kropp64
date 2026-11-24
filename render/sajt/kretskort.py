"""Sajtens hjaltebild: makrobild av kroppens moderkort.

Processorn U1 ar lasergraverad "Kropp64", en oppen guldledare i form av ett EKG gar in i den, en
hjartslags-LED (D7 HB) sitter bredvid och flaktkontakten heter J4 Andning. Varden pa locket ar
exempelvarden (samma som i appens illustrationer), inte uppmatt data.

blender -b -P kretskort.py -- <bredd> <hojd> <ut.png> [samples] [variant]
variant: 'slut' (standard) eller 'test'
Skriver ocksa <ut>_heat.exr (AOV "heat", underlag for varmekameraversionen) och <ut>_ankare.json
(bildkoordinater for LED, processor m.m. sa att sajten kan lagga etiketter och LED-pulsen ratt).
Texturerna pcb.png och etch.png ritas av texturer.py och ska ligga bredvid skriptet.
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector
from common import *
from pcb_layout import *

a = args()
W_ = int(a[0]) if a else 2400
H_ = int(a[1]) if len(a) > 1 else 1600
OUT = a[2] if len(a) > 2 else os.path.join(HERE, 'ut', 'kretskort.png')
SAMPLES = int(a[3]) if len(a) > 3 else 256
VAR = a[4] if len(a) > 4 else 'slut'
EXPO = float(a[5]) if len(a) > 5 else -3.2
FSTOP = float(a[6]) if len(a) > 6 else 9.0

MESHES = {}


def blk_mesh(key, sx, sy, sz, bev):
    if key in MESHES:
        return MESHES[key]
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx, v.co.y * sy, (v.co.z + 0.5) * sz))
    me = bpy.data.meshes.new(key)
    bm.to_mesh(me)
    bm.free()
    MESHES[key] = (me, bev)
    return MESHES[key]


def blk(name, sx, sy, sz, x, y, z0, mat, bev=0.0, rot=0.0):
    """Lada i mm, origo i bottenmitten."""
    key = '%s_%.3f_%.3f_%.3f' % (mat.name, sx, sy, sz)
    me, _ = blk_mesh(key, sx * MM, sy * MM, sz * MM, bev)
    if not me.materials:
        me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    link(ob)
    ob.location = (x * MM, y * MM, z0 * MM)
    ob.rotation_euler.z = math.radians(rot)
    if bev > 0:
        m = ob.modifiers.new('b', 'BEVEL')
        m.width = bev * MM
        m.segments = 2
        m.limit_method = 'ANGLE'
    return ob


def aov(m, value=None, socket=None):
    """Skriv varmevardet (0..1) till AOV 'heat'."""
    nt = m.node_tree
    o = nt.nodes.new('ShaderNodeOutputAOV')
    o.aov_name = 'heat'
    if socket is not None:
        nt.links.new(socket, o.inputs['Value'])
    else:
        o.inputs['Value'].default_value = value
    return m


def mat(name, color, rough=0.5, metal=0.0, heat=0.2, **kw):
    return aov(mat_principled(name, color, rough, metal, **kw), heat)


def board_material():
    m = bpy.data.materials.new('kort')
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(os.path.join(HERE, 'pcb.png'))
    tex.image.colorspace_settings.name = 'Non-Color'
    tex.interpolation = 'Cubic'
    tex.extension = 'EXTEND'
    nt.links.new(tc.outputs['Generated'], tex.inputs['Vector'])
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(tex.outputs['Color'], sep.inputs['Color'])
    R, G, B = sep.outputs['Red'], sep.outputs['Green'], sep.outputs['Blue']

    def mix(fac, c1, c2):
        n = nt.nodes.new('ShaderNodeMix')
        n.data_type = 'RGBA'
        nt.links.new(fac, n.inputs['Factor'])
        for i, c in ((6, c1), (7, c2)):
            if isinstance(c, tuple):
                n.inputs[i].default_value = c
            else:
                nt.links.new(c, n.inputs[i])
        return n.outputs[2]

    def fmix(fac, v1, v2):
        n = nt.nodes.new('ShaderNodeMix')
        n.data_type = 'FLOAT'
        nt.links.new(fac, n.inputs['Factor'])
        for i, v in ((2, v1), (3, v2)):
            if isinstance(v, float):
                n.inputs[i].default_value = v
            else:
                nt.links.new(v, n.inputs[i])
        return n.outputs[0]

    # lodmask: djupt gron, ljusare dar koppar ligger under
    mask = mix(R, (0.010, 0.060, 0.032, 1), (0.030, 0.150, 0.070, 1))
    gold = (0.90, 0.52, 0.16, 1)
    col = mix(G, mask, gold)
    col = mix(B, col, (0.78, 0.78, 0.74, 1))
    nt.links.new(col, b.inputs['Base Color'])
    nt.links.new(G, b.inputs['Metallic'])
    rough = fmix(G, 0.42, 0.22)
    rough = fmix(B, rough, 0.7)
    nt.links.new(rough, b.inputs['Roughness'])
    # lodmasken ar en blank lack ovanpa: coat dar det inte ar guld eller silkscreen
    add = nt.nodes.new('ShaderNodeMath'); add.operation = 'ADD'
    nt.links.new(G, add.inputs[0]); nt.links.new(B, add.inputs[1])
    inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.use_clamp = True
    inv.inputs[0].default_value = 1.0
    nt.links.new(add.outputs[0], inv.inputs[1])
    nt.links.new(inv.outputs[0], b.inputs['Coat Weight'])
    b.inputs['Coat Roughness'].default_value = 0.12
    b.inputs['Coat Tint'].default_value = (0.75, 0.95, 0.8, 1)
    # relief: koppar och silkscreen ligger ovanpa laminatet
    h = nt.nodes.new('ShaderNodeMath'); h.operation = 'MULTIPLY_ADD'
    nt.links.new(R, h.inputs[0]); h.inputs[1].default_value = 0.6
    nt.links.new(add.outputs[0], h.inputs[2])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.35
    bump.inputs['Distance'].default_value = 0.00003
    nt.links.new(h.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    # varme: avtar med avstandet till processorn, kopparn leder lite extra
    ob_ = nt.nodes.new('ShaderNodeTexCoord')
    sub = nt.nodes.new('ShaderNodeVectorMath'); sub.operation = 'DISTANCE'
    nt.links.new(ob_.outputs['Object'], sub.inputs[0])
    sub.inputs[1].default_value = (CPU[0] * MM, CPU[1] * MM, 0)
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = 0.012
    mr.inputs['From Max'].default_value = 0.11
    mr.inputs['To Min'].default_value = 0.62
    mr.inputs['To Max'].default_value = 0.08
    nt.links.new(sub.outputs['Value'], mr.inputs['Value'])
    hv = nt.nodes.new('ShaderNodeMath'); hv.operation = 'MULTIPLY_ADD'
    nt.links.new(R, hv.inputs[0]); hv.inputs[1].default_value = 0.06
    nt.links.new(mr.outputs['Result'], hv.inputs[2])
    aov(m, socket=hv.outputs[0])
    return m


def ihs_material():
    m = bpy.data.materials.new('ihs')
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Metallic'].default_value = 1.0
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (1 / (IHS * MM), 1 / (IHS * MM), 1)
    mp.inputs['Location'].default_value = (0.5, 0.5, 0)
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(os.path.join(HERE, 'etch.png'))
    tex.image.colorspace_settings.name = 'Non-Color'
    tex.extension = 'CLIP'
    tex.interpolation = 'Cubic'
    nt.links.new(mp.outputs['Vector'], tex.inputs['Vector'])
    # borstat nickel: anisotropt brus langs x
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 1.0
    nz.inputs['Detail'].default_value = 8.0
    sc_ = nt.nodes.new('ShaderNodeMapping')
    sc_.inputs['Scale'].default_value = (300, 30000, 1)
    nt.links.new(tc.outputs['Object'], sc_.inputs['Vector'])
    nt.links.new(sc_.outputs['Vector'], nz.inputs['Vector'])
    rr = nt.nodes.new('ShaderNodeMapRange')
    rr.inputs['To Min'].default_value = 0.16
    rr.inputs['To Max'].default_value = 0.30
    nt.links.new(nz.outputs['Fac'], rr.inputs['Value'])
    # gravyren: matt och morkare
    rmix = nt.nodes.new('ShaderNodeMix'); rmix.data_type = 'FLOAT'
    nt.links.new(tex.outputs['Color'], rmix.inputs['Factor'])
    nt.links.new(rr.outputs['Result'], rmix.inputs[2])
    rmix.inputs[3].default_value = 0.62
    nt.links.new(rmix.outputs[0], b.inputs['Roughness'])
    cmix = nt.nodes.new('ShaderNodeMix'); cmix.data_type = 'RGBA'
    nt.links.new(tex.outputs['Color'], cmix.inputs['Factor'])
    cmix.inputs[6].default_value = (0.80, 0.79, 0.77, 1)
    cmix.inputs[7].default_value = (0.20, 0.20, 0.20, 1)
    nt.links.new(cmix.outputs[2], b.inputs['Base Color'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.25
    bump.inputs['Distance'].default_value = 0.00002
    bump.invert = True
    nt.links.new(tex.outputs['Color'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return aov(m, 1.0)


def build(sc):
    Wb, Db, Tb = BOARD
    # underlag: matt svart antistatmatta
    bpy.ops.mesh.primitive_plane_add(size=1.2, location=(0, 0, -Tb * MM - 0.0002))
    golv = bpy.context.active_object
    assign(golv, mat('matta', (0.004, 0.004, 0.005, 1), 0.9, heat=0.02))
    kort = blk('kort', Wb, Db, Tb, 0, 0, -Tb, board_material())
    kort.modifiers.clear()

    alu = aov(mat_aluminium('alu', rough=0.28), 0.35)
    tenn = mat('tenn', (0.78, 0.78, 0.76, 1), 0.3, 1.0, heat=0.3)
    keram = mat('keram', (0.42, 0.30, 0.18, 1), 0.45, heat=0.3)
    epoxi = mat('epoxi', (0.018, 0.018, 0.02, 1), 0.5, heat=0.55)
    ferrit = mat('ferrit', (0.025, 0.025, 0.028, 1), 0.6, heat=0.6)
    nylon = mat('nylon', (0.80, 0.77, 0.68, 1), 0.55, heat=0.15, **{'Subsurface Weight': 0.2})
    guld = mat('guld', (0.95, 0.68, 0.32, 1), 0.2, 1.0, heat=0.15)
    vit = mat('ledbas', (0.85, 0.85, 0.84, 1), 0.4, heat=0.5)
    klar = mat('epoxiklar', (1, 1, 1, 1), 0.05, heat=0.5, **{'Transmission Weight': 1.0, 'IOR': 1.5})
    die = mat('leddie', (1, 0.4, 0.1, 1), 0.4, heat=0.7, **{'Emission Color': (1.0, 0.30, 0.06, 1), 'Emission Strength': 60.0})
    substr = mat('substrat', (0.035, 0.05, 0.03, 1), 0.3, heat=0.85, **{'Coat Weight': 1.0, 'Coat Roughness': 0.1})

    cx, cy = CPU
    # processorn
    blk('substrat', SUBSTRATE, SUBSTRATE, 1.15, cx, cy, 0.35, substr, bev=0.15)
    blk('kulor', SUBSTRATE - 1.5, SUBSTRATE - 1.5, 0.35, cx, cy, 0.0, epoxi)
    ihs = rounded_box('ihs', IHS * MM, IHS * MM, 3.0 * MM, 2.4 * MM, 0.5 * MM, seg_plan=10, seg_edge=4)
    ihs.location = (cx * MM, cy * MM, 1.5 * MM)
    assign(ihs, ihs_material())
    for i in range(12):   # kondensatorer pa substratet
        for (x, y, r) in ((cx - 16.8, cy - 13 + i * 2.3, 90), (cx - 13 + i * 2.3, cy - 16.8, 0)):
            blk('subcap', 1.0, 0.5, 0.5, x, y, 1.5, keram, rot=r)
            for s in (-1, 1):
                ox, oy = (s * 0.42, 0) if r == 0 else (0, s * 0.42)
                blk('subcap_e', 0.18, 0.52, 0.52, x + ox, y + oy, 1.49, tenn, rot=r)

    anchors = {'cpu': (cx, cy, 4.5)}
    for typ, x, y, rot, lab in components():
        if typ in ('c0402', 'c0603', 'r0603'):
            L, Wd, Hh = {'c0402': (1.0, 0.5, 0.5), 'c0603': (1.6, 0.8, 0.8), 'r0603': (1.6, 0.8, 0.45)}[typ]
            body = epoxi if typ == 'r0603' else keram
            blk(typ, L * 0.7, Wd, Hh, x, y, 0.02, body, rot=rot)
            for s in (-1, 1):
                ox, oy = (s * L * 0.4, 0) if rot == 0 else (0, s * L * 0.4)
                blk(typ + '_e', L * 0.2, Wd * 1.02, Hh * 1.02, x + ox, y + oy, 0.0, tenn, rot=rot)
        elif typ == 'choke':
            blk('drossel', 8.0, 8.0, 5.2, x, y, 0.05, ferrit, bev=0.6)
            blk('drossel_ben', 8.4, 1.0, 0.25, x, y - 4.4, 0.0, tenn)
            if lab == 'L3':
                anchors['vrm'] = (x, y, 5.2)
        elif typ == 'mosfet':
            blk('mosfet', 5.0, 6.0, 1.0, x, y, 0.05, epoxi, bev=0.15)
            for k in range(4):
                blk('mosfet_ben', 0.5, 1.1, 0.25, x - 1.9 + k * 1.27, y - 3.2, 0.0, tenn)
        elif typ == 'polycap':
            c = lathe('polycap', [(0.0, 9.0 * MM), (3.6 * MM, 9.0 * MM), (3.95 * MM, 8.7 * MM), (4.0 * MM, 8.2 * MM),
                                  (4.0 * MM, 1.0 * MM), (3.9 * MM, 0.8 * MM), (4.1 * MM, 0.6 * MM), (4.1 * MM, 0.0)], steps=48)
            c.location = (x * MM, y * MM, 0)
            assign(c, alu)
            # krysset i toppen
            for ang in (45, 135):
                k = blk('polycap_kryss', 6.0, 0.35, 0.08, x, y, 8.97, epoxi, rot=ang)
        elif typ == 'led':
            blk('led_bas', 1.6, 0.8, 0.28, x, y, 0.0, vit)
            blk('led_die', 0.32, 0.32, 0.12, x, y, 0.28, die)
            blk('led_lins', 1.5, 0.75, 0.34, x, y, 0.28, klar, bev=0.05)
            ld = bpy.data.lights.new('led_ljus', 'POINT')
            ld.energy = 0.035
            ld.color = (1.0, 0.36, 0.1)
            ld.shadow_soft_size = 0.0005
            lo = bpy.data.objects.new('led_ljus', ld)
            link(lo)
            lo.location = (x * MM, y * MM, 0.9 * MM)
            anchors['led'] = (x, y, 0.5)
        elif typ == 'fan':
            # 4-polig flaktkontakt: golv, vaggar, nyckel och stift
            blk('flakt_golv', 10.6, 5.8, 0.8, x, y, 0.0, nylon)
            blk('flakt_bak', 10.6, 0.7, 6.2, x, y + 2.55, 0.0, nylon, bev=0.1)
            blk('flakt_v', 0.7, 5.8, 6.2, x - 4.95, y, 0.0, nylon, bev=0.1)
            blk('flakt_h', 0.7, 5.8, 6.2, x + 4.95, y, 0.0, nylon, bev=0.1)
            blk('flakt_nyckel', 7.6, 0.9, 6.2, x - 0.0, y + 1.8, 0.0, nylon)
            for k in range(4):
                blk('flakt_stift', 0.64, 0.64, 7.0, x - 3.81 + k * 2.54, y - 0.6, 0.0, guld, bev=0.08)
            anchors['flakt'] = (x, y, 6.2)
    anchors['ekg'] = (-60.0, cy + 14.0, 0.0)
    world_studio(sc, 0.002)
    return anchors


def lights():
    # stor softbox bakom kortet: dess spegling i lodmasken och locket ger ytan
    l = area_light('bak', (0.02, 0.26, 0.16), (0.0, 0.0, 0.0), 0.6, 9.0, size_y=0.3, spread=120)
    # nyckel fran vanster, lag, ritar komponenternas kanter
    area_light('nyckel', (-0.30, 0.02, 0.10), (0.0, 0.0, 0.0), 0.12, 2.6, color=(1.0, 0.97, 0.94), spread=60)
    # svag fyllnad framifran
    area_light('fyll', (0.10, -0.32, 0.20), (0.0, 0.0, 0.0), 0.3, 0.5, spread=90)
    # varmt kantljus fran hoger: knappt synligt, ger drosslarna en varm kant
    # reflexskarm som bara syns i processorlocket, sa att gravyren gar att lasa mot en ljus gradient
    r = area_light('refl_ihs', (0.25, 0.21, 0.165), (CPU[0] * MM, CPU[1] * MM, 0.004), 0.16, 0.7, size_y=0.05, spread=30)
    r.visible_camera = False
    r.visible_diffuse = False
    rc = bpy.data.collections.new('refl_mottagare')
    rc.objects.link(bpy.data.objects['ihs'])
    r.light_linking.receiver_collection = rc
    k = area_light('kant', (0.26, 0.12, 0.05), (0.0, 0.02, 0.0), 0.06, 1.6, color=(1.0, 0.62, 0.38), spread=40)


def aov_output(sc, out):
    vl = bpy.context.view_layer
    av = vl.aovs.add()
    av.name = 'heat'
    av.type = 'VALUE'
    sc.use_nodes = True
    tree = sc.node_tree
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    rl = tree.nodes.new('CompositorNodeRLayers')
    comp = tree.nodes.new('CompositorNodeComposite')
    tree.links.new(rl.outputs['Image'], comp.inputs['Image'])
    fo = tree.nodes.new('CompositorNodeOutputFile')
    fo.base_path = os.path.dirname(out)
    fo.format.file_format = 'OPEN_EXR'
    fo.format.color_depth = '32'
    fo.file_slots[0].path = os.path.splitext(os.path.basename(out))[0] + '_heat'
    tree.links.new(rl.outputs['heat'], fo.inputs[0])


if __name__ == '__main__':
    sc = reset()
    setup_render(sc, W_, H_, samples=SAMPLES, noise=0.01, exposure=EXPO)
    sc.cycles.transparent_max_bounces = 8
    anchors = build(sc)
    lights()
    tgt = (-14 * MM, 4 * MM, 0.0)
    foc = empty('fokus', (CPU[0] * MM - 8 * MM, CPU[1] * MM - 4 * MM, 4.5 * MM))
    cam = camera('kamera', (-0.095, -0.088, 0.078), tgt, lens=55, fstop=FSTOP, focus=foc)
    aov_output(sc, OUT)
    # ankare i bildkoordinater (0..1, origo uppe till vanster)
    from bpy_extras.object_utils import world_to_camera_view
    sc.frame_set(1)
    res = {}
    for k_, (x, y, z) in anchors.items():
        v = world_to_camera_view(sc, cam, Vector((x * MM, y * MM, z * MM)))
        res[k_] = [round(v.x, 4), round(1 - v.y, 4)]
    with open(os.path.splitext(OUT)[0] + '_ankare.json', 'w') as f:
        json.dump(res, f)
    print('ANKARE', res)
    render_still(sc, OUT)
    # AOV:n som 16-bitars PGM (gratoner, linjar 0..1), lattare att lasa an EXR pa Macen
    import glob, struct
    exr = sorted(glob.glob(os.path.splitext(OUT)[0] + '_heat*.exr'))[-1]
    im = bpy.data.images.load(exr)
    w, h = im.size
    px = list(im.pixels)
    rows = []
    for y in range(h - 1, -1, -1):
        base = y * w * 4
        rows.append(b''.join(struct.pack('>H', max(0, min(65535, int(px[base + x * 4] * 65535)))) for x in range(w)))
    with open(os.path.splitext(OUT)[0] + '_heat.pgm', 'wb') as f:
        f.write(b'P5 %d %d 65535\n' % (w, h))
        f.write(b''.join(rows))
    print('HEAT', exr, w, h)
    open(OUT + '.klar', 'w').write('ok')
