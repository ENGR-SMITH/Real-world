"""Can we pose this 1037-bone rig from Python? Move an IK hand and both IK feet,
then measure the deformation and render two views."""
import bpy
from mathutils import Vector

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'boy_rig.py').read())
exec(open(GW + 'render_util.py').read())

a = arm('Boy1_RIG')


def body_bbox(tag):
    dg = bpy.context.evaluated_depsgraph_get()
    ob = bpy.data.objects['Boy1_body'].evaluated_get(dg)
    me = ob.to_mesh()
    mn = [1e18] * 3
    mx = [-1e18] * 3
    for v in me.vertices:
        w = ob.matrix_world @ v.co
        for k in range(3):
            mn[k] = min(mn[k], w[k])
            mx[k] = max(mx[k], w[k])
    ob.to_mesh_clear()
    print("BBOX %-10s min=%s max=%s" % (tag, ["%.3f" % v for v in mn], ["%.3f" % v for v in mx]))
    return mn, mx


print("Root mode props:", {k: a.pose.bones['Root'][k] for k in MODE_PROPS})
body_bbox('rest')
print("IK.hand.L world head", ["%.3f" % v for v in bone_world_head(a, 'IK.hand.L')])
print("IK.foot.L world head", ["%.3f" % v for v in bone_world_head(a, 'IK.foot.L')])
print("FK.upper_arm.L world head", ["%.3f" % v for v in bone_world_head(a, 'FK.upper_arm.L')])

set_modes(a, arms_ik=True, legs_ik=True)
body_bbox('modes')

# --- pose it: left arm reaches forward, left foot steps forward, right foot back
move_to(a, 'IK.hand.L', a2w(a, Vector((0.30, -4.2, 9.2))))
move_to(a, 'IK.hand.R', a2w(a, Vector((-1.6, 0.6, 8.4))))
move_to(a, 'IK.foot.L', a2w(a, Vector((0.638, -2.6, 0.55))))
move_to(a, 'IK.foot.R', a2w(a, Vector((-0.638, 2.8, 0.55))))
print("posed IK.hand.L world head", ["%.3f" % v for v in bone_world_head(a, 'IK.hand.L')])
print("posed IK.foot.L world head", ["%.3f" % v for v in bone_world_head(a, 'IK.foot.L')])
print("posed DEF.hand.L world head", ["%.3f" % v for v in bone_world_head(a, 'DEF.hand.L')])
print("posed DEF.foot.L world head", ["%.3f" % v for v in bone_world_head(a, 'DEF.foot.L')])
body_bbox('posed')

px, py = a.location.x, a.location.y
shot('C:/temp/blender_previews/pose_front.png', (px, py - 4.0, 1.3), (px, py, 0.85), lens=40)
shot('C:/temp/blender_previews/pose_side.png', (px - 4.0, py, 1.3), (px, py, 0.85), lens=40)
print("POSE TEST DONE")
