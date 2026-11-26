"""Hjaltebild: Mac mini pa skrivbordet med Pixel Watch och Android-telefon.

blender -b -P hero.py -- <bredd> <hojd> <ut.png> [samples] [variant]
variant: 'bred' (16:9) eller 'hog' (4:5)
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from common import *

a = args()
W = int(a[0]) if a else 1920
H = int(a[1]) if len(a) > 1 else 1080
OUT = a[2] if len(a) > 2 else os.path.join(HERE, 'ut', 'hero.png')
SAMPLES = int(a[3]) if len(a) > 3 else 512
VAR = a[4] if len(a) > 4 else 'bred'


def build(sc, led_strength=6.0):
    # mattsvart skrivbordsskiva med svag reflektion, ger foremalen en mjuk spegling att sta pa
    desk(size=4.0, color=(0.014, 0.014, 0.015, 1), rough=0.38, spec=0.5, wall=True, wall_color=(0.01, 0.01, 0.01, 1))
    mini, mp = mac_mini(led_strength=led_strength)
    mini.location = (0.075, 0.045, 0.0)
    mini.rotation_euler.z = math.radians(-30)
    # klockan framfor, med uppsidan bort fran kameran sa att urtavlan ar rattvand; korta remmar
    watch, wp = pixel_watch(os.environ.get('TEX_KLOCKA', os.path.join(HERE, 'tex_klocka_panel.png')), band_color=(0.30, 0.30, 0.29, 1),
                            screen_strength=9.0, band_bend=0.008, band_len=(62, 72))
    watch.location = (-0.035, -0.095, 0.0)
    watch.rotation_euler.z = math.radians(16)
    tel, tp = phone(os.environ.get('TEX_MOBIL', os.path.join(HERE, 'tex_mobil_panel.png')), screen_strength=9.0)
    tel.location = (-0.125, 0.025, 0.0)
    tel.rotation_euler.z = math.radians(22)
    world_studio(sc, 0.006)
    # nyckelljus: mjuk softbox fran vanster sida, lag, faller av mot bakgrunden
    area_light('nyckel', (-0.62, -0.02, 0.32), (0.0, 0.0, 0.02), 0.7, 13, size_y=0.5, spread=50)
    # kantljus bakifran hoger: ritar Mac minins rundade ovankant och telefonens kant
    k1 = area_light('kant', (0.20, 0.55, 0.30), (0.06, 0.04, 0.05), 0.9, 15, size_y=0.08, spread=22)
    k1.visible_camera = False
    # svag fyllnad fran hoger fram
    area_light('fyll', (0.70, -0.45, 0.28), (0.0, 0.0, 0.02), 1.0, 2.5, color=(1.0, 0.97, 0.93), size_y=0.35, spread=60)
    # reflexskarmar som bara syns i aluminiumet: en mjuk spegling i ovansidan och en gradient i fronten
    for nm, loc, tgt, sz, sy, e in (('refl_topp', (-0.10, 0.70, 0.55), (0.075, 0.045, 0.05), 0.5, 0.9, 5),
                                    ('refl_fram', (0.30, -1.2, 0.25), (0.075, 0.045, 0.03), 1.2, 0.6, 5)):
        l = area_light(nm, loc, tgt, sz, e, size_y=sy, spread=180)
        l.visible_camera = False
        l.visible_diffuse = False
        rc = bpy.data.collections.get('refl_mottagare') or bpy.data.collections.new('refl_mottagare')
        if mp['body'].name not in rc.objects:
            rc.objects.link(mp['body'])
        l.light_linking.receiver_collection = rc
    return mini, mp, watch, tel


if __name__ == '__main__':
    sc = reset()
    setup_render(sc, W, H, samples=SAMPLES, noise=0.008, exposure=-3.2)
    mini, mp, watch, tel = build(sc)
    foc = empty('fokus', (-0.01, -0.025, 0.01))
    if VAR == 'test_klocka':
        camera('kamera', (watch.location.x + 0.08, watch.location.y - 0.12, 0.09), (watch.location.x, watch.location.y, 0.005), lens=70, fstop=8, focus=0.16)
    elif VAR == 'hog':
        # hogre kamera ser mer av reflexskarmen i ovansidan: dampa den
        bpy.data.objects['refl_topp'].data.energy *= 0.4
        bpy.data.objects['kant'].data.energy *= 0.6
        camera('kamera', (0.07, -0.47, 0.44), (-0.01, -0.005, 0.0), lens=50, fstop=5.6, focus=foc)
    else:
        camera('kamera', (0.14, -0.58, 0.30), (-0.005, -0.015, 0.012), lens=60, fstop=5.6, focus=foc)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    render_still(sc, OUT)
