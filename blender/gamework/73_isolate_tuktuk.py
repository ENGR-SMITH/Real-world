import bpy, sys
from mathutils import Vector

def p(*a):
    print(*a); sys.stdout.flush()

SKIP = {"Plane.001", "Plane.006"}
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name not in SKIP]
body = bpy.data.objects["Plane"]

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE_NEXT"
sc.render.resolution_x = 900
sc.render.resolution_y = 600
if "Sun" not in bpy.data.objects:
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 40)); bpy.context.object.data.energy = 5
for o in meshes:
    if o.type == "LIGHT":
        continue
sc.world = sc.world or bpy.data.worlds.new("W")
sc.world.use_nodes = True

cam = bpy.data.objects.new("ProbeCam", bpy.data.cameras.new("ProbeCam"))
sc.collection.objects.link(cam); sc.camera = cam
tgt = bpy.data.objects.new("T", None); sc.collection.objects.link(tgt)
con = cam.constraints.new("TRACK_TO"); con.target = tgt
con.track_axis = "TRACK_NEGATIVE_Z"; con.up_axis = "UP_Y"

# where is the tuk tuk, in world space?
mn = Vector((1e9, 1e9, 1e9)); mx = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
ctr = (mn + mx) / 2; size = mx - mn
tgt.location = ctr

def shot(direction, dist_mul, out):
    d = Vector(direction).normalized()
    cam.location = ctr + d * (max(size) * dist_mul)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True); p("wrote", out)

# 1. plain side profile (along the width axis) and a front-left 3/4
shot((0.0, -1.0, 0.12), 0.85, "E:/Reality/webapp/public/ref/iso_side.png")
shot((0.9, -0.55, 0.30), 0.9, "E:/Reality/webapp/public/ref/iso_34.png")

# 2. one material at a time: everything dim, the target bright
dim = (0.08, 0.08, 0.08, 1)
for name in ("AnodizedMetal", "Material.002", "Material.003", "Material.007", "Aluminium"):
    for m in bpy.data.materials:
        m.use_nodes = False
        m.diffuse_color = dim
    m = bpy.data.materials.get(name)
    if not m:
        p("missing", name); continue
    m.use_nodes = False
    m.diffuse_color = (1.0, 0.85, 0.0, 1.0)
    p("isolating", name)
    shot((0.75, -0.9, 0.35), 1.0, "E:/Reality/webapp/public/ref/iso_%s.png" % name.replace(".", "_"))
