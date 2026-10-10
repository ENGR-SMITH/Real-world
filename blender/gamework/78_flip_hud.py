"""78_flip_hud.py -- do camera children draw if they sit at local +z?

The engine draws world objects (the QQ_F/G/H cubes appear in live_a.png) but never
draws a child of the active camera: not the HUD text, not the QQ_A/B/C cubes that
sit one metre in front.  One candidate is a sign convention: the engine's world
model agrees the children are at camera-space z = -1 (our depth probe read their
world positions back as exactly one metre ahead), but its rasteriser may want +z
for camera-space objects.

Flip every camera child to +z and save a copy to run.

    blender.exe -b hud_test.blend --python 78_flip_hud.py
"""

import bpy

P = print
cam = bpy.data.objects.get("Camera_Game")
P("### camera children:")
n = 0
for o in bpy.data.objects:
    if o.parent is cam:
        loc = list(o.location)
        P("###   %-14s local=%s" % (o.name, tuple(round(v, 3) for v in loc)))
        loc[2] = -loc[2]
        o.location = loc
        n += 1
P("### flipped %d children to local +z" % n)
bpy.ops.wm.save_mainfile()
P("### saved %s" % bpy.data.filepath)
