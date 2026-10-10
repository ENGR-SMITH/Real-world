"""Build all clips (walk, idle, reach, sit) for both characters, bake + verify each.

Run:  blender -b --factory-startup Shop_with_people.blend --python 23_build_all.py
"""
import bpy
import time

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'anim_lib.py').read())
exec(open(GW + 'render_util.py').read())

CLIPS = [('walk', walk_pose, 32), ('idle', idle_pose, 64),
         ('reach', reach_pose, 36), ('sit', sit_pose, 48)]
PROBE_BONES = ('DEF.foot.L', 'DEF.foot.R', 'DEF.hand.L', 'DEF.hand.R', 'DEF.head', 'DEF.pelvis')


def probe(a, frames):
    res = {}
    for f in (1, frames // 2, frames + 1):
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        res[f] = {n: tuple(a.matrix_world @ a.pose.bones[n].head) for n in PROBE_BONES}
    return res


def deviation(x, y):
    worst, where = 0.0, None
    for f in x:
        for n in x[f]:
            d = max(abs(x[f][n][k] - y[f][n][k]) for k in range(3))
            if d > worst:
                worst, where = d, (f, n)
    return worst, where


def mesh_bbox(a):
    mn = [1e18] * 3
    mx = [-1e18] * 3
    dg = bpy.context.evaluated_depsgraph_get()
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
    return mn, mx


for name in ('Boy1_RIG', 'Boy2_RIG'):
    a = bpy.data.objects[name]
    for clip, fn, frames in CLIPS:
        t0 = time.time()
        author_clip(a, clip, fn, frames)
        ta = time.time() - t0
        t0 = time.time()
        baked = bake_clip(a, clip, frames)
        tb = time.time() - t0
        active = probe(a, frames)
        mute_constraints(a, True)
        muted = probe(a, frames)
        mute_constraints(a, False)
        dev, where = deviation(active, muted)
        bpy.context.scene.frame_set(1)
        bpy.context.view_layer.update()
        mn1, mx1 = mesh_bbox(a)
        bpy.context.scene.frame_set(frames // 2)
        bpy.context.view_layer.update()
        mn2, mx2 = mesh_bbox(a)
        print("### %s %-6s auth %4.1fs bake %4.1fs fcurves=%d check=%.5f  zmin f1=%.3f f%d=%.3f  height=%.3f"
              % (name, clip, ta, tb, len(baked.fcurves), dev, mn1[2], frames // 2, mn2[2],
                 mx2[2] - mn2[2]))
        a.animation_data.action = baked

t0 = time.time()
bpy.ops.wm.save_mainfile()
print("### saved in %.1fs" % (time.time() - t0))

# contact sheets: one clip per row, 4 poses
a = bpy.data.objects['Boy1_RIG']
bx, by = a.location.x, a.location.y
for clip, fn, frames in CLIPS:
    a.animation_data.action = bpy.data.actions[clip]
    for f in (1, int(frames * 0.3), int(frames * 0.55), int(frames * 0.8)):
        shot('C:/temp/blender_previews/%s_%02d.png' % (clip, f),
             (bx - 3.1, by - 2.6, 1.15), (bx, by, 0.85), lens=50, frame=f)
print("### DONE")
