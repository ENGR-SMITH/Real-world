"""Rebuild just the walk clip with a usable stride.

The first version used step=2.2 local units, which is only 0.30 m per footfall --
0.44 m/s at 1x playback, far slower than a character walks. Here the stride is
lengthened and the cycle shortened so 1x playback is a natural walk and the game
drives the clip speed from the real ground speed.

One action is shared by both rigs (they are copies of the same skeleton, and the
engine resolves actions by name), which also avoids the walk.001 duplicates the
earlier build script produced.

Run:  blender -b --factory-startup Shop_with_people.blend --python 24_rebuild_walk.py
"""
import bpy
import time

GW = 'E:/Reality/blender/gamework/'
exec(open(GW + 'anim_lib.py').read())

STEP = 3.4          # local units per half-stride
FRAMES = 22         # 0.917 s cycle at 24 fps
PARAMS = dict(step=STEP, lift=0.85, bob=0.30, lean=4.0, arm_swing=24.0, sway=4.0)

SOLE = ('boot.L', 'boot.R', 'boot_laces.L', 'boot_laces.R')


def clear_walk():
    for o in bpy.data.objects:
        if o.animation_data and o.animation_data.action and o.animation_data.action.name.startswith('walk'):
            o.animation_data.action = None
    for act in list(bpy.data.actions):
        if act.name.split('.')[0].startswith('walk'):
            bpy.data.actions.remove(act)


def sole_report(arm, frames):
    """lowest boot vertex per frame: the planted foot must stay on the ground"""
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.parent is arm and
              o.name.split('_', 1)[-1] in SOLE]
    out = []
    for f in range(1, frames + 2):
        sc.frame_set(f)
        bpy.context.view_layer.update()
        z = 1e18
        for ob in meshes:
            obe = ob.evaluated_get(dg)
            me = obe.to_mesh()
            for v in me.vertices:
                z = min(z, (obe.matrix_world @ v.co).z)
            obe.to_mesh_clear()
        out.append(round(z, 4))
    return out


clear_walk()
STRIDE = 2.0 * STEP * 0.135026
print("### target stride %.3f m, cycle %.3f s -> %.3f m/s at 1x"
      % (STRIDE, FRAMES / 24.0, STRIDE / (FRAMES / 24.0)))

arm = bpy.data.objects['Boy1_RIG']
a = arm          # anim_lib's pose helpers resolve the rig through this global
t0 = time.time()
author_clip(arm, 'walk', lambda i, frames, **kw: walk_pose(i, frames, **PARAMS), FRAMES)
ta = time.time() - t0
t0 = time.time()
baked = bake_clip(arm, 'walk', FRAMES)
tb = time.time() - t0
baked.name = 'walk'
baked.use_fake_user = True

zs = sole_report(arm, FRAMES)
print("### walk auth %.1fs bake %.1fs fcurves=%d  action=%s" % (ta, tb, len(baked.fcurves), baked.name))
print("###   sole z per frame: %s" % (zs,))
print("###   sole min %.4f max %.4f  (ground is 0.06, planted foot should sit there)"
      % (min(zs), max(zs)))

bpy.data.objects['Boy1_RIG'].animation_data.action = baked
bpy.data.objects['Boy2_RIG'].animation_data.action = baked
clear_walk_extra = [act for act in bpy.data.actions if act.name != 'walk' and act.name.split('.')[0].startswith('walk')]
for act in clear_walk_extra:
    print("###   removing leftover action", act.name)
    bpy.data.actions.remove(act)

print("### actions now:", sorted(x.name for x in bpy.data.actions))
bpy.context.scene.frame_set(1)
bpy.ops.wm.save_mainfile()
print("### saved")
print("REBUILD WALK DONE")
