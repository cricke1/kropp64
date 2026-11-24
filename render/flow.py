"""Dataflode: isometrisk teknisk illustration klocka -> telefon -> Mac mini, med
uppskjutna lager over Mac minin (lokal AI, vakt, konsilium, granskare).
Etiketter och linjer ritas efterat av post_flow.py med ankarpunkter fran ankare.json.

blender -b -P flow.py -- <bredd> <hojd> <ut.png> [samples]
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from common import *

a = args()
W = int(a[0]) if a else 1920
H = int(a[1]) if len(a) > 1 else 1080
OUT = a[2] if len(a) > 2 else os.path.join(HERE, 'ut', 'flow.png')
SAMPLES = int(a[3]) if len(a) > 3 else 384

sc = reset()
setup_render(sc, W, H, samples=SAMPLES, noise=0.01, exposure=-2.0)
sc.view_settings.look = 'AgX - Base Contrast'

# golv med svagt rutnat (10 mm), farg som webbens --bg
bpy.ops.mesh.primitive_plane_add(size=6)
fl = bpy.context.active_object
m = bpy.data.materials.new('golv')
m.use_nodes = True
nt = m.node_tree
b = nt.nodes['Principled BSDF']
b.inputs['Roughness'].default_value = 0.8
tc = nt.nodes.new('ShaderNodeTexCoord')
sep = nt.nodes.new('ShaderNodeSeparateXYZ')
nt.links.new(tc.outputs['Object'], sep.inputs[0])


def gridline(comp, step, width):
    mul = nt.nodes.new('ShaderNodeMath'); mul.operation = 'DIVIDE'; mul.inputs[1].default_value = step
    nt.links.new(sep.outputs[comp], mul.inputs[0])
    fr = nt.nodes.new('ShaderNodeMath'); fr.operation = 'PINGPONG'; fr.inputs[1].default_value = 0.5
    nt.links.new(mul.outputs[0], fr.inputs[0])
    lt = nt.nodes.new('ShaderNodeMath'); lt.operation = 'LESS_THAN'; lt.inputs[1].default_value = width
    nt.links.new(fr.outputs[0], lt.inputs[0])
    return lt


gx, gy = gridline('X', 0.02, 0.025), gridline('Y', 0.02, 0.025)
mx = nt.nodes.new('ShaderNodeMath'); mx.operation = 'MAXIMUM'
nt.links.new(gx.outputs[0], mx.inputs[0]); nt.links.new(gy.outputs[0], mx.inputs[1])
mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'
mix.inputs[6].default_value = srgb((0x16, 0x1a, 0x1d))
mix.inputs[7].default_value = srgb((0x1f, 0x25, 0x29))
nt.links.new(mx.outputs[0], mix.inputs['Factor'])
nt.links.new(mix.outputs[2], b.inputs['Base Color'])
assign(fl, m)

# foremal langs en diagonal (isometrin later dem ga fran vanster till hoger)
watch, wp = pixel_watch(os.path.join(HERE, 'tex_klocka_panel.png'), band_color=(0.075, 0.077, 0.078, 1), screen_strength=6.0)
watch.location = (-0.24, -0.24, 0.0)
watch.rotation_euler.z = math.radians(45)
tel, tp = phone(os.path.join(HERE, 'tex_mobil_panel.png'), screen_strength=4.0)
tel.location = (-0.04, -0.04, 0.0)
tel.rotation_euler.z = math.radians(45)
mini, mp = mac_mini()
mini.location = (0.17, 0.17, 0.0)
mini.rotation_euler.z = math.radians(0)

# uppskjutna lager over Mac minin: samma fotavtryck, tunna plattor
plates = []
names = ['ollama', 'vakt', 'konsilium', 'granskare']
cols = [(0x2a, 0x31, 0x36), (0x2a, 0x31, 0x36), (0x2a, 0x31, 0x36), (0x2a, 0x31, 0x36)]
for i, nm in enumerate(names):
    p = rounded_box('lager_' + nm, 0.112, 0.112, 0.004, 0.018, 0.0012, seg_plan=16, seg_edge=3)
    p.location = (0.17, 0.17, 0.105 + i * 0.06)
    pm = mat_principled('lager_' + nm, srgb(cols[i]), 0.45, 0.0)
    assign(p, pm)
    plates.append(p)
    # tunn ljus kant langs plattans ovansida: en lite storre platta under med matt ljusgra
    e = rounded_box('kant_' + nm, 0.1135, 0.1135, 0.0006, 0.0185, 0.0, seg_plan=16)
    e.location = (0.17, 0.17, 0.105 + i * 0.06 + 0.0041)
    em = mat_principled('kant_' + nm, srgb((0x3a, 0x44, 0x4a)), 0.5)
    assign(e, em)

world_studio(sc, 0.35)
area_light('topp', (-0.3, 0.3, 1.6), (0, 0, 0), 2.0, 260)
area_light('sida', (-1.2, -0.6, 0.6), (0, 0, 0.05), 1.2, 60, color=(1.0, 0.98, 0.95))
area_light('bak', (0.8, 0.9, 0.5), (0, 0, 0.05), 1.0, 40)

# isometrisk ortografisk kamera
cd = bpy.data.cameras.new('iso')
cd.type = 'ORTHO'
cd.ortho_scale = 0.86
cam = bpy.data.objects.new('iso', cd)
link(cam)
cam.rotation_euler = (math.radians(54.7356), 0, math.radians(45))
d = Vector((0, 0, 1))
d.rotate(cam.rotation_euler)
cen = Vector((0.0, 0.0, 0.15))
cam.location = cen + d * 3.0
cd.shift_x = -0.03
cd.shift_y = 0.0
cd.clip_end = 10
sc.camera = cam

bpy.context.view_layer.update()


def px(p):
    v = world_to_camera_view(sc, cam, Vector(p))
    return [round(v.x * W, 1), round((1 - v.y) * H, 1)]


def world(ob, local):
    return tuple(ob.matrix_world @ Vector(local))


anch = {
    'klocka': px(world(watch, (0, 0, 0.012))),
    'klocka_kant': px(world(watch, (0.021, 0, 0.006))),
    'telefon': px(world(tel, (0, 0, 0.009))),
    'telefon_topp': px(world(tel, (0, 0.076, 0.009))),
    'telefon_botten': px(world(tel, (0, -0.076, 0.009))),
    'mini': px(world(mini, (0, 0, 0.05))),
    'mini_front': px(world(mini, (0, -0.0635, 0.025))),
    'mini_vanster': px(world(mini, (-0.0635, 0, 0.025))),
}
for p, nm in zip(plates, names):
    anch['lager_' + nm] = px(world(p, (0, 0, 0.004)))
    anch['lager_' + nm + '_hoger'] = px(world(p, (0.0507, 0.0507, 0.002)))
    anch['lager_' + nm + '_vanster'] = px(world(p, (-0.0507, -0.0507, 0.002)))
    anch['lager_' + nm + '_bak'] = px(world(p, (0.0, 0.056, 0.002)))
anch['mini_hoger'] = px(world(mini, (0.058, 0.058, 0.025)))
anch['mini_framhorn'] = px(world(mini, (0.058, -0.058, 0.0)))
anch['mini_vhorn'] = px(world(mini, (-0.058, -0.058, 0.025)))
anch['klocka_hoger'] = px(world(watch, (0.0215, 0.0, 0.004)))
anch['telefon_vanster'] = px(world(tel, (-0.036, 0.0, 0.004)))
anch['telefon_hoger'] = px(world(tel, (0.036, 0.0, 0.004)))
anch['mini_vanster_golv'] = px(world(mini, (-0.0635, 0.0, 0.0)))
anch['klocka_golv'] = px(world(watch, (0.0, 0.0, 0.0)))
anch['telefon_golv'] = px(world(tel, (0.0, 0.0, 0.0)))
anch['mini_golv'] = px(world(mini, (0.0, 0.0, 0.0)))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(os.path.splitext(OUT)[0] + '_ankare.json', 'w') as f:
    json.dump(anch, f, indent=1)
render_still(sc, OUT)
