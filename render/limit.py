"""Hardvarugransen: Mac mini i genomskuren vy med kretskort, M4-paket med minne och flakt.
Siffrorna ritas efterat av post_limit.py.

blender -b -P limit.py -- <bredd> <hojd> <ut.png> [samples]
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from common import *

a = args()
W = int(a[0]) if a else 1920
H = int(a[1]) if len(a) > 1 else 1080
OUT = a[2] if len(a) > 2 else os.path.join(HERE, 'ut', 'limit.png')
SAMPLES = int(a[3]) if len(a) > 3 else 512

sc = reset()
setup_render(sc, W, H, samples=SAMPLES, noise=0.008, exposure=-3.2)

desk(size=4.0, color=(0.032, 0.031, 0.030, 1), rough=0.72, spec=0.3, wall=True, wall_color=(0.03, 0.03, 0.03, 1))

mini, mp = mac_mini(led_strength=6.0)
body = mp['body']
# gor kroppen ihalig (1,6 mm gods) och skar bort ovre bakre halften sa att insidan syns
inner = rounded_box('inre', 0.127 - 0.0032, 0.127 - 0.0032, 0.050 - 0.0022 - 0.0032, 0.0194, 0.0, seg_plan=20)
inner.location = (0, 0, 0.0022 + 0.0016)
boolean_cut(body, inner)
# lock bort (snitt strax under ovankantens rundning) och narmaste hornet nedsankt till 18 mm
cutter2 = rounded_box('snitt2', 0.2, 0.2, 0.04, 0.0001, 0.0, seg_plan=1)
cutter2.location = (0.0, 0.0, 0.0455)
cutter = rounded_box('snitt', 0.23, 0.23, 0.06, 0.0001, 0.0, seg_plan=1)
cutter.location = (0.085, -0.085, 0.018)  # tar bort framre hogra kvadranten ovanfor 18 mm
bpy.context.view_layer.update()
boolean_cut(body, cutter2)
boolean_cut(body, cutter)
smooth(body, 40)

# snittytor i aluminiumet far en ljusare, matt fras-yta: ange via separat material pa nya ytor ar
# krangligt efter boolean; godset ar tunt nog att samma material fungerar.

inside = []
pcb_m = mat_principled('kort', srgb((0x16, 0x1d, 0x20)), 0.5, 0.0, **{'Coat Weight': 0.3, 'Coat Roughness': 0.35})
nt = pcb_m.node_tree
bsdf = nt.nodes['Principled BSDF']
tc = nt.nodes.new('ShaderNodeTexCoord')
br = nt.nodes.new('ShaderNodeTexBrick')
br.inputs['Scale'].default_value = 90.0
br.inputs['Mortar Size'].default_value = 0.004
br.inputs['Color1'].default_value = srgb((0x16, 0x1d, 0x20))
br.inputs['Color2'].default_value = srgb((0x18, 0x20, 0x23))
br.inputs['Mortar'].default_value = srgb((0x26, 0x30, 0x33))
nt.links.new(tc.outputs['Object'], br.inputs['Vector'])
nt.links.new(br.outputs['Color'], bsdf.inputs['Base Color'])
pcb = rounded_box('kort', 0.112, 0.112, 0.0016, 0.012, 0.0, seg_plan=10)
pcb.location = (0, 0.004, 0.012)
assign(pcb, pcb_m)
inside.append(pcb)
# M4-paketet: substrat, kiselchip och tva minnespaket (LPDDR5X, 2 x 8 GB = 16 GB)
sub = rounded_box('substrat', 0.034, 0.030, 0.0012, 0.0012, 0.0, seg_plan=4)
sub.location = (0.004, 0.010, 0.0136)
assign(sub, mat_principled('substrat', srgb((0x2c, 0x32, 0x2e)), 0.5))
die = rounded_box('m4', 0.014, 0.016, 0.0007, 0.0004, 0.0, seg_plan=3)
die.location = (-0.004, 0.010, 0.0148)
assign(die, mat_principled('kisel', (0.04, 0.045, 0.06, 1), 0.08, 0.6))
mem_m = mat_principled('minne', (0.018, 0.018, 0.02, 1), 0.4)
mems = []
for k, y in enumerate((0.0035, 0.0165)):
    mm = rounded_box('minne%d' % k, 0.011, 0.0115, 0.0011, 0.0004, 0.0002, seg_plan=3, seg_edge=2)
    mm.location = (0.0125, y, 0.0148)
    assign(mm, mem_m)
    mems.append(mm)
inside += [sub, die] + mems
# smakomponenter i ordnade rader runt paketet (avkopplingskondensatorer), spolar och NAND-kretsar
cap_m = mat_principled('komp', srgb((0x8a, 0x7a, 0x62)), 0.4, 0.2)
ind_m = mat_principled('spole', (0.16, 0.16, 0.17, 1), 0.45, 0.6)
for row in range(2):
    for i in range(10):
        for (ox, oy, rot) in ((0.004 - 0.0135 + i * 0.003, 0.010 - 0.0175 - row * 0.0022, 0), (0.004 - 0.0135 + i * 0.003, 0.010 + 0.0175 + row * 0.0022, 0)):
            c = rounded_box('komp', 0.0012, 0.0006, 0.0005, 0.0001, 0.0, seg_plan=1)
            c.location = (ox, oy, 0.0136)
            assign(c, cap_m)
            inside.append(c)
for i in range(4):
    sp = rounded_box('spole', 0.006, 0.006, 0.003, 0.0008, 0.0003, seg_plan=3, seg_edge=2)
    sp.location = (-0.026 + i * 0.0075, -0.020, 0.0136)
    assign(sp, ind_m)
    inside.append(sp)
nand_m = mat_principled('nand', (0.02, 0.02, 0.022, 1), 0.5)
for i in range(2):
    nd = rounded_box('nand', 0.014, 0.018, 0.0012, 0.0005, 0.0002, seg_plan=3, seg_edge=2)
    nd.location = (0.036, -0.010 + i * 0.024, 0.0136)
    assign(nd, nand_m)
    inside.append(nd)
# portar pa baksidan (natverk, HDMI, tre USB-C) och strom: metallholjen langs bakre vaggen
shell_m = mat_principled('portholje', (0.55, 0.56, 0.57, 1), 0.3, 1.0)
x0 = 0.050
for w_, h_ in ((0.016, 0.0135), (0.015, 0.0062), (0.0092, 0.0034), (0.0092, 0.0034), (0.0092, 0.0034)):
    sh = rounded_box('port', w_, 0.012, h_, min(h_, w_) * 0.25, 0.0, seg_plan=4)
    sh.location = (x0 - w_ / 2, 0.0545, 0.0136)
    assign(sh, shell_m)
    inside.append(sh)
    x0 -= w_ + 0.0045
# sma styrkretsar vid de framre USB-C-portarna
for x in (-0.044, -0.031):
    ch = rounded_box('usbstyr', 0.006, 0.006, 0.0009, 0.0004, 0.0, seg_plan=3)
    ch.location = (x, -0.044, 0.0136)
    assign(ch, nand_m)
    inside.append(ch)
# flakt (Mac minin har en centrifugalflakt under locket) bakre vanstra delen
fan_ring = lathe('flakthus', [(0.020, 0.0136), (0.0205, 0.0136), (0.0205, 0.028), (0.020, 0.028)], 96)
fan_ring.location = (-0.030, 0.026, 0.0)
fan_m = mat_principled('flakt', (0.03, 0.03, 0.032, 1), 0.5)
assign(fan_ring, fan_m)
hub = lathe('nav', [(0.0, 0.016), (0.008, 0.016), (0.008, 0.0255), (0.0, 0.0255)], 64)
hub.location = (-0.030, 0.026, 0.0)
assign(hub, fan_m)
inside += [fan_ring, hub]
for i in range(31):
    bl = rounded_box('blad', 0.0105, 0.0005, 0.0085, 0.0001, 0.0, seg_plan=1)
    ang = 2 * math.pi * i / 31
    r = 0.0137
    bl.location = (-0.030 + r * math.cos(ang), 0.026 + r * math.sin(ang), 0.0165)
    bl.rotation_euler.z = ang + math.radians(30)
    assign(bl, fan_m)
    inside.append(bl)
parent(inside, mini)
mini.location = (0.0, 0.0, 0.0)
mini.rotation_euler.z = math.radians(-32)

world_studio(sc, 0.2)
area_light('nyckel', (-0.45, 0.35, 0.7), (0, 0, 0.02), 0.8, 110, size_y=0.5)
area_light('fyll', (0.7, -0.6, 0.4), (0, 0, 0.03), 1.2, 30, color=(1.0, 0.97, 0.93))
area_light('kant', (0.4, 0.7, 0.2), (0, 0, 0.03), 1.2, 40, size_y=0.08)
area_light('topp', (0.0, -0.05, 0.8), (0, 0, 0), 0.6, 35, size_y=0.6)

foc = empty('fokus', (0.0, 0.0, 0.015))
cam = camera('kamera', (0.20, -0.34, 0.30), (0.0, 0.0, 0.012), lens=56, fstop=5.6, focus=foc)
cam.data.shift_x = 0.17
cam.data.shift_y = 0.02
bpy.context.view_layer.update()


def px(p):
    v = world_to_camera_view(sc, cam, Vector(p))
    return [round(v.x * W, 1), round((1 - v.y) * H, 1)]


anch = {
    'minne0': px(mems[0].matrix_world @ Vector((0, 0, 0.0011))),
    'minne1': px(mems[1].matrix_world @ Vector((0, 0, 0.0011))),
    'm4': px(die.matrix_world @ Vector((0, 0, 0.0007))),
    'led': px(mp['led'].matrix_world.translation),
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(os.path.splitext(OUT)[0] + '_ankare.json', 'w') as f:
    json.dump(anch, f, indent=1)
render_still(sc, OUT)
