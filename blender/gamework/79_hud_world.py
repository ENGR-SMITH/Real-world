"""79_hud_world.py -- put copies of the HUD text in world space, one metre ahead.

The engine draws world objects (QQ_F/G/H on the road show up in live_a.png) but no
child of the active camera ever drew.  So: take three of the HUD lines, copy them,
unparent, and place them by hand exactly where the camera-parented originals sit
when the camera has settled behind a boy parked at (-5, -2):

    camera  (-5.0, 1.35, 1.96)
    X (-1, 0, 0)   Y (0, -0.2045, 0.9789)   Z (0, 0.9789, 0.2045)

    world = camera + X*u + Y*v - Z*1.0            (u, v = the original's local x, y)

If these render, the fix is to place the HUD in world space from game.py each frame.

    blender.exe -b hud_test.blend --python 79_hud_world.py
"""

import bpy
from mathutils import Matrix, Vector

P = print
sc = bpy.context.scene
CAM = Vector((-5.0, 1.35, 1.96))
X = Vector((-1.0, 0.0, 0.0))
Y = Vector((0.0, -0.2045, 0.9789))
Z = Vector((0.0, 0.9789, 0.2045))
ORI = Matrix(((X.x, Y.x, Z.x, 0.0),
              (X.y, Y.y, Z.y, 0.0),
              (X.z, Y.z, Z.z, 0.0),
              (0.0, 0.0, 0.0, 1.0)))

WANT = ("HUD_Help", "HUD_Title1", "P_DoorOpen", "P_Drive")

for o in list(bpy.data.objects):
    if o.name.startswith("W_"):
        bpy.data.objects.remove(o, do_unlink=True)

for nm in WANT:
    src = bpy.data.objects.get(nm)
    if src is None:
        P("### %s missing" % nm)
        continue
    c = src.copy()
    c.data = src.data.copy()
    c.name = "W_" + nm
    c.parent = None
    c.matrix_parent_inverse.identity()
    u, v = src.location[0], src.location[1]
    pos = CAM + X * u + Y * v - Z * 1.0
    c.matrix_world = Matrix(((ORI[0][0], ORI[0][1], ORI[0][2], pos.x),
                             (ORI[1][0], ORI[1][1], ORI[1][2], pos.y),
                             (ORI[2][0], ORI[2][1], ORI[2][2], pos.z),
                             (0.0, 0.0, 0.0, 1.0)))
    sc.collection.objects.link(c)
    P("### %-14s world=%s verts=%d mats=%s" % (
        c.name, tuple(round(x, 3) for x in pos), len(c.data.vertices),
        [m.name for m in c.data.materials]))

# a control cube at the same depth, world space
me = bpy.data.meshes.new("W_cube")
import bmesh
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.12)
bm.to_mesh(me)
bm.free()
cube = bpy.data.objects.new("W_cube", me)
me.materials.append(bpy.data.materials.get("QQ_PBR"))
sc.collection.objects.link(cube)
cube.location = CAM + X * 0.35 + Y * (-0.05) - Z * 1.0
P("### W_cube world=%s" % (tuple(round(x, 3) for x in cube.location),))

P("### saving")
bpy.ops.wm.save_mainfile()
P("### saved %s" % bpy.data.filepath)
