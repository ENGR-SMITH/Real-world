"""Remove the rig's authoring drivers (they fight our placement) and check the entrance."""
import bpy
import math
import mathutils

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'render_util.py').read())

POS = {'Boy1_RIG': (-5.35, 6.0), 'Boy2_RIG': (-5.55, 7.4)}
GROUND = 0.06

drivers_removed = 0
for o in bpy.data.objects:
    if o.type not in ('ARMATURE', 'MESH', 'EMPTY'):
        continue
    ad = o.animation_data
    if not ad:
        continue
    for d in list(ad.drivers):
        if not d.data_path.startswith('pose.bones'):
            ad.drivers.remove(d)
            drivers_removed += 1
print("### removed %d object-level drivers" % drivers_removed)

for name in ('Boy1_RIG', 'Boy2_RIG'):
    a = bpy.data.objects[name]
    a.animation_data.action = bpy.data.actions['idle']
    a.scale = (a.scale[0], a.scale[1], a.scale[2])
    bpy.context.view_layer.update()


def bbox_of(a):
    dg = bpy.context.evaluated_depsgraph_get()
    mn = [1e18] * 3
    mx = [-1e18] * 3
    for ob in bpy.data.objects:
        if ob.parent is not a or ob.type != 'MESH':
            continue
        obe = ob.evaluated_get(dg)
        me = obe.to_mesh()
        for v in me.vertices:
            w = obe.matrix_world @ v.co
            for k in range(3):
                mn[k] = min(mn[k], w[k])
                mx[k] = max(mx[k], w[k])
        obe.to_mesh_clear()
    return mn, mx


for name, (x, y) in POS.items():
    a = bpy.data.objects[name]
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    mn, mx = bbox_of(a)
    a.location = (a.location[0] + x - (mn[0] + mx[0]) / 2.0,
                  a.location[1] + y - (mn[1] + mx[1]) / 2.0,
                  a.location[2] + GROUND - mn[2])
    bpy.context.view_layer.update()
    mn, mx = bbox_of(a)
    d = [abs(a.scale[i] - 0.135026) for i in range(3)]
    print("### %s loc=%s scale=%s sole=%.3f height=%.3f scaledrift=%.5f"
          % (name, tuple(round(v, 3) for v in a.location), tuple(round(v, 4) for v in a.scale),
             mn[2], mx[2] - mn[2], max(d)))

shot('C:/temp/blender_previews/entrance_closed.png', (-9.0, -2.0, 1.7), (-4.15, -2.0, 1.35), lens=35)
shot('C:/temp/blender_previews/entrance_34.png', (-7.4, -5.6, 2.1), (-4.15, -1.6, 1.25), lens=35)

for n, s in (('Shop_Door_L', -1.0), ('Shop_Door_R', 1.0)):
    ob = bpy.data.objects[n]
    ob.rotation_euler.z = s * math.radians(96)
bpy.context.view_layer.update()
shot('C:/temp/blender_previews/entrance_open.png', (-7.4, -5.6, 2.1), (-4.15, -1.6, 1.25), lens=35)
shot('C:/temp/blender_previews/entrance_open_top.png', (-6.0, -2.0, 4.6), (-3.4, -2.0, 0.9), lens=30)
for n in ('Shop_Door_L', 'Shop_Door_R'):
    bpy.data.objects[n].rotation_euler.z = 0.0

bpy.ops.wm.save_mainfile()
print("### saved")
print("FINALIZE DONE")
