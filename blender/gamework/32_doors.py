"""Driver audit + shop entrance build + verification renders.

The leftover 'stretch helper' drivers reference self.scale, which is nonsense once
the rig is scaled down to human size - they would move the character when Blender
evaluates them with auto-execution on.
"""
import bpy
import math

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'render_util.py').read())

print("--- drivers before ---")
for holder in list(bpy.data.objects) + list(bpy.data.armatures) + list(bpy.data.meshes):
    ad = getattr(holder, 'animation_data', None)
    if ad and ad.drivers:
        for d in ad.drivers:
            print("DRV|%-12s|%s|%s" % (holder.name, d.data_path, d.driver.expression))

removed = 0
for holder in list(bpy.data.objects) + list(bpy.data.armatures) + list(bpy.data.meshes):
    ad = getattr(holder, 'animation_data', None)
    if not ad:
        continue
    for d in list(ad.drivers):
        expr = d.driver.expression
        if 'self.' in expr or 'context' in expr:
            ad.drivers.remove(d)
            removed += 1
print("### removed %d authoring drivers" % removed)

left = 0
for holder in list(bpy.data.objects) + list(bpy.data.armatures) + list(bpy.data.meshes):
    ad = getattr(holder, 'animation_data', None)
    if ad and ad.drivers:
        left += len(ad.drivers)
print("### %d drivers remain" % left)

# make sure the character transforms are exactly what we placed
for name in ('Boy1_RIG', 'Boy2_RIG'):
    a = bpy.data.objects[name]
    print("### %s loc=%s scale=%s" % (name, tuple(round(v, 4) for v in a.location),
                                      tuple(round(v, 5) for v in a.scale)))

if 'Shop_Door_L' not in bpy.data.objects:
    exec(compile(open(GW + '30_shop_door.py').read(), '30_shop_door.py', 'exec'))

doors = [n for n in ('Shop_Door_L', 'Shop_Door_R') if n in bpy.data.objects]
print("### doors present:", doors)

shot('C:/temp/blender_previews/entrance_closed.png', (-9.0, -2.0, 1.7), (-4.15, -2.0, 1.35), lens=35)
shot('C:/temp/blender_previews/entrance_34.png', (-7.4, -5.6, 2.1), (-4.15, -1.6, 1.25), lens=35)
for n, s in (('Shop_Door_L', -1.0), ('Shop_Door_R', 1.0)):
    if n in bpy.data.objects:
        bpy.data.objects[n].rotation_euler.z = s * math.radians(96)
bpy.context.view_layer.update()
shot('C:/temp/blender_previews/entrance_open.png', (-7.4, -5.6, 2.1), (-4.15, -1.6, 1.25), lens=35)
shot('C:/temp/blender_previews/entrance_open_side.png', (-8.6, -2.0, 2.2), (-4.6, -2.0, 1.0), lens=35)
for n in ('Shop_Door_L', 'Shop_Door_R'):
    if n in bpy.data.objects:
        bpy.data.objects[n].rotation_euler.z = 0.0

bpy.ops.wm.save_mainfile()
print("### saved")
print("DOORS DONE")
