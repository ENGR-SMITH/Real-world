import bpy, sys
from mathutils import Vector

def p(*a):
    print(*a); sys.stdout.flush()

SKIP = {"Plane.001", "Plane.006"}
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name not in SKIP]

# flat, unmistakable colours so every candidate part can be located by eye
TAG = {
    "AnodizedMetal": (255, 0, 255),   # magenta
    "Material.002": (0, 255, 255),    # cyan
    "Material.003": (255, 255, 0),    # yellow
    "Material.007": (255, 255, 255),  # white
    "Material.004": (255, 128, 0),    # orange
    "Material.005": (255, 105, 180),  # pink
    "Material.008": (0, 255, 0),      # green
    "Material": (255, 0, 0),          # red
}
for name, rgb in TAG.items():
    m = bpy.data.materials.get(name)
    if not m:
        p("missing material", name); continue
    m.use_nodes = False
    m.diffuse_color = (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1.0)
    p("tagged %-16s -> %s" % (name, rgb))

sc = bpy.context.scene
mn = Vector((1e9, 1e9, 1e9)); mx = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
ctr = (mn + mx) / 2; size = mx - mn

sc.render.engine = "BLENDER_EEVEE_NEXT"
sc.render.resolution_x = 900
sc.render.resolution_y = 700
if "Sun" not in bpy.data.objects:
    bpy.ops.object.light_add(type="SUN", location=(ctr.x, ctr.y, mx.z + 20))
    bpy.context.object.data.energy = 5

cam = bpy.data.objects.new("ProbeCam", bpy.data.cameras.new("ProbeCam"))
sc.collection.objects.link(cam); sc.camera = cam
tgt = bpy.data.objects.new("T", None); sc.collection.objects.link(tgt); tgt.location = ctr
con = cam.constraints.new("TRACK_TO"); con.target = tgt
con.track_axis = "TRACK_NEGATIVE_Z"; con.up_axis = "UP_Y"

def shot(direction, dist_mul, out):
    d = Vector(direction).normalized()
    cam.location = ctr + d * (max(size) * dist_mul)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True); p("wrote", out)

shot((0.9, -1.0, 0.45), 1.05, "E:/Reality/webapp/public/ref/tag_a.png")
shot((0.0, -1.0, 0.12), 0.95, "E:/Reality/webapp/public/ref/tag_front.png")
shot((1.0, 0.9, 0.45), 1.05, "E:/Reality/webapp/public/ref/tag_rear.png")
