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
    desk(size=4.0, color=(0.032, 0.031, 0.030, 1), rough=0.72, spec=0.3, wall=True, wall_color=(0.03, 0.03, 0.03, 1))
    mini, mp = mac_mini(led_strength=led_strength)
    mini.location = (0.06, 0.03, 0.0)
    mini.rotation_euler.z = math.radians(-33)
    watch, wp = pixel_watch(os.path.join(HERE, 'tex_klocka_panel.png'), band_color=(0.075, 0.077, 0.078, 1), screen_strength=9.0)
    watch.location = (-0.07, -0.135, 0.0)
    watch.rotation_euler.z = math.radians(25)
    tel, tp = phone(os.path.join(HERE, 'tex_mobil_panel.png'), screen_strength=7.0)
    tel.location = (-0.165, 0.035, 0.0)
    tel.rotation_euler.z = math.radians(-12)
    world_studio(sc, 0.015)
    # nyckelljus: stor softbox snett bakifran vanster, ger ljuskanten pa ovansidan
    area_light('nyckel', (-0.55, 0.30, 0.70), (0, 0, 0.02), 0.9, 30, size_y=0.6, spread=60)
    # fyllnad fran hoger fram, lag och mjuk
    area_light('fyll', (0.85, -0.25, 0.30), (0.06, 0.03, 0.03), 1.2, 6, color=(1.0, 0.97, 0.93), size_y=0.35, spread=60)
    # kantljus bakom, smal list
    area_light('kant', (0.30, 0.60, 0.16), (0, 0, 0.03), 1.0, 8, size_y=0.06, spread=40)
    # svag toppbelysning for en mjuk reflex i aluminiumet
    area_light('topp', (0.05, -0.20, 0.8), (0.05, 0, 0), 0.5, 4, size_y=0.4, spread=40)
    # reflexskarmar: syns bara i speglingar, ger aluminiumet mjuka gradienter
    for nm, loc, tgt, sz, sy, e in (('refl_topp', (-0.05, 0.85, 0.40), (0.06, 0.03, 0.05), 1.4, 0.45, 13),
                                    ('refl_fram', (0.35, -1.3, 0.30), (0.06, 0.03, 0.03), 1.2, 0.6, 7)):
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
    if VAR == 'hog':
        watch.location = (0.0, -0.175, 0.0)
        watch.rotation_euler.z = math.radians(18)
        tel.location = (-0.12, 0.02, 0.0)
        tel.rotation_euler.z = math.radians(-8)
    foc = empty('fokus', (0.09, -0.03, 0.026))
    if VAR == 'test_topp':
        camera('kamera', (watch.location.x, watch.location.y, 0.35), (watch.location.x, watch.location.y + 0.0001, 0.0), lens=50)
    elif VAR == 'test_klocka':
        camera('kamera', (watch.location.x + 0.08, watch.location.y - 0.12, 0.09), (watch.location.x, watch.location.y, 0.005), lens=70, fstop=8, focus=0.16)
    elif VAR == 'test_mini':
        camera('kamera', (0.10, -0.30, 0.07), (0.0, 0.0, 0.025), lens=70, fstop=8, focus=0.3)
    elif VAR == 'hog':
        camera('kamera', (0.14, -0.64, 0.40), (0.0, -0.08, 0.0), lens=55, fstop=2.8, focus=foc)
    else:
        camera('kamera', (0.20, -0.70, 0.30), (-0.01, -0.035, 0.02), lens=62, fstop=2.8, focus=foc)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    render_still(sc, OUT)
