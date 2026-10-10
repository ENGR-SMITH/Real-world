import bpy, mathutils

p = print
p("=== BOY RIG ANALYSIS:", bpy.data.filepath)
arm = bpy.data.objects['Boy_RIG']

# --- true world bbox of the character meshes only
dg = bpy.context.evaluated_depsgraph_get()
mn = [1e18] * 3
mx = [-1e18] * 3
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    if o.parent is not arm and o.name not in ('body', 'hair', 'shirt', 'shorts'):
        continue
    ob = o.evaluated_get(dg)
    for c in ob.bound_box:
        w = ob.matrix_world @ mathutils.Vector(c)
        for k in range(3):
            mn[k] = min(mn[k], w[k])
            mx[k] = max(mx[k], w[k])
p("CHAR_BBOX min=%s max=%s" % (["%.3f" % v for v in mn], ["%.3f" % v for v in mx]))
p("CHAR_HEIGHT=%.3f  WIDTH=%.3f DEPTH=%.3f" % (mx[2] - mn[2], mx[0] - mn[0], mx[1] - mn[1]))

# --- which meshes belong to the character
p("CHAR_MESHES", [(o.name, len(o.data.vertices)) for o in bpy.data.objects
                  if o.type == 'MESH' and (o.parent is arm or o.parent is None) and
                  (o.parent is arm)])

# --- rig custom properties
p("ARM_CUSTOM_PROPS", {k: arm[k] for k in arm.keys()})
pb = arm.pose
p("BONE_CUSTOM_PROPS:")
for b in pb.bones:
    keys = [k for k in b.keys() if k not in ('_RNA_UI',)]
    if keys:
        p("   ", b.name, {k: b[k] for k in keys})

# --- animator-facing bones: no DEF./MCH/INT/tweak prefix, no constraints
p("=== CONTROL BONE REST POSITIONS (head/tail world) ===")
interesting = ['Root', 'body', 'pelvis', 'tweak.pelvis', 'spine_01', 'spine_02', 'chest', 'neck_01', 'neck_02',
               'head', 'jaw', 'eyes_panel.parent-head',
               'IK.foot.L', 'IK.foot.R', 'IK.leg.pole.L', 'IK.leg.pole.R',
               'IK.hand.L', 'IK.hand.R', 'IK.pole.arm.parent-IK.hand.L', 'IK.pole.arm.parent-IK.hand.R',
               'FK.thigh.L', 'FK.shin.L', 'FK.foot.L', 'FK.upper_arm.L', 'FK.lower_arm.L', 'FK.hand.L',
               'FK.thigh.R', 'FK.shin.R', 'FK.foot.R', 'FK.upper_arm.R', 'FK.lower_arm.R', 'FK.hand.R',
               'shorts.volume.middle.F', 'shirt.volume.middle.F']
for n in interesting:
    if n in arm.data.bones:
        b = arm.data.bones[n]
        h = arm.matrix_world @ b.head_local
        t = arm.matrix_world @ b.tail_local
        p("BONE|%s|head=(%.3f,%.3f,%.3f)|tail=(%.3f,%.3f,%.3f)|parent=%s|use_deform=%s|pbone_cons=%s" % (
            n, h[0], h[1], h[2], t[0], t[1], t[2],
            b.parent.name if b.parent else '-', b.use_deform,
            [c.type for c in pb.bones[n].constraints]))

# --- constraints on all bones, grouped by type
from collections import Counter
cc = Counter()
for b in pb.bones:
    for c in b.constraints:
        cc[c.type] += 1
p("CONSTRAINT_TYPES", dict(cc))

# --- drivers
p("=== DRIVERS")
ad = arm.animation_data
if ad and ad.drivers:
    for d in ad.drivers:
        p("DRV|%s|%s|%s" % (d.data_path, d.array_index, d.driver.expression))
for b in pb.bones:
    if b.animation_data and b.animation_data.drivers:
        for d in b.animation_data.drivers:
            p("DRV|pbone %s|%s|%s" % (b.name, d.data_path, d.driver.expression))

# --- current pose state of the IK/FK controls
p("=== CURRENT POSE VALUES")
for n in ['Root', 'body', 'IK.foot.L', 'IK.foot.R', 'IK.hand.L', 'IK.hand.R', 'FK.thigh.L', 'FK.upper_arm.L', 'spine_01', 'chest', 'head']:
    if n in pb.bones:
        b = pb.bones[n]
        p("POSE|%s|loc=(%.3f,%.3f,%.3f)|rotmode=%s|euler=(%.3f,%.3f,%.3f)|scale=(%.3f,%.3f,%.3f)" % (
            n, b.location[0], b.location[1], b.location[2], b.rotation_mode,
            b.rotation_euler[0], b.rotation_euler[1], b.rotation_euler[2],
            b.scale[0], b.scale[1], b.scale[2]))

# --- collections of the character objects
p("=== COLLECTIONS")
for c in bpy.data.collections:
    p("COLL|%s|%d objs" % (c.name, len(c.objects)))

# --- visibility flags of character meshes
p("=== VIS")
for o in bpy.data.objects:
    if o.parent is arm:
        p("VIS|%s|hide_viewport=%s|hide_render=%s|hide_get=%s" % (o.name, o.hide_viewport, o.hide_render, o.hide_get()))
p("DONE")
