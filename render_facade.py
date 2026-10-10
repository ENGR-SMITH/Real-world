import bpy, math, sys

def p(*a):
    print(*a); sys.stdout.flush()

sc = bpy.context.scene
p("FILE", bpy.data.filepath, "ENGINE", sc.render.engine)

# material of the storefront suspects
for n in ['Cube.390', 'Cube.392', 'Cube.395', 'Cube.398', 'Plane.001', 'Street_Pavement']:
    o = bpy.data.objects.get(n)
    if not o:
        continue
    p("MATS|%s|%s" % (n, [ms.material.name if ms.material else None for ms in o.material_slots]))

# list objects whose world bbox crosses the facade plane x in [-4.30,-4.02]
import mathutils
dg = bpy.context.evaluated_depsgraph_get()
hits = []
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    ob = o.evaluated_get(dg)
    xs = [(ob.matrix_world @ mathutils.Vector(c)).x for c in ob.bound_box]
    if min(xs) <= -4.02 and max(xs) >= -4.30:
        ys = [(ob.matrix_world @ mathutils.Vector(c)).y for c in ob.bound_box]
        zs = [(ob.matrix_world @ mathutils.Vector(c)).z for c in ob.bound_box]
        hits.append((o.name, round(min(ys), 2), round(max(ys), 2), round(min(zs), 2), round(max(zs), 2),
                     round(len(ob.data.polygons)),
                     [ms.material.name if ms.material else None for ms in o.material_slots]))
p("CROSSING_FACADE", len(hits))
for h in sorted(hits):
    p("   ", h)

# how many objects inside the shop
inside = 0
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    ob = o.evaluated_get(dg)
    xs = [(ob.matrix_world @ mathutils.Vector(c)).x for c in ob.bound_box]
    if min(xs) > -4.0 and max(xs) < 4.0:
        inside += 1
p("OBJ_INSIDE_X", inside)

# camera setup and EEVEE renders
prev_cam = sc.camera
prev_engine = sc.render.engine
cd = bpy.data.cameras.new('TMPR')
cd.lens = 35
co = bpy.data.objects.new('TMPR', cd)
sc.collection.objects.link(co)
sc.camera = co
sc.render.engine = 'BLENDER_EEVEE_NEXT'
try:
    sc.eevee.taa_render_samples = 16
except Exception as e:
    p("eevee samples", e)
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.frame_set(120)

shots = [
    ('facade_street.png', (-13.0, -1.7, 2.6), (math.radians(90), 0, math.radians(-90))),
    ('facade_angle.png', (-11.5, 4.5, 2.9), (math.radians(87), 0, math.radians(-135))),
    ('entrance_ext.png', (-8.0, -6.5, 2.0), (math.radians(90), 0, math.radians(-115))),
]
for name, loc, rot in shots:
    co.location = loc
    co.rotation_euler = rot
    sc.render.filepath = 'C:/temp/blender_previews/' + name
    bpy.ops.render.render(write_still=True)
    p("shot", name)

sc.render.engine = prev_engine
sc.camera = prev_cam
bpy.data.objects.remove(co, do_unlink=True)
bpy.data.cameras.remove(cd)
p("DONE")
