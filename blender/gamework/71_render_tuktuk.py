import bpy, math, sys
from mathutils import Vector

def p(*a):
    print(*a); sys.stdout.flush()

SKIP = {"Plane.001", "Plane.006"}  # the two 2000 m ground planes

sc = bpy.context.scene
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name not in SKIP]
p("meshes:", len(meshes))

# world bbox over the real geometry
mn = Vector((1e9, 1e9, 1e9)); mx = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
ctr = (mn + mx) / 2
size = (mx - mn)
p("bbox min %.2f,%.2f,%.2f max %.2f,%.2f,%.2f size %.2f,%.2f,%.2f" % (*mn, *mx, *size))

sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [
    i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
sc.render.resolution_x = 900
sc.render.resolution_y = 700
sc.render.film_transparent = False

# a soft sun so the panels read
for name in ("Sun",):
    if name not in bpy.data.objects:
        bpy.ops.object.light_add(type="SUN", location=(ctr.x, ctr.y, mx.z + 20))
        bpy.context.object.data.energy = 4

cam_data = bpy.data.cameras.new("ProbeCam")
cam = bpy.data.objects.new("ProbeCam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam

def shot(direction, dist_mul, out):
    d = Vector(direction).normalized()
    radius = max(size) * dist_mul
    cam.location = ctr + d * radius
    tr = cam.constraints.new("TRACK_TO")
    empty = bpy.data.objects.get("ProbeTarget") or bpy.data.objects.new("ProbeTarget", None)
    if empty.name not in sc.collection.objects:
        sc.collection.objects.link(empty)
    empty.location = ctr
    tr.target = empty
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    p("wrote", out)

shot((0.9, -1.0, 0.55), 1.15, "E:/Reality/webapp/public/ref/tuktuk_a.png")
shot((-0.95, -1.0, 0.35), 1.15, "E:/Reality/webapp/public/ref/tuktuk_b.png")
shot((0.0, -1.0, 0.10), 1.05, "E:/Reality/webapp/public/ref/tuktuk_front.png")

# and the body panel on its own, from the front-left
body = bpy.data.objects.get("Plane")
if body:
    for o in meshes:
        if o is not body:
            o.hide_render = True
    shot((0.9, -1.0, 0.45), 1.15, "E:/Reality/webapp/public/ref/tuktuk_body.png")
    # now with the red shell hidden, to expose what sits behind it
    for o in meshes:
        o.hide_render = False
    body.hide_render = True
    shot((0.9, -1.0, 0.45), 1.15, "E:/Reality/webapp/public/ref/tuktuk_nobody.png")
