"""Cut the SUV's pavement-side front door out of the single body mesh.

The body is one 277k-face mesh, so the door has to be separated by geometry. The
selection window is derived from the actual wheel positions rather than guessed:
the front door starts just behind the front wheel arch.
"""
import bpy
import math
import mathutils

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'render_util.py').read())

bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()

body = bpy.data.objects['bmw27-Body']
SUVCOLL = 'SUV_Rigged'

dg = bpy.context.evaluated_depsgraph_get()
wheels = []
for o in bpy.data.objects:
    if not o.name.startswith('bmw27-Wheel.') or o.type != 'MESH':
        continue      # the road wheels only - brakes and the tuk-tuk wheels must not match
    obe = o.evaluated_get(dg)
    xs = [(obe.matrix_world @ mathutils.Vector(c)) for c in obe.bound_box]
    cx = sum(v.x for v in xs) / 8.0
    cy = sum(v.y for v in xs) / 8.0
    cz = sum(v.z for v in xs) / 8.0
    rad = (max(v.z for v in xs) - min(v.z for v in xs)) / 2.0
    wheels.append((o.name, cx, cy, cz, rad))
for w in sorted(wheels, key=lambda t: t[2]):
    print("### wheel %-22s x=%.3f y=%.3f z=%.3f r=%.3f" % w)

if len(wheels) < 4:
    raise SystemExit("expected 4 SUV road wheels, found %d" % len(wheels))
front_y = max(w[2] for w in wheels)          # the car faces +Y, so the front axle is at max y
back_y = min(w[2] for w in wheels)
radius = sum(w[4] for w in wheels) / len(wheels)
print("### axles: front y=%.3f back y=%.3f wheelbase=%.3f radius=%.3f"
      % (front_y, back_y, front_y - back_y, radius))

xs = [(body.matrix_world @ mathutils.Vector(c)) for c in body.bound_box]
XMAX = max(v.x for v in xs)
YMAX = max(v.y for v in xs)
print("### body x max=%.3f y max=%.3f" % (XMAX, YMAX))

Y_FRONT = front_y + radius + 0.03
Y_BACK = Y_FRONT - 1.22
X_IN = XMAX - 0.34
Z0, Z1 = 0.42, 1.62
print("### door box x %.3f..%.3f  y %.3f..%.3f  z %.2f..%.2f" % (X_IN, XMAX + 0.03, Y_BACK, Y_FRONT, Z0, Z1))

if 'SUV_Door_FR' in bpy.data.objects:
    print("### door already separated")
else:
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = body
    for poly in body.data.polygons:
        c = body.matrix_world @ poly.center
        poly.select = (X_IN <= c.x <= XMAX + 0.03 and Y_BACK <= c.y <= Y_FRONT and Z0 <= c.z <= Z1)
    n = sum(1 for p in body.data.polygons if p.select)
    print("### selecting %d of %d faces" % (n, len(body.data.polygons)))
    if n < 200:
        raise SystemExit("door box selected only %d faces - geometry would be junk" % n)
    before = [p.index for p in body.data.polygons]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.separate(type='SELECTED')
    bpy.ops.object.mode_set(mode='OBJECT')
    new = [o for o in bpy.context.selected_objects if o is not body]
    if not new:
        raise SystemExit("separation produced nothing")
    door = new[0]
    door.name = 'SUV_Door_FR'
    door.data.name = 'SUV_Door_FR'
    print("### separated %s with %d faces (body keeps %d)" % (door.name, len(door.data.polygons),
                                                              len(body.data.polygons)))
    # hinge: vertical line at the door's own front edge, inset a little
    hinge = mathutils.Vector((XMAX - 0.18, Y_FRONT - 0.02, 0.9))
    sc = bpy.context.scene
    for o in bpy.data.objects:
        o.select_set(False)
    door.select_set(True)
    bpy.context.view_layer.objects.active = door
    sc.cursor.location = hinge
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
    door.rotation_mode = 'XYZ'
    print("### door origin now at %s (hinge target %s)" % (tuple(round(v, 3) for v in door.location),
                                                           tuple(round(v, 3) for v in hinge)))
    print("### door parent=%s" % (door.parent.name if door.parent else None))


def door_bbox():
    d = bpy.data.objects['SUV_Door_FR']
    obe = d.evaluated_get(bpy.context.evaluated_depsgraph_get())
    pts = [obe.matrix_world @ mathutils.Vector(c) for c in obe.bound_box]
    return ([min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)])


d = bpy.data.objects['SUV_Door_FR']
d.rotation_euler.z = 0.0
bpy.context.view_layer.update()
mn0, mx0 = door_bbox()
d.rotation_euler.z = math.radians(48)
bpy.context.view_layer.update()
mn1, mx1 = door_bbox()
print("### closed bbox x %.3f..%.3f y %.3f..%.3f" % (mn0[0], mx0[0], mn0[1], mx0[1]))
print("### opened bbox x %.3f..%.3f y %.3f..%.3f" % (mn1[0], mx1[0], mn1[1], mx1[1]))
print("### outer edge moved %+.3f m in x (must be positive = swings out)" % (mx1[0] - mx0[0]))
d.rotation_euler.z = 0.0
bpy.context.view_layer.update()

shot('C:/temp/blender_previews/door_closed.png', (-0.5, -17.0, 1.15), (-8.3, -17.0, 0.95), lens=26)
d.rotation_euler.z = math.radians(48)
bpy.context.view_layer.update()
shot('C:/temp/blender_previews/door_open.png', (-0.5, -17.0, 1.15), (-8.3, -17.0, 0.95), lens=26)
d.rotation_euler.z = 0.0
bpy.context.view_layer.update()

bpy.ops.wm.save_mainfile()
print("### saved")
print("SUV DOOR DONE")
