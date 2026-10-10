"""Build + bake the walk cycle, prove the bake matches the rig, render a filmstrip."""
import bpy
import time

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'anim_lib.py').read())
exec(open(GW + 'render_util.py').read())

FRAMES = 32
PROBE_BONES = ('DEF.foot.L', 'DEF.foot.R', 'DEF.hand.L', 'DEF.hand.R', 'DEF.head', 'DEF.pelvis')
PROBE_FRAMES = (1, 9, 17, 25, 33)


def probe():
    res = {}
    for f in PROBE_FRAMES:
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        res[f] = {n: tuple(a.matrix_world @ a.pose.bones[n].head) for n in PROBE_BONES}
    return res


for name in ('Boy1_RIG', 'Boy2_RIG'):
    a = bpy.data.objects[name]
    t0 = time.time()
    author_clip(a, 'walk', walk_pose, FRAMES)
    t_author = time.time() - t0
    t0 = time.time()
    baked = bake_clip(a, 'walk', FRAMES)
    t_bake = time.time() - t0
    print("### %s: authored %.1fs, baked %.1fs, fcurves=%d" % (name, t_author, t_bake, len(baked.fcurves)))

    active = probe()
    mute_constraints(a, True)
    muted = probe()
    worst = 0.0
    worst_where = None
    for f in active:
        for n in active[f]:
            d = max(abs(active[f][n][k] - muted[f][n][k]) for k in range(3))
            if d > worst:
                worst, worst_where = d, (f, n)
    print("### %s BAKE CHECK: worst deviation %.5f m at %s" % (name, worst, worst_where))
    mute_constraints(a, False)
    a.animation_data.action = baked

t0 = time.time()
bpy.ops.wm.save_mainfile()
print("### saved %s in %.1fs" % (bpy.data.filepath, time.time() - t0))

a = bpy.data.objects['Boy1_RIG']
for f in (1, 5, 9, 13, 17, 21, 25, 29):
    shot('C:/temp/blender_previews/walk_%02d.png' % f,
         (a.location.x - 3.6, a.location.y - 1.2, 1.05), (a.location.x, a.location.y, 0.85),
         lens=50, frame=f)
print("### DONE")
