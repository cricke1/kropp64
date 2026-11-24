"""Riggen: överkroppen som ett PC-chassi (Blender 4.5, Cycles). Modell till webbens riggvy och en stillbild.

Hjärtat är processorn med tornkylare, lungorna två fläktar, revbenen kylflänsar, mellangärdet ett
PSU-skydd och nätaggregatet (headroom) sitter i buken. Allt i meter och ungefär i verklig skala:
bålen är 43 cm bred och 69 cm hög, chassit 22 cm djupt.

Körs på Lenovon:
  blender -b -P rigg.py -- <utmapp> [bredd hojd samples]
Skriver <utmapp>/kropp64-rigg.glb (Draco, bakad AO) och <utmapp>/rigg-still.png, plus klar.txt med tider.

Namngivna objekt som webben animerar: hjarta_cpu, flakt_vanster (+ flakt_vanster_rotor),
flakt_hoger (+ flakt_hoger_rotor), kylflans, psu_matare, chassi, glas.
Material som webben byter eller styr: glas, psu_skarm, hjarta_glod, led_list, led_strom.
Vänster och höger är kroppens egna: vänster lunga (den mindre, 120 mm, bredvid hjärtat) sitter på +X,
alltså till höger sett framifrån.
"""
import bpy, bmesh, math, os, re, sys, time
from mathutils import Matrix, Vector

T0 = time.time()
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = ARGS[0] if ARGS else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ut')
W = int(ARGS[1]) if len(ARGS) > 1 else 2400
H = int(ARGS[2]) if len(ARGS) > 2 else 1200
SAMPLES = int(ARGS[3]) if len(ARGS) > 3 else 384
os.makedirs(OUT, exist_ok=True)
TIDER = {}


def tid(namn):
    TIDER[namn] = round(time.time() - T0, 1)
    print(f'RIGG {namn} {TIDER[namn]} s', flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene
COLL = SC.collection

D = 0.22           # chassits djup (Y)
YF = -D / 2        # framkanten (glaset), mot kameran
YB = D / 2         # bakkanten
Y_PCB = 0.083      # moderkortets framsida


# ------------------------------------------------------------------ material

def srgb(h):
    h = h.lstrip('#')
    def f(v):
        v = int(v, 16) / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (f(h[0:2]), f(h[2:4]), f(h[4:6]))


def mat(name, color, metal=0.0, rough=0.5, emis=None, emis_str=0.0, transm=0.0, coat=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    b.inputs['Specular IOR Level'].default_value = spec
    if transm:
        b.inputs['Transmission Weight'].default_value = transm
        b.inputs['IOR'].default_value = 1.5
    if coat:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = 0.08
    if emis:
        b.inputs['Emission Color'].default_value = (*emis, 1)
        b.inputs['Emission Strength'].default_value = emis_str
    return m


M = {
    'alu': mat('alu_borstad', (0.80, 0.81, 0.83), metal=1.0, rough=0.30),
    'alu_mork': mat('alu_mork', (0.16, 0.17, 0.18), metal=1.0, rough=0.38),
    'stal': mat('stal_anodiserad', srgb('#2a3036'), metal=0.6, rough=0.4),
    'pcb': mat('pcb', srgb('#121618'), metal=0.0, rough=0.5),
    'flans': mat('flans_alu', (0.74, 0.76, 0.79), metal=1.0, rough=0.34),
    'koppar': mat('koppar', (0.93, 0.62, 0.50), metal=1.0, rough=0.26),
    'nickel': mat('nickel', (0.80, 0.78, 0.75), metal=1.0, rough=0.18),
    'ram': mat('flakt_ram', srgb('#1b1f22'), metal=0.0, rough=0.62),
    'blad': mat('flakt_blad', srgb('#202427'), metal=0.0, rough=0.48, coat=0.2),
    'gummi': mat('gummi', srgb('#0b0c0d'), metal=0.0, rough=0.85),
    'kabel': mat('kabel', srgb('#24282b'), metal=0.0, rough=0.72),
    'psu': mat('psu_hus', srgb('#121517'), metal=0.4, rough=0.5),
    'skarm': mat('psu_skarm', srgb('#070809'), metal=0.0, rough=0.12, emis=srgb('#4cc38a'), emis_str=0.0),
    'glas': mat('glas', (0.92, 0.95, 0.96), metal=0.0, rough=0.02, transm=1.0),
    'glod': mat('hjarta_glod', srgb('#4cc38a'), metal=0.0, rough=0.4, emis=srgb('#4cc38a'), emis_str=4.0),
    'led_list': mat('led_list', (0.9, 0.88, 0.84), emis=(1.0, 0.93, 0.84), emis_str=6.0),
    'led_strom': mat('led_strom', srgb('#4cc38a'), emis=srgb('#4cc38a'), emis_str=3.0),
    'port': mat('port', srgb('#050606'), metal=0.0, rough=0.7),
}


# ------------------------------------------------------------------ geometrihjälp

def link(ob):
    COLL.objects.link(ob)
    return ob


def obj(name, bm, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    return link(bpy.data.objects.new(name, me))


def to_plane(u, v, a, axis):
    if axis == 'y':
        return Vector((u, a, v))
    if axis == 'z':
        return Vector((u, v, a))
    return Vector((a, u, v))


def prism(name, poly, axis, a0, a1, m, bevel=0.0, seg=2, smooth=30):
    """Polygon (u,v) i planet vinkelrätt mot axeln, extruderat från a0 till a1, med lock."""
    bm = bmesh.new()
    lo = [bm.verts.new(to_plane(u, v, a0, axis)) for u, v in poly]
    hi = [bm.verts.new(to_plane(u, v, a1, axis)) for u, v in poly]
    bm.faces.new(lo)
    bm.faces.new(hi[::-1])
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = obj(name, bm, [m])
    if bevel:
        bev(ob, bevel, seg)
    shade(ob, smooth)
    return ob


def ring_prism(name, outer, inner, axis, a0, a1, m, smooth=30):
    """Ring mellan två slingor med lika många punkter, extruderad."""
    bm = bmesh.new()
    n = len(outer)
    oa = [bm.verts.new(to_plane(u, v, a0, axis)) for u, v in outer]
    ob_ = [bm.verts.new(to_plane(u, v, a1, axis)) for u, v in outer]
    ia = [bm.verts.new(to_plane(u, v, a0, axis)) for u, v in inner]
    ib = [bm.verts.new(to_plane(u, v, a1, axis)) for u, v in inner]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((oa[i], oa[j], ia[j], ia[i]))
        bm.faces.new((ob_[i], ib[i], ib[j], ob_[j]))
        bm.faces.new((oa[i], ob_[i], ob_[j], oa[j]))
        bm.faces.new((ia[i], ia[j], ib[j], ib[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = obj(name, bm, [m])
    shade(o, smooth)
    return o


def bev(ob, width, seg=2):
    md = ob.modifiers.new('bev', 'BEVEL')
    md.width = width
    md.segments = seg
    md.limit_method = 'ANGLE'
    md.angle_limit = math.radians(40)
    md.harden_normals = False
    apply(ob)


def apply(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)


def shade(ob, angle=30):
    me = ob.data
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(angle))


def box(name, sx, sy, sz, loc, m, bevel=0.0, r=0.0):
    """Låda med valfri hörnradie i XZ-planet (r) och fas på kanterna."""
    poly = rrect(sx, sz, r) if r else [(-sx / 2, -sz / 2), (sx / 2, -sz / 2), (sx / 2, sz / 2), (-sx / 2, sz / 2)]
    ob = prism(name, poly, 'y', -sy / 2, sy / 2, m, bevel=bevel)
    ob.location = loc
    return ob


def cyl(name, r, depth, loc, m, axis='y', verts=32, bevel=0.0):
    poly = [(r * math.cos(2 * math.pi * i / verts), r * math.sin(2 * math.pi * i / verts)) for i in range(verts)]
    ob = prism(name, poly, axis, -depth / 2, depth / 2, m, bevel=bevel, smooth=50)
    ob.location = loc
    return ob


def rrect(w, h, r, n=6, cx=0.0, cy=0.0):
    r = min(r, w / 2 - 1e-5, h / 2 - 1e-5)
    pts = []
    for k, (sx, sy, a0) in enumerate([(1, -1, -90), (1, 1, 0), (-1, 1, 90), (-1, -1, 180)]):
        ccx, ccy = cx + sx * (w / 2 - r), cy + sy * (h / 2 - r)
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def superellipse(s, n=64, p=7.0, cx=0.0, cy=0.0, phase=0.0):
    out = []
    for i in range(n):
        t = phase + 2 * math.pi * i / n
        c, si = math.cos(t), math.sin(t)
        rr = s / ((abs(c) ** p + abs(si) ** p) ** (1 / p))
        out.append((cx + rr * c, cy + rr * si))
    return out


def circle(r, n=64, cx=0.0, cy=0.0, phase=0.0):
    return [(cx + r * math.cos(phase + 2 * math.pi * i / n), cy + r * math.sin(phase + 2 * math.pi * i / n)) for i in range(n)]


def tube(name, pts, r, m, res=10, caps=True):
    """Rör längs en polyline (kablar, värmerör)."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts):
        p.co = (q[0], q[1], q[2], 1)
    cu.bevel_depth = r
    cu.bevel_resolution = max(1, res // 4)
    cu.use_fill_caps = caps
    co = link(bpy.data.objects.new(name + '_kurva', cu))
    co.data.materials.append(m)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(co.evaluated_get(dg))
    bpy.data.objects.remove(co)
    ob = link(bpy.data.objects.new(name, me))
    shade(ob, 50)
    return ob


def bezier_pts(p0, p1, p2, p3, n=24):
    out = []
    for i in range(n + 1):
        t = i / n
        a = [(1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3]
        out.append(tuple(a[0] * p0[k] + a[1] * p1[k] + a[2] * p2[k] + a[3] * p3[k] for k in range(3)))
    return out


def catmull(pts, n=8):
    out = []
    P = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in range(2)))
    out.append(pts[-1])
    return out


def arc(cx, cy, r, a0, a1, n=8):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def join(obs, name):
    obs = [o for o in obs if o]
    for o in obs:
        bake_transform(o)
    bpy.context.view_layer.update()
    with bpy.context.temp_override(active_object=obs[0], object=obs[0], selected_objects=obs, selected_editable_objects=obs):
        bpy.ops.object.join()
    o = obs[0]
    o.name = name
    o.data.name = name
    return o


def set_origin(ob, p):
    """Flytta objektets origo till p (världskoordinater) utan att geometrin flyttar sig."""
    p = Vector(p)
    off = p - ob.location
    ob.data.transform(Matrix.Translation(-off))
    ob.location = ob.location + off


def bake_transform(ob):
    ob.data.transform(ob.matrix_basis)
    ob.matrix_basis.identity()


# ------------------------------------------------------------------ bålens kontur (XZ, framifrån)

def kontur():
    hoger = [(0.0, 0.0), (0.12, 0.0)]
    hoger += arc(0.12, 0.035, 0.035, -90, 0, 6)[1:]
    sida = catmull([(0.155, 0.035), (0.166, 0.10), (0.151, 0.20), (0.163, 0.28), (0.197, 0.38),
                    (0.219, 0.47), (0.228, 0.54)], 7)
    hoger += sida[1:]
    hoger += arc(0.176, 0.54, 0.052, 0, 90, 8)[1:]
    topp = catmull([(0.176, 0.592), (0.13, 0.606), (0.08, 0.622), (0.0, 0.630)], 6)
    hoger += topp[1:]
    vanster = [(-x, z) for x, z in reversed(hoger[1:-1])]
    return hoger + vanster


KONTUR = kontur()


def halvbredd(z):
    """Kroppens halva innerbredd på höjden z, ur konturen."""
    best = 0.0
    P = KONTUR
    for i in range(len(P)):
        (x0, z0), (x1, z1) = P[i], P[(i + 1) % len(P)]
        if (z0 - z) * (z1 - z) <= 0 and z0 != z1:
            x = x0 + (z - z0) / (z1 - z0) * (x1 - x0)
            best = max(best, x)
    return best


def ngon_inset(poly, y, inset, keep='inner'):
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z)) for x, z in poly]
    f = bm.faces.new(vs)
    res = bmesh.ops.inset_region(bm, faces=[f], thickness=inset, use_even_offset=True)
    if keep == 'inner':
        bmesh.ops.delete(bm, geom=res['faces'], context='FACES')
    else:
        bmesh.ops.delete(bm, geom=[f], context='FACES_ONLY')
    return bm


def solidify(ob, t, offset=1.0):
    md = ob.modifiers.new('sol', 'SOLIDIFY')
    md.thickness = t
    md.offset = offset
    md.use_even_offset = True
    apply(ob)


# ------------------------------------------------------------------ chassit

statiska = []

# väggarna: konturen extruderad i djupled, 5 mm gods utåt
bm = bmesh.new()
fr = [bm.verts.new((x, YF, z)) for x, z in KONTUR]
bk = [bm.verts.new((x, YB, z)) for x, z in KONTUR]
for i in range(len(KONTUR)):
    j = (i + 1) % len(KONTUR)
    bm.faces.new((fr[i], bk[i], bk[j], fr[j]))
vagg = obj('vaggar', bm, [M['alu']])
solidify(vagg, 0.005, 1.0)
bev(vagg, 0.0016, 3)
shade(vagg, 30)
statiska.append(vagg)

# frontram 12 mm runt glaset, 4 mm tjock mot kameran
bm = ngon_inset(KONTUR, YF, 0.012, keep='ring')
ram = obj('frontram', bm, [M['alu']])
solidify(ram, 0.004, 1.0)
for f in ram.data.polygons:
    pass
bev(ram, 0.0012, 2)
shade(ram, 30)
statiska.append(ram)

# baksida
bm = bmesh.new()
vs = [bm.verts.new((x, YB, z)) for x, z in reversed(KONTUR)]
bm.faces.new(vs)
bak = obj('baksida', bm, [M['alu']])
solidify(bak, 0.004, 1.0)
bev(bak, 0.0012, 2)
statiska.append(bak)

# moderkortsplåten (tray) strax bakom moderkortet
bm = ngon_inset(KONTUR, 0.089, 0.003, keep='inner')
for f in bm.faces:
    f.normal_flip()
tray = obj('tray', bm, [M['stal']])
solidify(tray, 0.003, 1.0)
statiska.append(tray)

# glaset, 4 mm, inpassat bakom frontramen
bm = ngon_inset(KONTUR, YF + 0.0008, 0.010, keep='inner')
for f in bm.faces:
    f.normal_flip()
glas = obj('glas', bm, [M['glas']])
solidify(glas, 0.004, 1.0)
bev(glas, 0.0008, 1)
shade(glas, 30)

# tumskruvar i frontramen
for x, z in [(-0.115, 0.006), (0.115, 0.006), (-0.150, 0.5975), (0.150, 0.5975)]:
    s = cyl('skruv', 0.0055, 0.006, (x, YF - 0.007, z), M['alu'], bevel=0.0008)
    statiska.append(s)

# halsen: I/O-blocket ovanpå axlarna
HY = 0.062   # halsens halva djup, framsidan vid y=-HY
hals_poly = [(x * 0.054 / 0.06, y * HY / 0.06) for x, y in superellipse(0.06, 64, 3.2)]
hals = prism('hals', hals_poly, 'z', 0.60, 0.695, M['alu'], bevel=0.004, seg=3, smooth=40)
statiska.append(hals)
YH = -HY + 0.0012
knapp = cyl('stromknapp', 0.0072, 0.004, (0.0, YH - 0.0012, 0.668), M['alu'], bevel=0.0008)
ring_strom = ring_prism('ledring', circle(0.0095, 40), circle(0.0080, 40), 'y', YH, YH - 0.0012, M['led_strom'])
ring_strom.location = (0.0, 0, 0.668)
for o in (knapp, ring_strom):
    statiska.append(o)
for x in (-0.026, 0.026):
    statiska.append(box('usbc', 0.0088, 0.003, 0.0032, (x, YH + 0.0003, 0.668), M['port'], r=0.0015))
statiska.append(box('usba', 0.0125, 0.003, 0.0048, (0.0, YH + 0.0003, 0.648), M['port'], r=0.0005))

# ljuslist under axlarna, bakom glaset
statiska.append(box('ljuslist_hus', 0.24, 0.008, 0.006, (0, -0.088, 0.583), M['alu_mork'], r=0.002))
statiska.append(box('ljuslist', 0.232, 0.002, 0.0025, (0, -0.0925, 0.581), M['led_list'], r=0.001))

# moderkortet
pcb = prism('pcb', rrect(0.27, 0.39, 0.012), 'y', Y_PCB, Y_PCB + 0.0016, M['pcb'], smooth=20)
pcb.location = (0, 0, 0.37)
statiska.append(pcb)
for x, z in [(-0.125, 0.185), (0.125, 0.185), (-0.125, 0.555), (0.125, 0.555), (0.0, 0.555), (0.0, 0.185)]:
    statiska.append(cyl('pcbskruv', 0.0035, 0.002, (x, Y_PCB - 0.001, z), M['nickel']))

# hjärtats placering
HX, HZ = 0.024, 0.302
# sockel och spänningsregleringens kylflänsar runt
statiska.append(box('sockel', 0.056, 0.004, 0.056, (HX, Y_PCB - 0.002, HZ), M['stal'], r=0.003))
statiska.append(box('vrm_v', 0.012, 0.018, 0.095, (HX - 0.058, Y_PCB - 0.009, HZ + 0.005), M['alu_mork'], bevel=0.0012, r=0.002))
statiska.append(box('vrm_o', 0.085, 0.016, 0.011, (HX + 0.002, Y_PCB - 0.008, HZ + 0.067), M['alu_mork'], bevel=0.0012, r=0.002))
# minnen bredvid processorn
for i in range(2):
    x = HX + 0.062 + i * 0.011
    statiska.append(box(f'ram{i}', 0.0065, 0.032, 0.105, (x, Y_PCB - 0.016, HZ), M['alu_mork'], bevel=0.0008, r=0.001))
    statiska.append(box(f'ramkant{i}', 0.0068, 0.004, 0.103, (x, Y_PCB - 0.034, HZ), M['nickel'], bevel=0.0006, r=0.001))
# M.2-kylare och några kondensatorer
statiska.append(box('m2', 0.03, 0.006, 0.075, (-0.075, Y_PCB - 0.003, 0.24), M['alu_mork'], bevel=0.001, r=0.003))
for k in range(6):
    statiska.append(cyl('kond', 0.0035, 0.008, (HX + 0.006 + k * 0.009, Y_PCB - 0.004, HZ - 0.058), M['alu_mork'], verts=16))

# mellangärdet: välvt PSU-skydd
hw = halvbredd(0.16) - 0.006
bm = bmesh.new()
NU, NV = 28, 10
grid = []
for j in range(NV + 1):
    row = []
    y = YF + 0.006 + (0.086 - YF - 0.006) * j / NV
    for i in range(NU + 1):
        u = -1 + 2 * i / NU
        z = 0.158 + 0.02 * (1 - u * u) ** 1.2 * (0.6 + 0.4 * math.sin(math.pi * j / NV))
        row.append(bm.verts.new((u * hw, y, z)))
    grid.append(row)
for j in range(NV):
    for i in range(NU):
        bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
diafragma = obj('mellangarde', bm, [M['stal']])
solidify(diafragma, 0.003, -1.0)
bev(diafragma, 0.001, 2)
shade(diafragma, 40)
statiska.append(diafragma)
GROMMETS = [(0.036, 0.045), (-0.095, 0.03), (0.105, 0.03)]
for gx, gy in GROMMETS:
    u = gx / hw
    z = 0.158 + 0.02 * (1 - u * u) ** 1.2 * 0.95
    g = ring_prism('genomforing', superellipse(0.016, 40, 4), superellipse(0.0105, 40, 4), 'z', z - 0.001, z + 0.004, M['gummi'], smooth=60)
    g.location = (gx, gy, 0)
    bake_transform(g)
    statiska.append(g)

# stativ och fot
statiska.append(cyl('stativ', 0.022, 0.058, (0, 0, -0.028), M['alu'], axis='z', verts=48, bevel=0.0015))
fot = prism('fot', rrect(0.30, 0.20, 0.07, n=10), 'z', -0.07, -0.057, M['stal'], bevel=0.003, seg=3)
statiska.append(fot)
statiska.append(prism('fotgummi', rrect(0.29, 0.19, 0.065, n=10), 'z', -0.072, -0.07, M['gummi']))

# fläktfästen (stöd från moderkortet till fläktarnas hörn)
FLAKTAR = {'hoger': (-0.095, 0.460, 0.150, 9), 'vanster': (0.110, 0.450, 0.120, 7)}
YFL = -0.004
for k, (fx, fz, s, _) in FLAKTAR.items():
    for dx, dz in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        px, pz = fx + dx * (s / 2 - 0.0075), fz + dz * (s / 2 - 0.0075)
        statiska.append(cyl('stod', 0.0028, Y_PCB - (YFL + 0.0125), (px, (Y_PCB + YFL + 0.0125) / 2, pz), M['nickel'], verts=12))

tid('chassi')

# ------------------------------------------------------------------ hjärtat: processor med tornkylare

hjarta = []
SX, SZ = 0.088, 0.102
Y_STACK0, Y_STACK1 = 0.058, -0.040
hjarta.append(box('bas', 0.05, 0.012, 0.048, (HX, Y_PCB - 0.0075, HZ), M['koppar'], bevel=0.001, r=0.002))
hjarta.append(box('fastbygel', 0.095, 0.004, 0.012, (HX, Y_PCB - 0.0155, HZ), M['alu_mork'], bevel=0.0008, r=0.002))
N_FENOR = 30
for i in range(N_FENOR):
    y = Y_STACK0 + (Y_STACK1 - Y_STACK0) * i / (N_FENOR - 1)
    fena = prism('fena', rrect(SX, SZ, 0.004, 4), 'y', y - 0.0004, y + 0.0004, M['flans'], smooth=30)
    fena.location = (HX, 0, HZ)
    hjarta.append(fena)
# värmerör: tre U-rör, sex toppar
for a, dz in [(0.011, -0.013), (0.024, 0.0), (0.037, 0.013)]:
    yb, rb, yt = Y_PCB - 0.006, 0.008, Y_STACK1 - 0.006
    pts = [(HX - a, yt, HZ + dz), (HX - a, yb - rb, HZ + dz)]
    for i in range(1, 7):
        t = math.radians(90 * i / 6)
        pts.append((HX - a + rb * (1 - math.cos(t)), yb - rb + rb * math.sin(t), HZ + dz))
    for i in range(0, 7):
        t = math.radians(90 * i / 6)
        pts.append((HX + a - rb + rb * math.sin(t), yb - rb * (1 - math.cos(t)), HZ + dz))
    pts.append((HX + a, yt, HZ + dz))
    hjarta.append(tube('varmeror', pts, 0.003, M['koppar'], res=12))
    for sx in (-1, 1):
        hjarta.append(cyl('rortopp', 0.0036, 0.004, (HX + sx * a, Y_STACK1 - 0.008, HZ + dz), M['nickel'], verts=20, bevel=0.0008))
# topplocket mot glaset och glödlisten runt
lock = prism('lock', rrect(SX + 0.006, SZ + 0.006, 0.007, 6), 'y', Y_STACK1 - 0.006, Y_STACK1 - 0.001, M['alu_mork'], bevel=0.0015, seg=3)
lock.location = (HX, 0, HZ)
hjarta.append(lock)
glod = ring_prism('glodlist', rrect(SX - 0.004, SZ - 0.004, 0.005, 6), rrect(SX - 0.008, SZ - 0.008, 0.003, 6), 'y',
                  Y_STACK1 - 0.0062, Y_STACK1 - 0.0068, M['glod'])
glod.location = (HX, 0, HZ)
hjarta.append(glod)
for o in hjarta:
    bake_transform(o)
hjarta_cpu = join(hjarta, 'hjarta_cpu')
set_origin(hjarta_cpu, (HX, Y_PCB, HZ))
tid('hjarta')

# ------------------------------------------------------------------ lungorna: två fläktar


def flakt(namn, fx, fz, s, nblad):
    delar = []
    yc = YFL
    t = 0.025
    yr0, yr1 = yc - t / 2, yc + t / 2
    n = 72
    outer = superellipse(s / 2, n, 7.5, fx, fz, math.radians(2.5))
    inner = circle(s * 0.47, n, fx, fz, math.radians(2.5))
    delar.append(ring_prism(namn + '_ram', outer, inner, 'y', yr0, yr1, M['ram'], smooth=35))
    # gummihörn
    for dx, dz in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        c = (fx + dx * (s / 2 - 0.009), fz + dz * (s / 2 - 0.009))
        g = prism('horn', superellipse(0.0075, 20, 3, *c), 'y', yr0 - 0.0006, yr0 + 0.004, M['gummi'], smooth=60)
        delar.append(g)
    # motorhus och fyra stag på baksidan
    delar.append(cyl('motor', s * 0.2, 0.008, (fx, yr1 - 0.004, fz), M['ram'], verts=40, bevel=0.001))
    for k in range(4):
        a = math.radians(45 + 90 * k)
        L = s * 0.47 - s * 0.19
        mx, mz = fx + math.cos(a) * (s * 0.19 + L / 2), fz + math.sin(a) * (s * 0.19 + L / 2)
        st = box('stag', L + 0.004, 0.003, 0.004, (mx, yr1 - 0.0015, mz), M['ram'])
        st.rotation_euler = (0, -a, 0)
        bake_transform(st)
        delar.append(st)
    ram = join(delar, namn)
    # rotorn: nav + blad
    rot = []
    rh, rt = s * 0.19, s * 0.455
    nav = cyl('nav', rh, 0.012, (fx, yc - 0.002, fz), M['blad'], verts=48, bevel=0.002)
    rot.append(nav)
    navlock = cyl('navlock', rh * 0.82, 0.0012, (fx, yc - 0.0086, fz), M['alu_mork'], verts=48, bevel=0.0004)
    rot.append(navlock)
    R, A = 7, 6
    for k in range(nblad):
        th0 = 2 * math.pi * k / nblad
        bm = bmesh.new()
        g = []
        for i in range(R + 1):
            f = i / R
            r = rh * 0.96 + (rt - rh * 0.96) * f
            thc = th0 + 0.42 * f ** 1.3
            w = (2 * math.pi / nblad) * (0.62 + 0.22 * f)
            row = []
            for j in range(A + 1):
                q = j / A - 0.5
                th = thc + q * w
                y = yc - 0.002 + q * 0.016 * (1 - 0.35 * f) - 0.002 * math.sin(math.pi * (j / A))
                row.append(bm.verts.new((fx + r * math.cos(th), y, fz + r * math.sin(th))))
            g.append(row)
        for i in range(R):
            for j in range(A):
                bm.faces.new((g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]))
        b = obj('blad', bm, [M['blad']])
        solidify(b, 0.0014, 0.0)
        shade(b, 60)
        rot.append(b)
    rotor = join(rot, namn + '_rotor')
    set_origin(rotor, (fx, yc, fz))
    set_origin(ram, (fx, yc, fz))
    rotor.parent = ram
    rotor.location = rotor.location - ram.location
    return ram, rotor


flakt_hoger, rotor_h = flakt('flakt_hoger', *FLAKTAR['hoger'])
flakt_vanster, rotor_v = flakt('flakt_vanster', *FLAKTAR['vanster'])
tid('flaktar')

# ------------------------------------------------------------------ revbenen: kylflänsar med värmerör

fl = []
ZF = [0.232 + 0.0215 * i for i in range(16)]
YC, BY, TR, TH = -0.006, 0.088, 0.020, 0.0045
PHI0, PHI1, NS = 34, 128, 22
for sx in (-1, 1):
    for z in ZF:
        a = halvbredd(z + TH / 2) - 0.010
        bm = bmesh.new()
        rings = []
        for s in range(NS + 1):
            ph = math.radians(PHI0 + (PHI1 - PHI0) * s / NS)
            o = (sx * a * math.sin(ph), YC + BY * math.cos(ph))
            ii = (sx * (a - TR) * math.sin(ph), YC + (BY - TR) * math.cos(ph))
            rings.append([bm.verts.new((o[0], o[1], z)), bm.verts.new((ii[0], ii[1], z)),
                          bm.verts.new((ii[0], ii[1], z + TH)), bm.verts.new((o[0], o[1], z + TH))])
        for s in range(NS):
            A_, B_ = rings[s], rings[s + 1]
            for k in range(4):
                m_ = (k + 1) % 4
                bm.faces.new((A_[k], B_[k], B_[m_], A_[m_]))
        bm.faces.new(rings[0])
        bm.faces.new(rings[-1][::-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        r = obj('revben', bm, [M['flans']])
        shade(r, 35)
        fl.append(r)
    for phd in (66, 100):
        ph = math.radians(phd)
        pts = []
        for i in range(30):
            z = 0.215 + (ZF[-1] + 0.03 - 0.215) * i / 29
            a = halvbredd(z) - 0.010 - TR / 2
            pts.append((sx * a * math.sin(ph), YC + (BY - TR / 2) * math.cos(ph), z))
        fl.append(tube('revror', pts, 0.0034, M['koppar'], res=12))
kylflans = join(fl, 'kylflans')
tid('kylflans')

# ------------------------------------------------------------------ nätaggregatet i buken

psu = []
PSU_Y0, PSU_Y1 = -0.060, 0.082
PSU_Z = 0.044
psu.append(prism('psu_hus', rrect(0.15, 0.086, 0.006, 4), 'y', PSU_Y0, PSU_Y1, M['psu'], bevel=0.002, seg=2))
psu[-1].location = (0, 0, PSU_Z)
# skärmram och skärm (UV 0-1, webben ritar headroom-mätaren här)
sr = ring_prism('skarmram', rrect(0.118, 0.058, 0.004, 4), rrect(0.110, 0.050, 0.002, 4), 'y', PSU_Y0 - 0.0002, PSU_Y0 - 0.0016, M['alu'])
sr.location = (0, 0, PSU_Z)
psu.append(sr)
bm = bmesh.new()
SW, SH = 0.110, 0.050
vs = [bm.verts.new((-SW / 2, PSU_Y0 - 0.0008, PSU_Z - SH / 2)), bm.verts.new((SW / 2, PSU_Y0 - 0.0008, PSU_Z - SH / 2)),
      bm.verts.new((SW / 2, PSU_Y0 - 0.0008, PSU_Z + SH / 2)), bm.verts.new((-SW / 2, PSU_Y0 - 0.0008, PSU_Z + SH / 2))]
f = bm.faces.new(vs)
uvl = bm.loops.layers.uv.new('UVMap')
for loop, uv in zip(f.loops, [(0, 0), (1, 0), (1, 1), (0, 1)]):
    loop[uvl].uv = uv
bm.normal_update()
if f.normal.y > 0:
    f.normal_flip()
skarm = obj('psu_skarm', bm, [M['skarm']])
psu.append(skarm)
# modulära uttag ovanpå
for k, x in enumerate([-0.045, -0.015, 0.03]):
    psu.append(box('uttag', 0.022, 0.012, 0.004, (x, 0.02, PSU_Z + 0.044), M['port'], r=0.001))
psu_matare = join(psu, 'psu_matare')
set_origin(psu_matare, (0, PSU_Y0, PSU_Z))
tid('psu')

# ------------------------------------------------------------------ kablar (statiska, i chassit)

def gz(gx):
    u = gx / hw
    return 0.158 + 0.02 * (1 - u * u) ** 1.2 * 0.95


# EPS till hjärtat: flätad bunt om fyra strängar, från PSU:n genom genomföringen upp under kylaren
for k in range(4):
    ox, oy = (k % 2 - 0.5) * 0.0062, (k // 2 - 0.5) * 0.0062
    p = bezier_pts((-0.045 + ox, 0.022 + oy, PSU_Z + 0.046), (-0.045 + ox, 0.03 + oy, 0.15),
                   (GROMMETS[0][0] - 0.01 + ox, GROMMETS[0][1] + oy, 0.15), (GROMMETS[0][0] + ox, GROMMETS[0][1] + oy, gz(0.036) + 0.004), 16)
    p += bezier_pts(p[-1], (GROMMETS[0][0] + ox, GROMMETS[0][1] + oy, 0.215), (HX - 0.02 + ox, 0.072 + oy * 0.4, 0.225),
                    (HX - 0.02 + ox, 0.072 + oy * 0.4, HZ - 0.052), 18)[1:]
    statiska.append(tube('eps', p, 0.0029, M['kabel'], res=8))
# fläktkablar
for (gx, gy), (k, (fx, fz, s, _)) in zip(GROMMETS[1:], FLAKTAR.items()):
    end = (fx - 0.02 * (1 if fx > 0 else -1), YFL + 0.0125, fz - s / 2 + 0.006)
    p = bezier_pts((0.0 + (0.02 if fx > 0 else -0.02), 0.03, PSU_Z + 0.046), (gx * 0.6, gy, 0.14), (gx, gy, 0.14), (gx, gy, gz(gx) + 0.004), 12)
    p += bezier_pts(p[-1], (gx, gy, 0.26), (end[0], end[1] + 0.01, end[2] - 0.08), end, 18)[1:]
    statiska.append(tube('flaktkabel', p, 0.0018, M['kabel'], res=8))

chassi = join(statiska, 'chassi')
tid('kablar')

# ------------------------------------------------------------------ AO-bakning

for o in bpy.data.objects:
    print('OBJ', o.name, o.type, len(o.data.polygons) if o.type == 'MESH' else '')

SC.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
try:
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
    SC.cycles.device = 'GPU'
except Exception as e:  # noqa: BLE001
    print('OPTIX saknas', e)

world = bpy.data.worlds.new('varld')
SC.world = world
world.light_settings.distance = 0.06


def ensure_uv(ob):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    for o in bpy.data.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004, area_weight=0.0, scale_to_bounds=True)
        bpy.ops.object.mode_set(mode='OBJECT')


def gltf_output_group():
    g = bpy.data.node_groups.get('glTF Material Output')
    if g:
        return g
    g = bpy.data.node_groups.new('glTF Material Output', 'ShaderNodeTree')
    g.interface.new_socket(name='Occlusion', in_out='INPUT', socket_type='NodeSocketFloat')
    g.nodes.new('NodeGroupInput')
    return g


def bake_ao(ob, size, namn):
    ensure_uv(ob)
    img = bpy.data.images.new(namn, size, size, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'Non-Color'
    nya = []
    for i, slot in enumerate(ob.material_slots):
        m = slot.material.copy()
        m.name = slot.material.name + '_' + ob.name
        slot.material = m
        nt = m.node_tree
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        nt.nodes.active = tex
        nya.append((m, tex))
    glas.hide_render = True
    SC.cycles.samples = 256
    SC.render.bake.margin = 6
    for o in bpy.data.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.bake(type='AO')
    glas.hide_render = False
    path = os.path.join(OUT, namn + '.png')
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    grp = gltf_output_group()
    for m, tex in nya:
        nt = m.node_tree
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(tex.outputs['Color'], sep.inputs['Color'])
        gn = nt.nodes.new('ShaderNodeGroup')
        gn.node_tree = grp
        nt.links.new(sep.outputs['Red'], gn.inputs['Occlusion'])


bake_ao(chassi, 2048, 'ao_chassi')
tid('ao_chassi')
bake_ao(kylflans, 1024, 'ao_kylflans')
tid('ao_kylflans')

# ------------------------------------------------------------------ glTF

for o in bpy.data.objects:
    o.select_set(o.type == 'MESH')
EXPORT = dict(
    filepath=os.path.join(OUT, 'kropp64-rigg.glb'), export_format='GLB', use_selection=True,
    export_apply=True, export_yup=True, export_texcoords=True, export_normals=True,
    export_materials='EXPORT', export_image_format='WEBP', export_image_quality=82,
    export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
    export_draco_position_quantization=14, export_draco_normal_quantization=10,
    export_draco_texcoord_quantization=12, export_cameras=False, export_lights=False, export_extras=False,
)
for _ in range(8):
    try:
        bpy.ops.export_scene.gltf(**EXPORT)
        break
    except TypeError as e:  # parameternamn som inte finns i den här exportörversionen
        bad = re.findall(r'"(export_[a-z_]+)"', str(e)) or re.findall(r"'(export_[a-z_]+)'", str(e))
        print('EXPORT parameter saknas', e)
        if not bad:
            raise
        EXPORT.pop(bad[0], None)
tid('glb')

# ------------------------------------------------------------------ stillbild (reservbild i webben)

# bara för stillbilden: borstad aluminium med anisotropi och synlig skärm
for m in bpy.data.materials:
    if m.name.startswith('alu_borstad'):
        m.node_tree.nodes['Principled BSDF'].inputs['Anisotropic'].default_value = 0.55
    if m.name == 'psu_skarm':
        m.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = 0.0

wn = world.node_tree if world.use_nodes else None
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (*srgb('#0e1113'), 1)
bg.inputs['Strength'].default_value = 0.6


def area(name, loc, rot, size, energy, color=(1, 1, 1), shape='RECTANGLE', sy=None):
    li = bpy.data.lights.new(name, 'AREA')
    li.energy = energy
    li.color = color
    li.shape = shape
    li.size = size
    if sy:
        li.size_y = sy
    ob = link(bpy.data.objects.new(name, li))
    ob.location = loc
    ob.rotation_euler = rot
    return ob


def aim(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


k = area('nyckel', (-0.8, -1.0, 1.5), (0, 0, 0), 1.0, 150, (1.0, 0.97, 0.93))
aim(k, (0, 0, 0.35))
r1 = area('kant_h', (1.1, 0.6, 0.9), (0, 0, 0), 0.5, 90, (0.85, 0.92, 1.0), sy=1.2)
aim(r1, (0, 0, 0.35))
r2 = area('kant_v', (-1.0, 0.8, 0.5), (0, 0, 0), 0.4, 60, (0.85, 0.92, 1.0), sy=1.0)
aim(r2, (0, 0, 0.35))
fi = area('fyll', (0.8, -1.4, 0.2), (0, 0, 0), 1.2, 30, (0.95, 0.97, 1.0))
aim(fi, (0, 0, 0.3))
inne = area('inne', (0, -0.05, 0.57), (0, 0, 0), 0.26, 14.0, (1.0, 0.94, 0.86), sy=0.14)
inne.rotation_euler = (0, 0, 0)

golv = bpy.data.meshes.new('golv')
bm = bmesh.new()
bmesh.ops.create_circle(bm, cap_ends=True, radius=3.0, segments=64)
bm.to_mesh(golv)
bm.free()
golvob = link(bpy.data.objects.new('golv', golv))
golvob.location = (0, 0, -0.072)
golv.materials.append(mat('golv', srgb('#101315'), rough=0.6, spec=0.2))

cam_d = bpy.data.cameras.new('kamera')
cam_d.lens = 30  # vid bild: webben beskär den (object-fit: cover) till scenens format
cam_d.sensor_width = 36
cam = link(bpy.data.objects.new('kamera', cam_d))
cam.location = (0.78, -1.62, 0.66)
aim(cam, (0.0, 0.0, 0.31))
SC.camera = cam

SC.cycles.samples = SAMPLES
SC.cycles.use_adaptive_sampling = True
SC.cycles.adaptive_threshold = 0.01
SC.cycles.use_denoising = True
try:
    SC.cycles.denoiser = 'OPTIX'
except Exception:  # noqa: BLE001
    pass
SC.cycles.max_bounces = 10
SC.cycles.transmission_bounces = 8
SC.cycles.blur_glossy = 1.0
SC.render.resolution_x = W
SC.render.resolution_y = H
SC.render.resolution_percentage = 100
SC.view_settings.view_transform = 'AgX'
SC.view_settings.look = 'AgX - Medium High Contrast'
SC.render.image_settings.file_format = 'PNG'
SC.render.image_settings.color_depth = '8'
SC.render.filepath = os.path.join(OUT, 'rigg-still.png')
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.render.render(write_still=True)
tid('still')

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'rigg.blend'))
with open(os.path.join(OUT, 'klar.txt'), 'w') as fh:
    for k_, v in TIDER.items():
        fh.write(f'{k_} {v}\n')
print('RIGG KLAR', TIDER, flush=True)
