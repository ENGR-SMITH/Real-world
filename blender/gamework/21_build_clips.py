"""Build the remaining clips (idle, reach, sit), bake + verify each, render checks."""
import bpy
import time
import mathutils

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'anim_lib.py').read())
exec(open(GW + 'render_util.py').read())

CLIPS = [('idle', idle_pose, 64), ('reach', reach_pose, 36), ('sit', sit_pose, 48)]
PROBE_BONES = ('DEF.foot.L', 'DEF.foot.R', 'DEF.hand.L', 'DEF.hand.R', 'DEF.head', 'DEF.pelvis')


def probe(a, frames):
    res = {}
    for f in (1, max(2, frames // 2), frames + 1):
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


# ---------------------------------------------------------------- SUV interior probe
dg = bpy.context.evaluated_depsgraph_get()
mn = [1e18] * 3
mx = [-1e18] * 3
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    if 'SUV_Rigged' not in [c.name for c in o.users_collection]:
        continue
    ob = o.evaluated_get(dg)
    for c in ob.bound_box:
        w = ob.matrix_world @ mathutils.Vector(c)
        for k in range(3):
            mn[k] = min(mn[k], w[k])
            mx[k] = max(mx[k], w[k])
print("### SUV bbox min=%s max=%s size=%s" % (["%.3f" % v for v in mn], ["%.3f" % v for v in mx],
                                              ["%.3f" % (mx[k] - mn[k]) for k in range(3)]))

# ---------------------------------------------------------------- build the clips
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
        print("### %s %-6s authored %4.1fs baked %4.1fs fcurves=%d  bake-check %.5f m %s"
              % (name, clip, ta, tb, len(baked.fcurves), dev, where))
        a.animation_data.action = baked

t0 = time.time()
bpy.ops.wm.save_mainfile()
print("### saved in %.1fs -> %s" % (time.time() - t0, bpy.data.filepath))

# ---------------------------------------------------------------- render checks
a = bpy.data.objects['Boy1_RIG']
bx, by = a.location.x, a.location.y
for clip, fn, frames in CLIPS:
    a.animation_data.action = bpy.data.actions[clip]
    picks = [1, int(frames * 0.3), int(frames * 0.5), int(frames * 0.7)]
    for f in picks:
        shot('C:/temp/blender_previews/%s_%02d.png' % (clip, f),
             (bx - 3.1, by - 2.6, 1.15), (bx, by, 0.85), lens=50, frame=f)
print("### DONE")
