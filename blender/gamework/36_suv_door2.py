"""Split the SUV's pavement-side front door out of the body mesh (bmesh edition).

The previous attempt used polygon.select + mesh.separate, which tore the wrong
region. This version edits the mesh data directly with bmesh: the door becomes a
copy of the body with everything outside the door box deleted, and the body loses
exactly those faces, so the two are guaranteed complementary.

The door box is anchored to the front wheel arch, not guessed: on this model the
front axle sits ~1.0 m behind the nose and the door starts behind its arch.
"""
import bpy
import bmesh
import math
import mathutils
from mathutils import Matrix

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'render_util.py').read())

bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()

body = bpy.data.objects['bmw27-Body']
mw = body.matrix_world.copy()


def vbbox(ob):
    obe = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = obe.to_mesh()
    m = obe.matrix_world
    mn = [1e18] * 3
    mx = [-1e18] * 3
    for v in me.vertices:
        w = m @ v.co
        for k in range(3):
            mn[k] = min(mn[k], w[k])
            mx[k] = max(mx[k], w[k])
    obe.to_mesh_clear()
    return mn, mx


bmn, bmx = vbbox(body)
front = vbbox(bpy.data.objects['bmw27-Wheel.Ft.L'])[0]      # min corner of the front wheel
front_arch_rear = vbbox(bpy.data.objects['bmw27-Wheel.Ft.L'])[0][1]
XMAX = bmx[0]
FACES = 'SUV_Door_FR'

Y_FRONT = front_arch_rear - 0.04          # just aft of the front arch
Y_BACK = Y_FRONT - 1.22                   # door length
X_IN = XMAX - 0.36
Z0, Z1 = 0.45, 1.60
HINGE = mathutils.Vector((XMAX - 0.20, Y_FRONT - 0.02, 0.95))
print("### car bbox x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f" % (bmn[0], bmx[0], bmn[1], bmx[1], bmn[2], bmx[2]))
print("### front arch rear edge y=%.3f" % front_arch_rear)
print("### door box x %.3f..%.3f y %.3f..%.3f z %.2f..%.2f" % (X_IN, XMAX + 0.03, Y_BACK, Y_FRONT, Z0, Z1))
print("### hinge world = %s" % (tuple(round(v, 3) for v in HINGE),))


def inside(co_world):
    return (X_IN <= co_world.x <= XMAX + 0.03 and Y_BACK <= co_world.y <= Y_FRONT
            and Z0 <= co_world.z <= Z1)


def partition(me, keep_inside):
    """delete faces of `me` whose world centre is inside/outside the door box"""
    bm = bmesh.new()
    bm.from_mesh(me)
    doomed = [f for f in bm.faces if inside(mw @ f.calc_center_median()) != keep_inside]
    n = len(bm.faces)
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    bm.to_mesh(me)
    bm.free()
    me.update()
    return n - len(doomed), len(doomed)


if FACES in bpy.data.objects:
    print("### already split; delete it first")
else:
    door_me = body.data.copy()
    door_me.name = FACES
    door = bpy.data.objects.new(FACES, door_me)
    for c in body.users_collection:
        c.objects.link(door)
    door.parent = bpy.data.objects['SUV_root']      # ride with the car, no armature involved
    door.matrix_parent_inverse = Matrix.Identity(4)
    door.matrix_world = mw.copy()
    door.rotation_mode = 'XYZ'

    keep, gone = partition(door_me, True)
    print("### door : kept %d faces, removed %d" % (keep, gone))
    keep_b, gone_b = partition(body.data, False)
    print("### body : kept %d faces, removed %d" % (keep_b, gone_b))

    # put the door's origin on the hinge line: shift the geometry, then the object.
    # world = mw @ local, and we want world = T @ (local - local_hinge),
    # so T = mw @ Translation(local_hinge) ... applied with a settled parent matrix.
    local_hinge = mw.inverted() @ HINGE
    door_me.transform(Matrix.Translation(-local_hinge))
    door.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    door.matrix_world = mw @ Matrix.Translation(local_hinge)
    bpy.context.view_layer.update()
    print("### door base rotation (rad) =", tuple(round(v, 4) for v in door.rotation_euler),
          " scale =", tuple(round(v, 5) for v in door.scale))

    dmn, dmx = vbbox(door)
    print("### door origin world = %s" % (tuple(round(v, 3) for v in (door.matrix_world @ mathutils.Vector((0, 0, 0)))),))
    print("### door bbox x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f  (%.2f x %.2f x %.2f m)"
          % (dmn[0], dmx[0], dmn[1], dmx[1], dmn[2], dmx[2],
             dmx[0] - dmn[0], dmx[1] - dmn[1], dmx[2] - dmn[2]))

    BASE_Z = door.rotation_euler.z
    door.rotation_euler.z = BASE_Z + math.radians(48)
    bpy.context.view_layer.update()
    omn, omx = vbbox(door)
    print("### door open48 bbox x %.3f..%.3f y %.3f..%.3f" % (omn[0], omx[0], omn[1], omx[1]))
    print("### outer skin moved x %+.3f (positive = swings away from the car)" % (omx[0] - dmx[0]))
    door.rotation_euler.z = BASE_Z
    bpy.context.view_layer.update()

shot('C:/temp/blender_previews/door_closed.png', (-0.5, -17.0, 1.15), (-8.3, -17.0, 0.95), lens=26)
d = bpy.data.objects[FACES]
BASE_Z2 = d.rotation_euler.z
d.rotation_euler.z = BASE_Z2 + math.radians(48)
bpy.context.view_layer.update()
shot('C:/temp/blender_previews/door_open.png', (-0.5, -17.0, 1.15), (-8.3, -17.0, 0.95), lens=26)
shot('C:/temp/blender_previews/door_open34.png', (-3.0, -12.0, 2.4), (-7.6, -16.5, 0.9), lens=32)
d.rotation_euler.z = BASE_Z2
bpy.context.view_layer.update()

bpy.ops.wm.save_mainfile()
print("### saved")
print("SUV DOOR 2 DONE")
