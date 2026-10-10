"""80_dist_test.py -- how close to the camera does the engine stop drawing?

Every object that failed to appear sat about a metre from the lens (the HUD text,
the QQ_A/B/C cubes, W_cube); the ones that do appear are metres away.  Put six
identical blue cubes in a vertical column of screen space at 1, 2, 3, 5, 8 and 12 m
from the settled camera pose and see where drawing stops.

    blender.exe -b hud_test.blend --python 80_dist_test.py
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

P = print
sc = bpy.context.scene
CAM = Vector((-5.0, 1.35, 1.96))
X = Vector((-1.0, 0.0, 0.0))          # camera right, in world
Y = Vector((0.0, -0.2045, 0.9789))    # camera up
Z = Vector((0.0, 0.9789, 0.2045))     # camera back
HALF_W, HALF_H = 0.5625, 0.3164       # half frustum at 1 m

for o in list(bpy.data.objects):
    if o.name.startswith("D_"):
        bpy.data.objects.remove(o, do_unlink=True)

me = bpy.data.meshes.new("D_cube")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.5)
bm.to_mesh(me)
bm.free()
me.materials.append(bpy.data.materials.get("QQ_PBR"))

DISTS = (1.0, 2.0, 3.0, 5.0, 8.0, 12.0)
for i, d in enumerate(DISTS):
    ndc_x = 0.70
    ndc_y = -0.75 + i * 0.28
    u = ndc_x * HALF_W * d
    v = ndc_y * HALF_H * d
    pos = CAM + X * u + Y * v - Z * d
    o = bpy.data.objects.new("D_%02d" % int(d * 10), me)
    sc.collection.objects.link(o)
    o.location = pos
    o.rotation_euler = Matrix(((X.x, Y.x, Z.x), (X.y, Y.y, Z.y),
                               (X.z, Y.z, Z.z))).to_euler()
    P("### D_%02d at %s   (%.0f m, ndc %.2f,%.2f)" % (
        int(d * 10), tuple(round(c, 3) for c in pos), d, ndc_x, ndc_y))

P("### saving")
bpy.ops.wm.save_mainfile()
P("### saved %s" % bpy.data.filepath)
