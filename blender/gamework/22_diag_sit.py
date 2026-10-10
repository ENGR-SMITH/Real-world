"""What does each baked clip actually do to the mesh? Measure, don't guess."""
import bpy
import mathutils

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'anim_lib.py').read())
exec(open(GW + 'render_util.py').read())

a = bpy.data.objects['Boy1_RIG']
print("meshes:", sorted(o.name for o in bpy.data.objects if o.parent is a))


def report(clip, frames):
    a.animation_data.action = bpy.data.actions[clip]
    print("=== clip %s" % clip)
    for f in (1, frames):
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        mn = [1e18] * 3
        mx = [-1e18] * 3
        for ob in bpy.data.objects:
            if ob.parent is not a or ob.type != 'MESH':
                continue
            obe = ob.evaluated_get(dg)
            me = obe.to_mesh()
            for v in me.vertices:
                w = obe.matrix_world @ v.co
                for k in range(3):
                    mn[k] = min(mn[k], w[k])
                    mx[k] = max(mx[k], w[k])
            obe.to_mesh_clear()
        print("  f%-3d bbox min=%s max=%s size=%s" % (f, ["%.2f" % v for v in mn], ["%.2f" % v for v in mx],
                                                      ["%.2f" % (mx[k] - mn[k]) for k in range(3)]))
        for n in ('Root', 'DEF.pelvis', 'DEF.head', 'DEF.foot.L', 'DEF.hand.L'):
            pb = a.pose.bones[n]
            w = a.matrix_world @ pb.head
            print("     %-12s head=(%7.3f,%7.3f,%7.3f) loc=%s scale=%s" % (
                n, w.x, w.y, w.z,
                ["%.3f" % v for v in pb.location], ["%.3f" % v for v in pb.scale]))


for clip, frames in (('walk', 32), ('idle', 64), ('reach', 36), ('sit', 48)):
    report(clip, frames)

# a wide shot of the sit pose to see where the character went
a.animation_data.action = bpy.data.actions['sit']
shot('C:/temp/blender_previews/sit_wide.png', (a.location.x - 7.0, a.location.y - 6.0, 2.5),
     (a.location.x, a.location.y, 0.9), lens=28, frame=14)
print("DIAG DONE")
