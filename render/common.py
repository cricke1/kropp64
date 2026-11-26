"""Gemensamma byggstenar for Konsiliets renderingar (Blender 4.5, Cycles).

Allt i meter och i verklig skala:
  Mac mini (M4, 2024): 127 x 127 x 50 mm
  Pixel Watch 3 (41 mm): diameter 41 mm, tjocklek 12,3 mm
  Android-telefon (Pixel-storlek): 152 x 72 x 8,5 mm
"""
import bpy, bmesh, math, os, sys, time
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
MM = 0.001

# Fargerna ur web/src/styles.css
PAL = {
    'bg': (0x0e, 0x11, 0x13), 'surface': (0x14, 0x18, 0x1b), 'line': (0x26, 0x2d, 0x32),
    'text': (0xe6, 0xe8, 0xe7), 'text2': (0x9b, 0xa4, 0xa9),
    'hr': (0x4c, 0xc3, 0x8a), 'spo2': (0x4f, 0xb3, 0xd9), 'hrv': (0xe0, 0x90, 0x5e),
    'danger': (0xe5, 0x57, 0x4e), 'warn': (0xd9, 0xa0, 0x3f),
}


def srgb(c):
    """(r,g,b) 0-255 sRGB -> linjar RGBA."""
    def f(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (f(c[0]), f(c[1]), f(c[2]), 1.0)


def args():
    a = sys.argv
    return a[a.index('--') + 1:] if '--' in a else []


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    return sc


# ---------------------------------------------------------------- rendering

def setup_render(sc, w, h, samples=512, noise=0.01, out=None, exposure=0.0):
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    # OptiX på NVIDIA (Lenovon), Metal på Mac minin. Avbrusning med OptiX där det finns, annars OpenImageDenoise.
    typ = None
    for kandidat in ('OPTIX', 'METAL', 'CUDA'):
        try:
            prefs.compute_device_type = kandidat
            prefs.get_devices()
            if any(d.type == kandidat for d in prefs.devices):
                typ = kandidat
                for d in prefs.devices:
                    d.use = d.type == kandidat
                break
        except Exception:
            continue
    print('Renderar med', typ or 'CPU')
    cy = sc.cycles
    cy.device = 'GPU' if typ else 'CPU'
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = noise
    cy.use_denoising = True
    cy.denoiser = 'OPTIX' if typ == 'OPTIX' else 'OPENIMAGEDENOISE'
    cy.denoising_use_gpu = True
    cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    cy.max_bounces = 12
    cy.glossy_bounces = 6
    cy.transmission_bounces = 8
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_depth = '16'
    if out:
        sc.render.filepath = out


def render_still(sc, out):
    sc.render.filepath = out
    t = time.time()
    bpy.ops.render.render(write_still=True)
    dt = time.time() - t
    with open(out + '.tid.txt', 'w') as f:
        f.write('%.1f\n' % dt)
    print('RENDERTID %s %.1f s' % (out, dt))
    return dt


# ---------------------------------------------------------------- material

def mat_principled(name, color, rough=0.5, metal=0.0, **kw):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = color
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    for k, v in kw.items():
        b.inputs[k].default_value = v
    return m


def mat_aluminium(name='aluminium', color=(0.80, 0.81, 0.82, 1), rough=0.30):
    """Parlblast aluminium: metall, lag anisotropi-fri strovhet med fint brus."""
    m = mat_principled(name, color, rough, 1.0)
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 4000.0
    nz.inputs['Detail'].default_value = 2.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = rough - 0.04
    mr.inputs['To Max'].default_value = rough + 0.04
    nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.03
    bump.inputs['Distance'].default_value = 0.00005
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def mat_screen(name, img_path, strength=1.0, mask_round=False, black_rough=0.05):
    """Skarm: emissiv bild bakom ett tunt lager glas (coat)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.0, 0.0, 0.0, 1)
    b.inputs['Roughness'].default_value = black_rough
    b.inputs['Coat Weight'].default_value = 1.0
    b.inputs['Coat Roughness'].default_value = 0.02
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(img_path)
    tex.interpolation = 'Cubic'
    tex.extension = 'CLIP'
    uv = nt.nodes.new('ShaderNodeTexCoord')
    nt.links.new(uv.outputs['UV'], tex.inputs['Vector'])
    nt.links.new(tex.outputs['Color'], b.inputs['Emission Color'])
    b.inputs['Emission Strength'].default_value = strength
    return m


def assign(ob, m):
    ob.data.materials.clear()
    ob.data.materials.append(m)


def smooth(ob, angle=35):
    for p in ob.data.polygons:
        p.use_smooth = True
    try:
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
        ob.select_set(False)
    except Exception as e:
        print('smooth', e)


def apply_mods(ob):
    bpy.context.view_layer.objects.active = ob
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def link(ob, coll=None):
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


# ---------------------------------------------------------------- geometri

def rounded_box(name, sx, sy, sz, r_plan, r_edge, seg_plan=16, seg_edge=6, edge_top=True, edge_bot=True):
    """Lada med rundade horn i planet och mjuka kanter upptill/nedtill. Origo i bottenmitten."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx, v.co.y * sy, (v.co.z + 0.5) * sz))
    bw = bm.edges.layers.float.new('bevel_weight_edge')
    for e in bm.edges:
        d = e.verts[0].co - e.verts[1].co
        e[bw] = 1.0 if abs(d.z) > 1e-9 else 0.0
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    m1 = ob.modifiers.new('plan', 'BEVEL')
    m1.limit_method = 'WEIGHT'
    m1.width = r_plan
    m1.segments = seg_plan
    m1.profile = 0.5
    apply_mods(ob)
    if r_edge > 0:
        # Fasa bara de horisontella ytterkanterna i topp/botten
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bw = bm.edges.layers.float.get('bevel_weight_edge') or bm.edges.layers.float.new('bevel_weight_edge')
        for e in bm.edges:
            z0, z1 = e.verts[0].co.z, e.verts[1].co.z
            horiz = abs(z0 - z1) < 1e-9
            top = horiz and abs(z0 - sz) < 1e-9
            bot = horiz and abs(z0) < 1e-9
            on_rim = len(e.link_faces) == 2 and any(abs(f.normal.z) < 0.5 for f in e.link_faces)
            e[bw] = 1.0 if on_rim and ((top and edge_top) or (bot and edge_bot)) else 0.0
        bm.to_mesh(ob.data)
        bm.free()
        m2 = ob.modifiers.new('kant', 'BEVEL')
        m2.limit_method = 'WEIGHT'
        m2.width = r_edge
        m2.segments = seg_edge
        m2.profile = 0.5
        m2.harden_normals = False
        apply_mods(ob)
    smooth(ob, 40)
    return ob


def boolean_cut(target, cutter, solver='EXACT'):
    m = target.modifiers.new('cut', 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.object = cutter
    m.solver = solver
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def slot(name, w, h, depth):
    """Avlang oppning (USB-C) med halvrunda andar, langs Y-axeln i djup."""
    ob = rounded_box(name, w, h, depth, h * 0.499, 0, seg_plan=10)
    # rundad i XY, extruderad i Z -> rotera sa att djupet gar langs -Y
    ob.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.transform_apply(rotation=True)
    ob.select_set(False)
    return ob


def lathe(name, prof, steps=96):
    """Rotationskropp ur profil [(r, z), ...] runt Z-axeln."""
    bm = bmesh.new()
    rings = []
    for (r, z) in prof:
        ring = []
        for i in range(steps):
            a = 2 * math.pi * i / steps
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for i in range(steps):
            j = (i + 1) % steps
            bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
    # lock i botten/topp om radien ar 0
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def parent(children, par):
    for c in children:
        c.parent = par


def empty(name, loc=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    link(e)
    return e


# ---------------------------------------------------------------- Mac mini

def mac_mini(alu=None, led_strength=6.0):
    """Mac mini M4 (2024). Origo i bottenmitten, framsidan mot -Y."""
    W, H = 127 * MM, 50 * MM
    foot_h = 2.2 * MM
    root = empty('MacMini')
    alu = alu or mat_aluminium()
    body = rounded_box('mm_body', W, W, H - foot_h, 21 * MM, 2.4 * MM, seg_plan=20, seg_edge=8)
    body.location.z = foot_h
    bpy.context.view_layer.objects.active = body
    # Portar pa framsidan: tva USB-C till vanster, horlursuttag till hoger, statuslampa langst till hoger
    zc = foot_h + 19.5 * MM
    yf = -W / 2
    cuts = []
    for x in (-44 * MM, -31 * MM):
        s = slot('usbc', 8.6 * MM, 3.0 * MM, 3.6 * MM)
        s.location = (x, yf - 2 * MM + 3.6 * MM, zc)
        cuts.append(s)
    jack = bpy.data.objects.new('jack', bpy.data.meshes.new('jack'))
    link(jack)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=2.9 * MM, radius2=2.9 * MM, depth=7.2 * MM)
    bm.to_mesh(jack.data)
    bm.free()
    jack.rotation_euler = (math.radians(90), 0, 0)
    jack.location = (31 * MM, yf, zc)
    cuts.append(jack)
    bpy.context.view_layer.update()
    for c in cuts:
        # flytta in sa att halva ar inne i kroppen
        boolean_cut(body, c)
    smooth(body, 40)
    assign(body, alu)

    dark = mat_principled('mm_inre', (0.02, 0.02, 0.022, 1), 0.6)
    port_in = mat_principled('mm_port', (0.05, 0.05, 0.055, 1), 0.35, 0.8)
    # insida i portarna: morka plattor bakom hal
    for x in (-44 * MM, -31 * MM):
        tongue = rounded_box('usbc_tunga', 6.6 * MM, 1.2 * MM, 0.7 * MM, 0.3 * MM, 0)
        tongue.location = (x, yf + 1.0 * MM, zc - 0.35 * MM)
        assign(tongue, port_in)
        back = rounded_box('usbc_bak', 9 * MM, 0.5 * MM, 3.4 * MM, 0.2 * MM, 0)
        back.location = (x, yf + 1.5 * MM, zc - 1.7 * MM)
        assign(back, dark)
        parent([tongue, back], root)
    jb = rounded_box('jack_bak', 6.5 * MM, 0.5 * MM, 6.5 * MM, 0.2 * MM, 0)
    jb.location = (31 * MM, yf + 1.5 * MM, zc - 3.25 * MM)
    assign(jb, dark)
    # statuslampa: liten vit punkt bakom en mikroperforering
    led = bpy.data.objects.new('mm_led', bpy.data.meshes.new('mm_led'))
    link(led)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=32, radius=0.65 * MM)
    bm.to_mesh(led.data)
    bm.free()
    led.rotation_euler = (math.radians(90), 0, 0)
    led.location = (46 * MM, yf - 0.02 * MM, zc)
    lm = bpy.data.materials.new('mm_led')
    lm.use_nodes = True
    nt = lm.node_tree
    nt.nodes.remove(nt.nodes['Principled BSDF'])
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (1.0, 0.97, 0.92, 1)
    em.inputs['Strength'].default_value = led_strength
    nt.links.new(em.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
    assign(led, lm)

    # fot: svart ring med ventilation, indragen
    foot = lathe('mm_fot', [(0.0, 0.0), (46 * MM, 0.0), (49 * MM, 0.4 * MM), (50 * MM, foot_h + 0.3 * MM), (0.0, foot_h + 0.3 * MM)], 128)
    assign(foot, mat_principled('mm_fot', (0.025, 0.025, 0.027, 1), 0.55))
    parent([body, jb, led, foot], root)
    return root, {'body': body, 'led': led, 'led_mat': lm, 'foot': foot}


# ---------------------------------------------------------------- Pixel Watch

def pixel_watch(screen_img, band_color=(0.045, 0.047, 0.05, 1), case_color=(0.78, 0.79, 0.80, 1), screen_strength=1.2, band_bend=0.018, band_len=(88, 104)):
    """Pixel Watch 3, 41 mm: helt valvt glas, krona pa hoger sida. Ligger med glaset uppat,
    armbandet utlagt at bada hall langs Y. Origo i bottenmitten under urtavlan."""
    root = empty('PixelWatch')
    R = 20.5 * MM
    # boett (rostfritt/aluminium, polerat) upp till glaset
    case_prof = [(0.0, 0.0), (15.5 * MM, 0.0), (17.5 * MM, 0.4 * MM), (19.3 * MM, 1.6 * MM), (20.3 * MM, 3.4 * MM),
                 (R, 5.0 * MM), (20.35 * MM, 6.2 * MM), (20.0 * MM, 6.8 * MM), (0.0, 6.8 * MM)]
    case = lathe('pw_boett', case_prof, 128)
    assign(case, mat_principled('pw_boett', case_color, 0.18, 1.0))
    # skarm (platt skiva) under glaset
    disp = bpy.data.objects.new('pw_skarm', bpy.data.meshes.new('pw_skarm'))
    link(disp)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=128, radius=19.6 * MM)
    uv = bm.loops.layers.uv.new('UVMap')
    for f in bm.faces:
        for l in f.loops:
            l[uv].uv = (0.5 + l.vert.co.x / (2 * 15.8 * MM), 0.5 + l.vert.co.y / (2 * 15.8 * MM))
    bm.to_mesh(disp.data)
    bm.free()
    disp.location.z = 6.85 * MM
    sm = mat_screen('pw_skarm', screen_img, screen_strength)
    assign(disp, sm)
    # valvt glas
    gl = []
    for i in range(25):
        t = i / 24.0
        r = 20.1 * MM * math.cos(t * math.pi / 2) ** 0.55
        z = 6.8 * MM + 5.5 * MM * math.sin(t * math.pi / 2) ** 0.9
        gl.append((r, z))
    gl[-1] = (0.0, gl[-1][1])
    glass = lathe('pw_glas', [(20.1 * MM, 6.79 * MM)] + gl, 128)
    # tunt valvt glas: ingen brytning (IOR 1), reflexerna kommer fran ett klarlack-lager
    gm = mat_principled('pw_glas', (1, 1, 1, 1), 0.0, 0.0, **{'Transmission Weight': 1.0, 'IOR': 1.0,
                        'Coat Weight': 1.0, 'Coat Roughness': 0.0, 'Coat IOR': 1.35})
    assign(glass, gm)
    # krona och knapp pa +X
    crown = bpy.data.objects.new('pw_krona', bpy.data.meshes.new('pw_krona'))
    link(crown)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=3.6 * MM, radius2=3.6 * MM, depth=3.0 * MM)
    bm.to_mesh(crown.data)
    bm.free()
    crown.rotation_euler = (0, math.radians(90), 0)
    crown.location = (20.9 * MM, 0, 4.4 * MM)
    bv = crown.modifiers.new('b', 'BEVEL'); bv.width = 0.6 * MM; bv.segments = 4
    apply_mods(crown)
    smooth(crown, 30)
    assign(crown, mat_principled('pw_krona', case_color, 0.25, 1.0))
    # armband: tva remmar som foljer en kurva fran fastet ned till bordet
    band_m = mat_principled('pw_band', band_color, 0.62, 0.0, **{'Sheen Weight': 0.15})
    straps = []
    for sgn in (1, -1):
        cu = bpy.data.curves.new('rem', 'CURVE')
        cu.dimensions = '3D'
        sp = cu.splines.new('BEZIER')
        bend = band_bend * sgn
        L = (band_len[0] if sgn > 0 else band_len[1]) * MM
        pts = [(0, sgn * 15 * MM, 3.4 * MM), (0, sgn * 24 * MM, 2.3 * MM), (bend * 0.15, sgn * 36 * MM, 1.25 * MM),
               (bend * 0.55, sgn * (36 * MM + (L - 36 * MM) * 0.55), 1.25 * MM), (bend, sgn * L, 1.25 * MM)]
        sp.bezier_points.add(len(pts) - 1)
        for bp, p in zip(sp.bezier_points, pts):
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
        cu.resolution_u = 24
        # rundad ande: avsmalning sista ~10 mm
        tcu = bpy.data.curves.new('remtaper', 'CURVE')
        ts = tcu.splines.new('POLY')
        tp = [(0.0, 1.0), (0.86, 1.0)] + [(0.86 + 0.14 * math.sin(math.pi / 2 * k / 8), math.cos(math.pi / 2 * k / 8) ** 0.8 * 0.95 + 0.05) for k in range(1, 9)]
        ts.points.add(len(tp) - 1)
        for p, c in zip(ts.points, tp):
            p.co = (c[0], c[1], 0, 1)
        to = bpy.data.objects.new('remtaper', tcu)
        link(to)
        to.hide_render = True
        to.hide_viewport = True
        cu.taper_object = to
        cu.taper_radius_mode = 'OVERRIDE'
        straps.append(to)
        cu.bevel_mode = 'OBJECT'
        prof = bpy.data.curves.new('remprof', 'CURVE')
        ps = prof.splines.new('POLY')
        pr = []
        for i in range(24):
            a = 2 * math.pi * i / 24
            x = 10.5 * MM * math.copysign(abs(math.cos(a)) ** 0.25, math.cos(a))
            y = 1.25 * MM * math.copysign(abs(math.sin(a)) ** 0.6, math.sin(a))
            pr.append((x, y))
        ps.points.add(len(pr) - 1)
        for p, c in zip(ps.points, pr):
            p.co = (c[0], c[1], 0, 1)
        ps.use_cyclic_u = True
        po = bpy.data.objects.new('remprof', prof)
        link(po)
        po.hide_render = True
        po.hide_viewport = True
        cu.bevel_object = po
        cu.use_fill_caps = True
        ob = bpy.data.objects.new('pw_rem', cu)
        link(ob)
        ob.data.materials.append(band_m)
        straps.append(ob)
        straps.append(po)
    parent([case, disp, glass, crown] + straps, root)
    return root, {'screen_mat': sm}


# ---------------------------------------------------------------- telefon

def phone(screen_img, frame_color=(0.04, 0.045, 0.05, 1), screen_strength=1.0):
    """Android-telefon 152 x 72 x 8,5 mm, liggande med skarmen uppat. Origo i bottenmitten."""
    root = empty('Telefon')
    L, B, T = 152 * MM, 72 * MM, 8.5 * MM
    body = rounded_box('tel_kropp', B, L, T, 9.5 * MM, 2.2 * MM, seg_plan=16, seg_edge=6)
    assign(body, mat_principled('tel_ram', frame_color, 0.35, 0.9))
    # glas och skarm som en tunn platta ovanpa
    scr = rounded_box('tel_skarm', B - 2.0 * MM, L - 2.0 * MM, 0.25 * MM, 8.5 * MM, 0.0, seg_plan=16)
    scr.location.z = T - 0.05 * MM
    me = scr.data
    uvl = me.uv_layers.new(name='UVMap')
    # aktiv yta: 1080x2400 i 68 x 151 mm, centrerad
    aw, ah = 68.0 * MM, 151.1 * MM
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uvl.data[li].uv = (0.5 + v.x / aw, 0.5 + v.y / ah)
    sm = mat_screen('tel_skarm', screen_img, screen_strength)
    assign(scr, sm)
    parent([body, scr], root)
    return root, {'screen_mat': sm}


# ---------------------------------------------------------------- miljo

def world_studio(sc, strength=0.25, color=(0.5, 0.5, 0.5)):
    w = bpy.data.worlds.new('studio')
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes['Background']
    exr = None
    for root in (os.path.dirname(bpy.app.binary_path),):
        for dp, dn, fn in os.walk(root):
            if 'studiolights' in dp and 'world' in dp:
                for f in fn:
                    if f.startswith('studio') and f.endswith('.exr'):
                        exr = os.path.join(dp, f)
            if exr:
                break
    if exr:
        env = nt.nodes.new('ShaderNodeTexEnvironment')
        env.image = bpy.data.images.load(exr)
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.inputs['Rotation'].default_value = (0, 0, math.radians(200))
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nt.links.new(tc.outputs['Generated'], mp.inputs['Vector'])
        nt.links.new(mp.outputs['Vector'], env.inputs['Vector'])
        sat = nt.nodes.new('ShaderNodeHueSaturation')
        sat.inputs['Saturation'].default_value = 0.0
        nt.links.new(env.outputs['Color'], sat.inputs['Color'])
        nt.links.new(sat.outputs['Color'], bg.inputs['Color'])
        print('HDRI', exr)
    else:
        bg.inputs['Color'].default_value = (*color, 1)
    bg.inputs['Strength'].default_value = strength
    return w


def area_light(name, loc, target, size, energy, color=(1, 1, 1), size_y=None, spread=180):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.color = color
    if size_y:
        ld.shape = 'RECTANGLE'
        ld.size = size
        ld.size_y = size_y
    else:
        ld.shape = 'DISK'
        ld.size = size
    ld.spread = math.radians(spread)
    ob = bpy.data.objects.new(name, ld)
    link(ob)
    ob.location = loc
    look_at(ob, target)
    return ob


def look_at(ob, target):
    d = Vector(target) - Vector(ob.location)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def camera(name, loc, target, lens=85, fstop=None, focus=None, sensor=36):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = sensor
    ob = bpy.data.objects.new(name, cd)
    link(ob)
    ob.location = loc
    look_at(ob, target)
    if fstop:
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.aperture_blades = 9
        if isinstance(focus, bpy.types.Object):
            cd.dof.focus_object = focus
        elif focus is not None:
            cd.dof.focus_distance = focus
    bpy.context.scene.camera = ob
    return ob


def desk(size=3.0, color=(0.16, 0.155, 0.15, 1), rough=0.55, wall=True, wall_color=None, spec=0.5):
    """Matt skrivbordsskiva (fin linoleum/laminatkansla) plus en mjuk bakgrund."""
    bpy.ops.mesh.primitive_plane_add(size=size)
    top = bpy.context.active_object
    top.name = 'bord'
    m = mat_principled('bord', color, rough, **{'Specular IOR Level': spec})
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 900.0
    nz.inputs['Detail'].default_value = 6.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nz2 = nt.nodes.new('ShaderNodeTexNoise')
    nz2.inputs['Scale'].default_value = 6.0
    nz2.inputs['Detail'].default_value = 3.0
    nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = rough - 0.08
    mr.inputs['To Max'].default_value = rough + 0.08
    nt.links.new(nz2.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.08
    bump.inputs['Distance'].default_value = 0.0002
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    # ljushetsvariation sa att ytan inte ar helt platt
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.inputs['Factor'].default_value = 0.12
    mix.inputs[6].default_value = color
    mix.inputs[7].default_value = tuple(c * 0.8 for c in color[:3]) + (1,)
    nt.links.new(nz2.outputs['Fac'], mix.inputs['Factor'])
    nt.links.new(mix.outputs[2], b.inputs['Base Color'])
    assign(top, m)
    objs = [top]
    if wall:
        bpy.ops.mesh.primitive_plane_add(size=size)
        w = bpy.context.active_object
        w.name = 'vagg'
        w.rotation_euler = (math.radians(90), 0, 0)
        w.location = (0, 0.9, size / 2)
        assign(w, mat_principled('vagg', wall_color or tuple(c * 0.7 for c in color[:3]) + (1,), 0.9))
        objs.append(w)
    return objs
