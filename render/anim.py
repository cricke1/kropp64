"""Kort animation: kameran borjar nara Mac minins statuslampa, glider runt och slutar pa skrivbordsscenen.
8 s i 30 bilder/s. PNG-sekvens till <utmapp>/f####.png.

blender -b -P anim.py -- <bredd> <hojd> <utmapp> [samples] [forsta] [sista]
"""
import sys, os, math, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector, Matrix
from common import *
import hero

a = args()
W = int(a[0]) if a else 1920
H = int(a[1]) if len(a) > 1 else 1080
OUTDIR = a[2] if len(a) > 2 else os.path.join(HERE, 'ut', 'anim')
SAMPLES = int(a[3]) if len(a) > 3 else 160
F0 = int(a[4]) if len(a) > 4 else 1
F1 = int(a[5]) if len(a) > 5 else 240
STEP = int(a[6]) if len(a) > 6 else 1

sc = reset()
setup_render(sc, W, H, samples=SAMPLES, noise=0.02, exposure=-3.2)
sc.render.use_persistent_data = True
sc.render.fps = 30
sc.frame_start, sc.frame_end = F0, F1
sc.frame_step = STEP
mini, mp, watch, tel = hero.build(sc)
bpy.context.view_layer.update()
M = mini.matrix_world
led = M @ Vector((0.046, -0.0635 - 0.0005, 0.0022 + 0.0195))


def L(x, y, z):
    return M @ Vector((x, y, z))


# kamerabana: (bild, position, mal, bt)
keys = [
    (-25, L(0.075, -0.185, 0.026), led, 95),
    (95, L(0.20, -0.20, 0.07), L(0.02, -0.03, 0.022), 80),
    (240, Vector((0.14, -0.58, 0.30)), Vector((-0.005, -0.015, 0.012)), 60),
]
cd = bpy.data.cameras.new('anim')
cam = bpy.data.objects.new('anim', cd)
link(cam)
sc.camera = cam
tgt = empty('mal')
foc = empty('fokus')
con = cam.constraints.new('TRACK_TO')
con.target = tgt
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'
cd.sensor_width = 36
cd.dof.use_dof = True
cd.dof.aperture_fstop = 2.8
cd.dof.aperture_blades = 9
cd.dof.focus_object = foc
# fokus: lampan i borjan, minins front i slutet (som hjaltebilden)
foc_keys = [(1, led), (95, L(0.03, -0.0635, 0.025)), (165, L(0.0, -0.0635, 0.025)), (240, Vector((-0.01, -0.025, 0.01)))]
for f, pos, t, lens in keys:
    cam.location = pos
    cam.keyframe_insert('location', frame=f)
    tgt.location = t
    tgt.keyframe_insert('location', frame=f)
    cd.lens = lens
    cd.keyframe_insert('lens', frame=f)
for f, fs in ((1, 2.8), (95, 3.5), (240, 5.6)):
    cd.dof.aperture_fstop = fs
    cd.dof.keyframe_insert('aperture_fstop', frame=f)
for f, p in foc_keys:
    foc.location = p
    foc.keyframe_insert('location', frame=f)
# mjuk start och mjukt slut, ingen stopp i mitten
for ob in (cam, tgt, foc, cd):
    ad = ob.animation_data
    for fc in ad.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
        fc.update()
# mittnyckeln ska inte bromsa: ersatt AUTO_CLAMPED med AUTO pa mitten
for ob in (cam, tgt, foc, cd):
    for fc in ob.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            if 2 < kp.co[0] < 239:
                kp.handle_left_type = kp.handle_right_type = 'AUTO'
        fc.update()

os.makedirs(OUTDIR, exist_ok=True)
sc.render.filepath = os.path.join(OUTDIR, 'f')
tider = {}
t_last = [time.time()]


def pre(scene, *_):
    t_last[0] = time.time()


def post(scene, *_):
    tider[scene.frame_current] = round(time.time() - t_last[0], 2)
    with open(os.path.join(OUTDIR, 'tider.json'), 'w') as fh:
        json.dump(tider, fh)


bpy.app.handlers.render_pre.append(pre)
bpy.app.handlers.render_post.append(post)
t = time.time()
bpy.ops.render.render(animation=True)
with open(os.path.join(OUTDIR, 'klar.txt'), 'w') as fh:
    fh.write('%.1f\n' % (time.time() - t))
print('ANIMATION KLAR %.1f s' % (time.time() - t))
