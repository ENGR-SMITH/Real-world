"""Verify the SUV door by measuring real vertices, not bound_box guesses."""
import bpy
import math
import mathutils

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'render_util.py').read())

bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()
door = bpy.data.objects['SUV_Door_FR']
body = bpy.data.objects['bmw27-Body']
print("### door parent=%s rotmode=%s loc=%s" % (door.parent.name if door.parent else None,
                                                door.rotation_mode,
                                                tuple(round(v, 3) for v in door.location)))
print("### door world origin = %s" % (tuple(round(v, 3) for v in (door.matrix_world @ mathutils.Vector((0, 0, 0)))),))
print("### body faces=%d door faces=%d  door mesh is body mesh: %s"
      % (len(body.data.polygons), len(door.data.polygons), door.data is body.data))


def vbbox(ob):
    obe = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = obe.to_mesh()
    mw = obe.matrix_world
    mn = [1e18] * 3
    mx = [-1e18] * 3
    for v in me.vertices:
        w = mw @ v.co
        for k in range(3):
            mn[k] = min(mn[k], w[k])
            mx[k] = max(mx[k], w[k])
    obe.to_mesh_clear()
    return mn, mx


door.rotation_euler.z = 0.0
bpy.context.view_layer.update()
mn0, mx0 = vbbox(door)
door.rotation_euler.z = math.radians(48)
bpy.context.view_layer.update()
mn1, mx1 = vbbox(door)
print("### door closed  x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f" % (mn0[0], mx0[0], mn0[1], mx0[1], mn0[2], mx0[2]))
print("### door open48  x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f" % (mn1[0], mx1[0], mn1[1], mx1[1], mn1[2], mx1[2]))
print("### size closed = %.2f x %.2f x %.2f m" % (mx0[0] - mn0[0], mx0[1] - mn0[1], mx0[2] - mn0[2]))
print("### open: outer face moved x %+.3f, front edge moved y %+.3f"
      % (mx1[0] - mx0[0], mn1[1] - mn0[1]))

# where are the front wheels, for a sanity check on the door's front edge
for n in ('bmw27-Wheel.Ft.L', 'bmw27-Wheel.Ft.R'):
    o = bpy.data.objects.get(n)
    if o:
        mnw, mxw = vbbox(o)
        print("### %s y %.3f..%.3f" % (n, mnw[1], mxw[1]))
door.rotation_euler.z = 0.0
bpy.context.view_layer.update()

shot('C:/temp/blender_previews/door_closed.png', (-0.5, -17.0, 1.15), (-8.3, -17.0, 0.95), lens=26)
door.rotation_euler.z = math.radians(48)
bpy.context.view_layer.update()
shot('C:/temp/blender_previews/door_open.png', (-0.5, -17.0, 1.15), (-8.3, -17.0, 0.95), lens=26)
door.rotation_euler.z = 0.0
bpy.context.view_layer.update()
print("CHECK DONE")
